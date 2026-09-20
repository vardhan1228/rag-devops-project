"""OpenSearch vector index management and bulk upsert."""

from __future__ import annotations

import os
from typing import Iterable, Sequence

import boto3
from opensearchpy import OpenSearch, RequestsHttpConnection, helpers
from opensearchpy.exceptions import TransportError
from requests_aws4auth import AWS4Auth

from app.ingestion.chunker import Chunk
from app.ingestion.embeddings import EMBED_DIMENSION, Embedder, get_embedder

OPENSEARCH_ENDPOINT = os.getenv("OPENSEARCH_ENDPOINT", "")
OPENSEARCH_INDEX = os.getenv("OPENSEARCH_INDEX", "rag-chunks")
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
SERVICE = os.getenv("OPENSEARCH_SERVICE", "es")  # "aoss" for Serverless collections

INDEX_BODY = {
    "settings": {"index": {"knn": True, "number_of_shards": 1, "number_of_replicas": 1}},
    "mappings": {
        "properties": {
            "vector": {
                "type": "knn_vector",
                "dimension": EMBED_DIMENSION,
                "method": {"name": "hnsw", "space_type": "cosinesimil", "engine": "nmslib"},
            },
            "text": {"type": "text"},
            "doc_id": {"type": "keyword"},
            "chunk_index": {"type": "integer"},
            "source": {"type": "keyword"},
        }
    },
}


def get_client(endpoint: str | None = None) -> OpenSearch:
    """Build a SigV4-signed OpenSearch client from the ambient AWS credentials."""
    host = (endpoint or OPENSEARCH_ENDPOINT).replace("https://", "").rstrip("/")
    if not host:
        raise RuntimeError("OPENSEARCH_ENDPOINT is not set")
    creds = boto3.Session().get_credentials()
    if creds is None:
        raise RuntimeError("no AWS credentials available for OpenSearch signing")
    creds = creds.get_frozen_credentials()
    auth = AWS4Auth(
        creds.access_key,
        creds.secret_key,
        AWS_REGION,
        SERVICE,
        session_token=creds.token,
    )
    return OpenSearch(
        hosts=[{"host": host, "port": 443}],
        http_auth=auth,
        use_ssl=True,
        verify_certs=True,
        connection_class=RequestsHttpConnection,
        pool_maxsize=20,
        timeout=30,
    )


def ensure_index(client: OpenSearch, index: str = OPENSEARCH_INDEX) -> bool:
    """Create the index if missing. Returns True when this call created it.

    Check-then-create is not atomic. When several ingest invocations start at
    once they all see the index as absent, all call create, one wins and the
    rest get a 400 resource_already_exists_exception. Treating that response as
    success makes concurrent ingestion safe instead of relying on retries.
    """
    if client.indices.exists(index=index):
        return False
    try:
        client.indices.create(index=index, body=INDEX_BODY)
        return True
    except TransportError as exc:
        if _is_already_exists(exc):
            return False
        raise


def _is_already_exists(exc: TransportError) -> bool:
    """True when OpenSearch rejected a create because the index is already there."""
    if getattr(exc, "status_code", None) != 400:
        return False
    return "resource_already_exists_exception" in str(getattr(exc, "error", "")) or (
        "resource_already_exists_exception" in str(exc)
    )


def delete_index(client: OpenSearch, index: str = OPENSEARCH_INDEX) -> bool:
    """Drop the index. Returns True if it existed. Used before a full reindex."""
    if not client.indices.exists(index=index):
        return False
    client.indices.delete(index=index)
    return True


def to_actions(chunks: Sequence[Chunk], vectors: Sequence[Sequence[float]], index: str) -> Iterable[dict]:
    if len(chunks) != len(vectors):
        raise ValueError("chunks and vectors must be the same length")
    for chunk, vector in zip(chunks, vectors):
        yield {
            "_op_type": "index",
            "_index": index,
            "_id": chunk.id,
            "_source": {
                "doc_id": chunk.doc_id,
                "chunk_index": chunk.index,
                "text": chunk.text,
                "source": chunk.source,
                "vector": list(vector),
                **chunk.metadata,
            },
        }


def index_chunks(
    chunks: Sequence[Chunk],
    client: OpenSearch | None = None,
    embedder: Embedder | None = None,
    index: str = OPENSEARCH_INDEX,
) -> dict:
    """Embed and upsert chunks. Returns a small ingest summary."""
    if not chunks:
        return {"indexed": 0, "failed": 0, "index": index}

    client = client or get_client()
    embedder = embedder or get_embedder()
    ensure_index(client, index)

    vectors = embedder.embed_batch([c.text for c in chunks])
    success, errors = helpers.bulk(
        client,
        to_actions(chunks, vectors, index),
        raise_on_error=False,
        refresh=True,
    )
    return {"indexed": success, "failed": len(errors), "index": index, "errors": errors[:5]}


def reindex_prefix(
    bucket: str,
    prefix: str = "uploads/",
    client: OpenSearch | None = None,
    embedder: Embedder | None = None,
    index: str = OPENSEARCH_INDEX,
) -> dict:
    """Rebuild the index from scratch for everything under ``prefix``.

    Needed because deleting an object from S3 does not remove its passages from
    the index. Without a rebuild, a replaced corpus leaves the old passages
    behind and they keep turning up in results.

    Runs as a single call, so it also avoids the concurrent-create contention
    that per-object invocations produce.
    """
    from app.ingestion.chunker import chunk_documents
    from app.ingestion.loader import load_s3

    client = client or get_client()
    embedder = embedder or get_embedder()

    dropped = delete_index(client, index)
    ensure_index(client, index)

    docs = [d.to_dict() for d in load_s3(bucket, prefix)]
    chunks = chunk_documents(docs)
    summary = index_chunks(chunks, client=client, embedder=embedder, index=index)

    return {
        "mode": "reindex",
        "dropped_existing_index": dropped,
        "documents": len(docs),
        "sources": sorted({d["id"] for d in docs}),
        **summary,
    }


def lambda_handler(event: dict, context=None) -> dict:
    """Ingest entrypoint, with two shapes.

    S3 notification (automatic): indexes each newly created object.

    Manual reindex: ``{"reindex": true, "bucket": "...", "prefix": "uploads/"}``
    drops the index and rebuilds it from the bucket, so the index matches the
    corpus exactly. Use this after replacing or deleting source documents.
    """
    from app.ingestion.chunker import chunk_documents
    from app.ingestion.loader import load_s3

    if event.get("reindex"):
        bucket = event.get("bucket") or os.getenv("DOCUMENTS_BUCKET", "")
        if not bucket:
            raise ValueError("reindex needs a bucket, in the event or DOCUMENTS_BUCKET")
        return {"statusCode": 200, **reindex_prefix(bucket, event.get("prefix", "uploads/"))}

    results = []
    for record in event.get("Records", []):
        bucket = record["s3"]["bucket"]["name"]
        key = record["s3"]["object"]["key"]
        docs = [d.to_dict() for d in load_s3(bucket, key)]
        summary = index_chunks(chunk_documents(docs))
        results.append({"key": key, **summary})
    return {"statusCode": 200, "processed": len(results), "results": results}
