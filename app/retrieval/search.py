"""Vector, keyword, and hybrid search over the OpenSearch chunk index."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from opensearchpy import OpenSearch

from app.ingestion.embeddings import Embedder, get_embedder
from app.ingestion.indexer import OPENSEARCH_INDEX, get_client

_SOURCE_FIELDS = ["doc_id", "chunk_index", "text", "source"]


@dataclass
class Hit:
    id: str
    score: float
    text: str
    doc_id: str
    source: str

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> "Hit":
        src = raw.get("_source", {})
        return cls(
            id=raw.get("_id", ""),
            score=float(raw.get("_score", 0.0)),
            text=src.get("text", ""),
            doc_id=src.get("doc_id", ""),
            source=src.get("source", ""),
        )


def build_knn_query(vector: list[float], k: int, doc_id: str | None = None) -> dict:
    knn: dict[str, Any] = {"vector": {"vector": vector, "k": k}}
    query: dict[str, Any] = {"size": k, "_source": _SOURCE_FIELDS, "query": {"knn": knn}}
    if doc_id:
        query["query"] = {
            "bool": {"must": [{"knn": knn}], "filter": [{"term": {"doc_id": doc_id}}]}
        }
    return query


def vector_search(
    query: str,
    k: int = 5,
    doc_id: str | None = None,
    client: OpenSearch | None = None,
    embedder: Embedder | None = None,
    index: str = OPENSEARCH_INDEX,
) -> list[Hit]:
    client = client or get_client()
    embedder = embedder or get_embedder()
    vector = embedder.embed_text(query)
    body = build_knn_query(vector, k, doc_id)
    response = client.search(index=index, body=body)
    return [Hit.from_raw(h) for h in response.get("hits", {}).get("hits", [])]


def keyword_search(
    query: str,
    k: int = 5,
    client: OpenSearch | None = None,
    index: str = OPENSEARCH_INDEX,
) -> list[Hit]:
    client = client or get_client()
    body = {"size": k, "_source": _SOURCE_FIELDS, "query": {"match": {"text": query}}}
    response = client.search(index=index, body=body)
    return [Hit.from_raw(h) for h in response.get("hits", {}).get("hits", [])]


def reciprocal_rank_fusion(*result_sets: list[Hit], k: int = 5, smoothing: int = 60) -> list[Hit]:
    """Merge ranked lists with RRF, which needs no score normalization."""
    scores: dict[str, float] = {}
    seen: dict[str, Hit] = {}
    for results in result_sets:
        for rank, hit in enumerate(results, start=1):
            scores[hit.id] = scores.get(hit.id, 0.0) + 1.0 / (smoothing + rank)
            seen.setdefault(hit.id, hit)
    ordered = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)[:k]
    merged = []
    for hit_id, score in ordered:
        hit = seen[hit_id]
        merged.append(Hit(id=hit.id, score=score, text=hit.text, doc_id=hit.doc_id, source=hit.source))
    return merged


def hybrid_search(
    query: str,
    k: int = 5,
    client: OpenSearch | None = None,
    embedder: Embedder | None = None,
    index: str = OPENSEARCH_INDEX,
) -> list[Hit]:
    client = client or get_client()
    dense = vector_search(query, k=k * 2, client=client, embedder=embedder, index=index)
    sparse = keyword_search(query, k=k * 2, client=client, index=index)
    return reciprocal_rank_fusion(dense, sparse, k=k)
