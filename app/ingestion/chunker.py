"""Split documents into overlapping chunks suitable for embedding."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterator, Sequence

DEFAULT_CHUNK_SIZE = 1000
DEFAULT_OVERLAP = 150

# Split on paragraph breaks first, then sentences, then whitespace.
_PARAGRAPH_RE = re.compile(r"\n\s*\n")
_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")


@dataclass
class Chunk:
    doc_id: str
    index: int
    text: str
    source: str = ""
    metadata: dict = field(default_factory=dict)

    @property
    def id(self) -> str:
        return f"{self.doc_id}::{self.index}"


def normalize(text: str) -> str:
    """Collapse runaway whitespace while preserving paragraph breaks."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _split_units(text: str) -> list[str]:
    units: list[str] = []
    for paragraph in _PARAGRAPH_RE.split(text):
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        units.extend(s for s in _SENTENCE_RE.split(paragraph) if s)
    return units


def _hard_split(unit: str, size: int) -> list[str]:
    return [unit[i : i + size] for i in range(0, len(unit), size)]


def split_text(
    text: str,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_OVERLAP,
) -> list[str]:
    """Greedily pack sentences into ``chunk_size`` windows with character overlap."""
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    if not 0 <= overlap < chunk_size:
        raise ValueError("overlap must be >= 0 and < chunk_size")

    text = normalize(text)
    if not text:
        return []

    units: list[str] = []
    for unit in _split_units(text):
        units.extend(_hard_split(unit, chunk_size) if len(unit) > chunk_size else [unit])

    chunks: list[str] = []
    current = ""
    for unit in units:
        candidate = f"{current} {unit}".strip() if current else unit
        if len(candidate) <= chunk_size:
            current = candidate
            continue
        if current:
            chunks.append(current)
            tail = current[-overlap:] if overlap else ""
            current = f"{tail} {unit}".strip() if tail else unit
        else:
            current = unit
    if current:
        chunks.append(current)
    return chunks


def chunk_documents(
    documents: Sequence[dict] | Iterator[dict],
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_OVERLAP,
) -> list[Chunk]:
    """Flatten an iterable of Document dicts into Chunk objects."""
    chunks: list[Chunk] = []
    for doc in documents:
        doc = doc if isinstance(doc, dict) else doc.to_dict()
        for i, piece in enumerate(split_text(doc["text"], chunk_size, overlap)):
            chunks.append(
                Chunk(
                    doc_id=doc["id"],
                    index=i,
                    text=piece,
                    source=doc.get("source", ""),
                    metadata=dict(doc.get("metadata") or {}),
                )
            )
    return chunks
