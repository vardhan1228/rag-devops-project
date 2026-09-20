"""Route and auth tests for the FastAPI app.

Skipped when FastAPI is not installed locally; CI installs the full
requirements.txt and runs them.
"""

import importlib

import pytest

pytest.importorskip("fastapi", reason="fastapi not installed in this environment")

from fastapi.testclient import TestClient  # noqa: E402

API_KEY = "test-key-1234567890"


def _load(monkeypatch, *, require_auth: bool, api_key: str | None = API_KEY):
    """Reload the app module under a given auth configuration."""
    monkeypatch.setenv("REQUIRE_AUTH", "true" if require_auth else "false")
    if api_key is None:
        monkeypatch.delenv("API_KEY", raising=False)
    else:
        monkeypatch.setenv("API_KEY", api_key)

    import app.api.main as main

    importlib.reload(main)
    return TestClient(main.app), main


@pytest.fixture
def open_client(monkeypatch):
    """Default deployment shape: caller auth disabled."""
    return _load(monkeypatch, require_auth=False, api_key=None)


@pytest.fixture
def secured_client(monkeypatch):
    return _load(monkeypatch, require_auth=True)


def _fake_answer(main, monkeypatch):
    from app.retrieval.rag import Answer

    monkeypatch.setattr(
        main,
        "answer_question",
        lambda question, k, search_fn: Answer(
            answer="Sentences are packed into a 1000 character window. [1]",
            citations=[{"marker": 1, "doc_id": "d", "source": "s", "score": 0.5}],
            model_id="amazon.nova-lite-v1:0",
        ),
    )


# ------------------------------------------------------------------- public
def test_health_is_public(open_client):
    c, _ = open_client
    assert c.get("/health").json() == {"status": "ok"}


def test_web_ui_is_served_at_root(open_client):
    c, _ = open_client
    res = c.get("/")
    assert res.status_code == 200
    assert "text/html" in res.headers["content-type"]
    assert "RAG Console" in res.text


def test_ui_asks_for_no_credentials(open_client):
    """The console posts questions directly; there is no key field to fill in."""
    c, _ = open_client
    body = c.get("/").text
    assert "x-api-key" not in body
    assert "apiKey" not in body
    assert 'type="password"' not in body


def test_query_works_without_a_key_when_auth_is_off(open_client, monkeypatch):
    c, main = open_client
    _fake_answer(main, monkeypatch)

    res = c.post("/query", json={"question": "How are documents chunked?"})
    assert res.status_code == 200
    body = res.json()
    assert body["citations"][0]["doc_id"] == "d"
    assert body["model_id"] == "amazon.nova-lite-v1:0"


# ------------------------------------------------------------------ secured
@pytest.mark.parametrize("path", ["/query", "/ingest"])
def test_write_routes_require_the_key_when_enabled(secured_client, path):
    c, _ = secured_client
    payload = {"question": "hi", "source": "s3://b/k"}
    assert c.post(path, json=payload).status_code == 401
    assert c.post(path, json=payload, headers={"x-api-key": "wrong"}).status_code == 401


def test_correct_key_is_accepted(secured_client, monkeypatch):
    c, main = secured_client
    _fake_answer(main, monkeypatch)

    res = c.post("/query", json={"question": "why?"}, headers={"x-api-key": API_KEY})
    assert res.status_code == 200


def test_enabling_auth_without_a_key_refuses_to_start(monkeypatch):
    """Fail closed: never serve a route that is supposed to be guarded."""
    with pytest.raises(RuntimeError, match="API_KEY is not set"):
        _load(monkeypatch, require_auth=True, api_key=None)


# ---------------------------------------------------------------- validation
def test_invalid_query_payload_is_rejected(open_client):
    c, _ = open_client
    assert c.post("/query", json={"question": ""}).status_code == 422
    assert c.post("/query", json={"question": "ok", "mode": "nope"}).status_code == 422
    assert c.post("/query", json={"question": "ok", "k": 99}).status_code == 422
