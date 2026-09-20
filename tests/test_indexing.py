"""Index lifecycle tests: creation under concurrency, deletion, full reindex."""

import pytest
from opensearchpy.exceptions import TransportError

from app.ingestion import indexer
from app.ingestion.chunker import Chunk


class FakeIndices:
    """Tracks index state and can simulate a losing race on create."""

    def __init__(self, existing=(), create_raises=None):
        self.existing = set(existing)
        self.create_raises = create_raises
        self.created: list[str] = []
        self.deleted: list[str] = []

    def exists(self, index):
        return index in self.existing

    def create(self, index, body=None):
        self.created.append(index)
        if self.create_raises is not None:
            raise self.create_raises
        self.existing.add(index)

    def delete(self, index):
        self.deleted.append(index)
        self.existing.discard(index)


class FakeClient:
    def __init__(self, indices):
        self.indices = indices


def already_exists_error():
    """Shape of the 400 OpenSearch returns when another writer won the race."""
    return TransportError(
        400,
        "resource_already_exists_exception",
        {"error": {"type": "resource_already_exists_exception"}},
    )


# ------------------------------------------------------------- ensure_index
def test_creates_index_when_absent():
    idx = FakeIndices()
    assert indexer.ensure_index(FakeClient(idx), "rag-chunks") is True
    assert idx.created == ["rag-chunks"]


def test_skips_creation_when_present():
    idx = FakeIndices(existing=["rag-chunks"])
    assert indexer.ensure_index(FakeClient(idx), "rag-chunks") is False
    assert idx.created == []


def test_losing_a_concurrent_create_race_is_not_an_error():
    """Several ingest invocations start together; only one create can win.

    The losers must carry on and index their passages rather than crashing,
    which is what produced resource_already_exists_exception in production.
    """
    idx = FakeIndices(create_raises=already_exists_error())
    assert indexer.ensure_index(FakeClient(idx), "rag-chunks") is False


def test_other_transport_errors_still_raise():
    idx = FakeIndices(create_raises=TransportError(403, "security_exception", {}))
    with pytest.raises(TransportError):
        indexer.ensure_index(FakeClient(idx), "rag-chunks")


@pytest.mark.parametrize(
    "exc,expected",
    [
        (already_exists_error(), True),
        (TransportError(400, "mapper_parsing_exception", {}), False),
        (TransportError(404, "index_not_found_exception", {}), False),
        (TransportError(403, "resource_already_exists_exception", {}), False),
    ],
)
def test_already_exists_detection(exc, expected):
    assert indexer._is_already_exists(exc) is expected


# ------------------------------------------------------------- delete_index
def test_delete_index_reports_whether_it_existed():
    idx = FakeIndices(existing=["rag-chunks"])
    assert indexer.delete_index(FakeClient(idx), "rag-chunks") is True
    assert idx.deleted == ["rag-chunks"]

    assert indexer.delete_index(FakeClient(idx), "rag-chunks") is False


# ----------------------------------------------------------- reindex_prefix
def test_reindex_drops_then_rebuilds(monkeypatch):
    """Dropping first is the point: it removes passages whose source is gone."""
    idx = FakeIndices(existing=["rag-chunks"])
    client = FakeClient(idx)

    docs = [
        {"id": "uploads/a.md", "source": "s3://b/uploads/a.md", "text": "one. two.", "metadata": {}},
        {"id": "uploads/b.md", "source": "s3://b/uploads/b.md", "text": "three.", "metadata": {}},
    ]

    class Doc:
        def __init__(self, d):
            self._d = d

        def to_dict(self):
            return self._d

    monkeypatch.setattr("app.ingestion.loader.load_s3", lambda b, p: [Doc(d) for d in docs])

    captured = {}

    def fake_index_chunks(chunks, client=None, embedder=None, index=None):
        captured["chunks"] = chunks
        return {"indexed": len(chunks), "failed": 0, "index": index, "errors": []}

    monkeypatch.setattr(indexer, "index_chunks", fake_index_chunks)

    result = indexer.reindex_prefix("bucket", "uploads/", client=client, embedder=object())

    assert idx.deleted == ["rag-chunks"]
    assert idx.created == ["rag-chunks"]
    assert result["dropped_existing_index"] is True
    assert result["documents"] == 2
    assert result["sources"] == ["uploads/a.md", "uploads/b.md"]
    assert result["indexed"] == len(captured["chunks"])
    assert all(isinstance(c, Chunk) for c in captured["chunks"])


# ----------------------------------------------------------- lambda_handler
def test_handler_routes_reindex_events(monkeypatch):
    monkeypatch.setattr(
        indexer, "reindex_prefix", lambda bucket, prefix: {"mode": "reindex", "bucket": bucket, "prefix": prefix}
    )
    out = indexer.lambda_handler({"reindex": True, "bucket": "b", "prefix": "uploads/"})
    assert out["statusCode"] == 200
    assert out["bucket"] == "b"


def test_reindex_falls_back_to_the_bucket_env_var(monkeypatch):
    monkeypatch.setenv("DOCUMENTS_BUCKET", "from-env")
    monkeypatch.setattr(indexer, "reindex_prefix", lambda bucket, prefix: {"bucket": bucket})
    assert indexer.lambda_handler({"reindex": True})["bucket"] == "from-env"


def test_reindex_without_a_bucket_is_rejected(monkeypatch):
    monkeypatch.delenv("DOCUMENTS_BUCKET", raising=False)
    with pytest.raises(ValueError, match="needs a bucket"):
        indexer.lambda_handler({"reindex": True})


def test_handler_still_processes_s3_notifications(monkeypatch):
    seen = []

    class Doc:
        def to_dict(self):
            return {"id": "k", "source": "s", "text": "hello.", "metadata": {}}

    monkeypatch.setattr("app.ingestion.loader.load_s3", lambda b, k: [Doc()])
    monkeypatch.setattr(
        indexer, "index_chunks", lambda chunks: seen.append(chunks) or {"indexed": 1, "failed": 0}
    )

    event = {"Records": [{"s3": {"bucket": {"name": "b"}, "object": {"key": "uploads/k.md"}}}]}
    out = indexer.lambda_handler(event)

    assert out["processed"] == 1
    assert out["results"][0]["key"] == "uploads/k.md"
    assert len(seen) == 1
