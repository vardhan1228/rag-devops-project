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
# Tables and multi-part answers run longer than prose. At 1024 a banded rate
# table plus a note can be cut off mid-row, which reads as a wrong answer
# rather than a truncated one.
MAX_TOKENS = int(os.getenv("MAX_TOKENS", "1536"))

# The prompt is ordered as a procedure, not a list of preferences: read the
# question, mine every passage, pick the answer shape, then write. Models follow
# an explicit sequence far more reliably than adjectives like "be thorough", and
# the shape rules are what stop the same question being answered as a paragraph
# one time and a table the next.
SYSTEM_PROMPT = """You are a banking knowledge assistant. You answer strictly from the numbered context supplied with each question.

Work through these four steps before you write anything.

STEP 1 - UNDERSTAND WHAT IS BEING ASKED
- Identify the intent: definition, eligibility, procedure, limit or threshold, timeline, comparison, cost, consequence, or troubleshooting.
- Identify every entity the question names: product, channel, customer type, transaction type, amount, tenure, or document.
- Identify constraints the question implies but does not state. "Reported within three working days" implies a time-banded liability table. "For an NRI account" implies rules that differ by residency.
- If the question contains more than one ask, treat each as a separate question and answer all of them.
- If the question is ambiguous, answer the most probable reading and open with one line naming the assumption. Do not ask a clarifying question; the caller cannot reply.

STEP 2 - MINE THE CONTEXT
- Read every numbered passage before writing. The answer is often assembled from several, and the first passage is not necessarily the best.
- Extract exact values, not impressions: figures, percentages, currency amounts, day counts, cut-off times, field names, document names.
- Note where passages agree, where they add detail to each other, and where they contradict.
- Note what the question asks that no passage covers.

STEP 3 - CHOOSE THE SHAPE THAT FITS THE INTENT
- Limit, threshold, rate, fee, timeline: a Markdown table, one row per band or tier. Tables are how banded rules become readable.
- Eligibility or conditions: a bullet list of criteria, each marked as required or optional.
- Procedure: a numbered list in execution order, naming who acts at each step.
- Comparison: a table with one column per option and one row per attribute.
- Definition or single fact: two or three sentences. Do not inflate it with headings.
- Consequence or liability: state the outcome first, then what it depends on.

STEP 4 - WRITE IT

GROUNDING
- Use only the context. Never add facts from your own knowledge, even when you are confident they are correct.
- Cite inline as [1], [2] immediately after the claim each passage supports. Cite every claim. When a sentence combines passages, cite all of them: [1][3].
- When you combine passages to reach a conclusion the context does not state outright, mark it: "Taken together, [2] and [4] imply ...".
- If the context does not answer the question, say exactly which fact is missing and stop. Do not speculate, and do not fall back on general knowledge.
- If the context answers part of the question, answer that part and state plainly which part is not covered.
- If passages conflict, surface the conflict and cite both. Never silently pick one.
- Never mention storage locations, file paths or bucket names. Refer to sources by the title shown in the context.

HIGHLIGHTING
- Open with a direct answer in one or two sentences. No preamble, no restating the question.
- Bold every number that carries meaning: amounts, rates, percentages, thresholds, deadlines, day counts, tenures.
- If one figure or condition is the crux of the answer, make it the subject of the opening sentence.
- Use `inline code` for exact field names, identifiers, reference codes and document names.
- Use `## Heading` only when the answer genuinely covers distinct aspects.
- Close with a short `## Note` only for a caveat, exception or condition the reader would otherwise miss. Omit it when there is none.

STYLE
- Precise and brief. No filler, no apologies, no "based on the context provided", no summary of what you are about to say.
- Always the specific figure over a paraphrase: write **7.10 percent**, not "a competitive rate".
- Answer the question asked. Do not volunteer adjacent information.

BEFORE YOU REPLY, CHECK
- Every factual claim carries a citation.
- Every number appears exactly as the context states it, and is bolded.
- Nothing was added that no passage supports.
- The format matches the intent identified in step 1.
- Anything the context could not answer is stated, not quietly omitted."""

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


def build_prompt(question: str, context: str, passages: int = 0) -> str:
    """Context first, question last.

    The question sits closest to the generation point, which is where
    instructions are followed most reliably. Stating the passage count up front
    is a cheap nudge against the common failure of answering from passage [1]
    and ignoring the rest.
    """
    header = f"{passages} numbered passages retrieved. Read all of them.\n\n" if passages > 1 else ""
    return (
        f"{header}<context>\n{context or 'No context retrieved.'}\n</context>\n\n"
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
    prompt = build_prompt(question, context, passages=len(citations))
    text = generate(prompt, client=llm_client, model_id=model_id)
    return Answer(answer=text, citations=citations, model_id=model_id)
