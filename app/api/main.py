"""FastAPI surface for the RAG service.

Endpoints
    GET  /              web UI (static, no credentials in the assets)
    GET  /health        liveness probe, for the load balancer
    GET  /ready         checks the OpenSearch index is reachable
    POST /ingest        load + chunk + embed + index a source
    POST /query         retrieval-augmented answer

Two unrelated kinds of authentication are involved here, and conflating them is
a common mistake:

1. The service to AWS. Bedrock, S3 and OpenSearch calls are signed with the
   task role's temporary credentials, handled by boto3. Nothing to configure.

2. The caller to this service. Controlled by REQUIRE_AUTH. When true, /query
   and /ingest need an `x-api-key` header matching API_KEY, and the service
   refuses to start if API_KEY is missing so it cannot fail open. When false
   every route is public, which means anyone who can reach the load balancer can
   read the indexed corpus and spend Bedrock tokens on this account. Only run
   that way behind a restricted network path.
"""

from __future__ import annotations

import hmac
import logging
import os
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, status
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.ingestion.chunker import chunk_documents
from app.ingestion.indexer import OPENSEARCH_INDEX, get_client, index_chunks
from app.ingestion.loader import load
from app.retrieval.rag import answer_question
from app.retrieval.search import hybrid_search, vector_search

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

API_KEY = os.getenv("API_KEY", "")
REQUIRE_AUTH = os.getenv("REQUIRE_AUTH", "true").lower() != "false"
STATIC_DIR = Path(__file__).parent / "static"

if REQUIRE_AUTH and not API_KEY:
    raise RuntimeError(
        "API_KEY is not set. Set API_KEY (recommended: inject from Secrets Manager) "
        "or explicitly set REQUIRE_AUTH=false for local development only."
    )

app = FastAPI(title="RAG DevOps API", version="1.1.0")


def require_api_key(x_api_key: str = Header(default="")) -> None:
    if not REQUIRE_AUTH:
        return
    if not hmac.compare_digest(x_api_key, API_KEY):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid api key")


class IngestRequest(BaseModel):
    source: str = Field(..., description="Local path or s3://bucket/prefix")
    chunk_size: int = Field(1000, ge=100, le=8000)
    overlap: int = Field(150, ge=0, le=2000)


class IngestResponse(BaseModel):
    source: str
    documents: int
    chunks: int
    indexed: int
    failed: int
    index: str


class QueryRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    k: int = Field(5, ge=1, le=20)
    mode: str = Field("hybrid", pattern="^(hybrid|vector)$")


class Citation(BaseModel):
    marker: int
    title: str
    score: float


class QueryResponse(BaseModel):
    question: str
    answer: str
    citations: list[Citation] = []
    model_id: str


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/ready", dependencies=[Depends(require_api_key)])
def ready() -> dict:
    try:
        exists = get_client().indices.exists(index=OPENSEARCH_INDEX)
    except Exception as exc:  # noqa: BLE001 - surfaced as 503 below
        logger.warning("readiness check failed: %s", exc)
        raise HTTPException(status_code=503, detail="search backend unavailable") from exc
    return {"status": "ok", "index": OPENSEARCH_INDEX, "index_exists": exists}


@app.post("/ingest", response_model=IngestResponse, dependencies=[Depends(require_api_key)])
def ingest(req: IngestRequest) -> IngestResponse:
    try:
        docs = [d.to_dict() for d in load(req.source)]
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    chunks = chunk_documents(docs, chunk_size=req.chunk_size, overlap=req.overlap)
    summary = index_chunks(chunks)
    logger.info("ingested source=%s docs=%d chunks=%d", req.source, len(docs), len(chunks))
    return IngestResponse(
        source=req.source,
        documents=len(docs),
        chunks=len(chunks),
        indexed=summary.get("indexed", 0),
        failed=summary.get("failed", 0),
        index=summary.get("index", OPENSEARCH_INDEX),
    )


@app.post("/query", response_model=QueryResponse, dependencies=[Depends(require_api_key)])
def query(req: QueryRequest) -> QueryResponse:
    search_fn = hybrid_search if req.mode == "hybrid" else vector_search
    result = answer_question(req.question, k=req.k, search_fn=search_fn)
    return QueryResponse(
        question=req.question,
        answer=result.answer,
        citations=[Citation(**c) for c in result.citations],
        model_id=result.model_id,
    )


# ------------------------------------------------------------------- web UI
# Mounted last so it cannot shadow the API routes above. The assets are public
# because they hold no credentials; the user supplies the API key at runtime.
if STATIC_DIR.is_dir():

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
else:  # pragma: no cover - only hit in a malformed image
    logger.warning("static directory %s is missing; web UI disabled", STATIC_DIR)
