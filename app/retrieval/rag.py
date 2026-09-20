"""Retrieval-augmented generation: retrieve context, then call an LLM."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

import boto3
from botocore.config import Config

from app.retrieval.search import Hit, hybrid_search

CHAT_MODEL_ID = os.getenv("CHAT_MODEL_ID", "amazon.nova-lite-v1:0")
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
MAX_CONTEXT_CHARS = int(os.getenv("MAX_CONTEXT_CHARS", "12000"))
MAX_TOKENS = int(os.getenv("MAX_TOKENS", "1024"))

# Asking for Markdown is what lets the console render headings, bold figures and
# tables. Kept explicit and ordered, because vague style instructions produce
# inconsistent structure between questions.
SYSTEM_PROMPT = """You are a banking knowledge assistant. You answer strictly from the numbered context supplied with each question.

GROUNDING
- Use only the context. Never add facts from your own knowledge, even if you are confident they are correct.
- Cite the passage you used inline as [1], [2], immediately after the claim it supports.
- If the context does not answer the question, say exactly what is missing and stop. Do not speculate or offer a general answer.
- If the context is partially relevant, answer the part it covers and state plainly which part it does not.
- If passages disagree, surface the conflict rather than silently choosing one.

FORMAT
Reply in Markdown, structured as follows:
- Open with a direct one or two sentence answer. No preamble, no restating the question.
- Then the supporting detail, using whichever of these fits:
  - `## Heading` to separate distinct aspects, only when there is more than one.
  - Bullet points for conditions, criteria, steps or exceptions.
  - A Markdown table when comparing options, tiers, limits or timelines.
- Bold every number that matters: amounts, rates, percentages, thresholds, deadlines, day counts.
- Use `inline code` for exact field names, identifiers, codes and document names.
- Finish with a short `## Note` only when there is a caveat, exception or condition the reader would otherwise miss.

STYLE
- Be precise and brief. No filler, no apologies, no "based on the context provided".
- Prefer the specific figure over a paraphrase: write **7.10 percent** rather than "a competitive rate".
- Keep to the question asked. Do not volunteer adjacent information."""

# Filenames are turned into readable titles for display. Words that should stay
# upper case when a title is capitalised.
_ACRONYMS = {
    "kyc": "KYC",
    "aml": "AML",
    "upi": "UPI",
    "neft": "NEFT",
    "rtgs": "RTGS",
    "imps": "IMPS",
    "api": "API",
    "sla": "SLA",
    "faq": "FAQ",
    "id": "ID",
}
_EXTENSIONS = re.compile(r"\.(md|markdown|txt|pdf)$", re.IGNORECASE)
_LEADING_ORDINAL = re.compile(r"^\d+\s*[-_.]*\s*")


def document_title(doc_id: str, source: str = "") -> str:
    """Turn a storage key into something worth showing a reader.

    ``uploads/05-fraud-and-disputes.md`` becomes ``Fraud And Disputes``.

    Display titles also keep bucket names and key layout out of the API
    response, so the storage arrangement is not published to every caller.
    """
    raw = (doc_id or source or "").split("?")[0].rstrip("/")
    name = raw.rsplit("/", 1)[-1]
    name = _EXTENSIONS.sub("", name)
    name = _LEADING_ORDINAL.sub("", name)
    name = name.replace("-", " ").replace("_", " ").strip()

    if not name:
        return "Untitled document"

    return " ".join(_ACRONYMS.get(word.lower(), word.capitalize()) for word in name.split())


@dataclass
class Answer:
    answer: str
    citations: list[dict] = field(default_factory=list)
    model_id: str = CHAT_MODEL_ID


def _runtime():
    return boto3.client(
        "bedrock-runtime",
        region_name=AWS_REGION,
        config=Config(retries={"max_attempts": 3, "mode": "standard"}),
    )


def build_context(hits: list[Hit], max_chars: int = MAX_CONTEXT_CHARS) -> tuple[str, list[dict]]:
    """Render numbered context blocks, truncated to a character budget.

    Blocks are labelled with the readable title rather than the storage key, so
    the model never has a bucket path available to quote into an answer.
    """
    blocks: list[str] = []
    citations: list[dict] = []
    used = 0
    for i, hit in enumerate(hits, start=1):
        title = document_title(hit.doc_id, hit.source)
        block = f"[{i}] {title}\n{hit.text}"
        # Count the separator join() will insert, or the rendered context can
        # exceed max_chars by two characters per block.
        cost = len(block) + (2 if blocks else 0)
        if used + cost > max_chars:
            break
        blocks.append(block)
        citations.append({"marker": i, "title": title, "score": round(hit.score, 4)})
        used += cost
    return "\n\n".join(blocks), citations


def build_prompt(question: str, context: str) -> str:
    return (
        f"<context>\n{context or 'No context retrieved.'}\n</context>\n\n"
        f"Question: {question}"
    )


def generate(prompt: str, client=None, model_id: str = CHAT_MODEL_ID) -> str:
    """Call Bedrock through the Converse API.

    Converse normalizes the request and response shape across providers, so
    swapping Nova for Claude, Llama, or Mistral needs no code change.
    """
    client = client or _runtime()
    response = client.converse(
        modelId=model_id,
        system=[{"text": SYSTEM_PROMPT}],
        messages=[{"role": "user", "content": [{"text": prompt}]}],
        inferenceConfig={"maxTokens": MAX_TOKENS, "temperature": 0.0},
    )
    parts = [b.get("text", "") for b in response["output"]["message"]["content"] if "text" in b]
    return "".join(parts).strip()


def answer_question(
    question: str,
    k: int = 5,
    search_fn=hybrid_search,
    llm_client=None,
    model_id: str = CHAT_MODEL_ID,
    **search_kwargs,
) -> Answer:
    """End-to-end RAG call. ``search_fn`` and ``llm_client`` are injectable for tests."""
    question = (question or "").strip()
    if not question:
        raise ValueError("question must not be empty")

    hits = search_fn(question, k=k, **search_kwargs)
    if not hits:
        return Answer(answer="I could not find anything relevant in the indexed documents.", model_id=model_id)

    context, citations = build_context(hits)
    text = generate(build_prompt(question, context), client=llm_client, model_id=model_id)
    return Answer(answer=text, citations=citations, model_id=model_id)
