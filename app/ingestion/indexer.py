"""OpenSearch vector index management and bulk upsert."""

from __future__ import annotations

import os
from typing import Iterable, Sequence

import boto3
from opensearchpy import OpenSearch, RequestsHttpConnection, helpers
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
    """Create the index if missing. Returns True when it was created."""
    if client.indices.exists(index=index):
        return False
    client.indices.create(index=index, body=INDEX_BODY)
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


def lambda_handler(event: dict, context=None) -> dict:
    """S3-event entrypoint: load -> chunk -> embed -> index each new object."""
    from app.ingestion.chunker import chunk_documents
    from app.ingestion.loader import load_s3

    results = []
    for record in event.get("Records", []):
        bucket = record["s3"]["bucket"]["name"]
        key = record["s3"]["object"]["key"]
        docs = [d.to_dict() for d in load_s3(bucket, key)]
        summary = index_chunks(chunk_documents(docs))
        results.append({"key": key, **summary})
    return {"statusCode": 200, "processed": len(results), "results": results}
