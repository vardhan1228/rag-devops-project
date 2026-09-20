"""Route and auth tests for the FastAPI app.

Skipped when FastAPI is not installed locally; CI installs the full
requirements.txt and runs them.
"""

import importlib
import os

import pytest

pytest.importorskip("fastapi", reason="fastapi not installed in this environment")

from fastapi.testclient import TestClient  # noqa: E402

API_KEY = "test-key-1234567890"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("API_KEY", API_KEY)
    monkeypatch.setenv("REQUIRE_AUTH", "true")

    import app.api.main as main

    importlib.reload(main)
    return TestClient(main.app), main


def test_health_is_public(client):
    c, _ = client
    res = c.get("/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}


def test_web_ui_is_served_at_root(client):
    c, _ = client
    res = c.get("/")
    assert res.status_code == 200
    assert "text/html" in res.headers["content-type"]
    assert "RAG Console" in res.text


def test_ui_does_not_leak_the_api_key(client):
    c, _ = client
    assert API_KEY not in c.get("/").text


@pytest.mark.parametrize("path", ["/query", "/ingest"])
def test_write_routes_require_the_key(client, path):
    c, _ = client
    assert c.post(path, json={"question": "hi", "source": "s3://b/k"}).status_code == 401
    assert c.post(
        path, json={"question": "hi", "source": "s3://b/k"}, headers={"x-api-key": "wrong"}
    ).status_code == 401


def test_query_returns_answer_and_citations(client, monkeypatch):
    c, main = client
    from app.retrieval.rag import Answer

    def fake_answer(question, k, search_fn):
        assert question == "why?"
        return Answer(
            answer="42",
            citations=[{"marker": 1, "doc_id": "d", "source": "s", "score": 0.5}],
            model_id="amazon.nova-lite-v1:0",
        )

    monkeypatch.setattr(main, "answer_question", fake_answer)

    res = c.post("/query", json={"question": "why?"}, headers={"x-api-key": API_KEY})
    assert res.status_code == 200
    body = res.json()
    assert body["answer"] == "42"
    assert body["citations"][0]["doc_id"] == "d"
    assert body["model_id"] == "amazon.nova-lite-v1:0"


def test_startup_fails_without_a_key(monkeypatch):
    monkeypatch.delenv("API_KEY", raising=False)
    monkeypatch.setenv("REQUIRE_AUTH", "true")

    import app.api.main as main

    with pytest.raises(RuntimeError, match="API_KEY is not set"):
        importlib.reload(main)

    # Restore a usable module state for any later tests.
    monkeypatch.setenv("API_KEY", API_KEY)
    importlib.reload(main)


def test_invalid_query_payload_is_rejected(client):
    c, _ = client
    res = c.post("/query", json={"question": ""}, headers={"x-api-key": API_KEY})
    assert res.status_code == 422
    res = c.post("/query", json={"question": "ok", "mode": "nope"}, headers={"x-api-key": API_KEY})
    assert res.status_code == 422


def test_environment_is_not_echoed(client):
    c, _ = client
    assert os.getenv("API_KEY") == API_KEY
    assert API_KEY not in c.get("/health").text
