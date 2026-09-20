"""Retrieval-augmented generation: retrieve context, then call an LLM."""

from __future__ import annotations

import os
from dataclasses import dataclass, field

import boto3
from botocore.config import Config

from app.retrieval.search import Hit, hybrid_search

CHAT_MODEL_ID = os.getenv("CHAT_MODEL_ID", "amazon.nova-lite-v1:0")
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
MAX_CONTEXT_CHARS = int(os.getenv("MAX_CONTEXT_CHARS", "12000"))
MAX_TOKENS = int(os.getenv("MAX_TOKENS", "1024"))

SYSTEM_PROMPT = (
    "You answer questions using only the provided context. "
    "Cite the sources you used as [1], [2], and so on. "
    "If the context does not contain the answer, say so plainly instead of guessing."
)


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
    """Render numbered context blocks, truncated to a character budget."""
    blocks: list[str] = []
    citations: list[dict] = []
    used = 0
    for i, hit in enumerate(hits, start=1):
        block = f"[{i}] source: {hit.source or hit.doc_id}\n{hit.text}"
        if used + len(block) > max_chars:
            break
        blocks.append(block)
        citations.append(
            {"marker": i, "doc_id": hit.doc_id, "source": hit.source, "score": round(hit.score, 4)}
        )
        used += len(block)
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
