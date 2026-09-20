import io
import json

import pytest
from botocore.exceptions import ClientError

from app.ingestion.embeddings import Embedder


class FakeBody:
    def __init__(self, payload: dict):
        self._buf = io.BytesIO(json.dumps(payload).encode())

    def read(self) -> bytes:
        return self._buf.read()


class FakeBedrock:
    """Minimal stand-in for bedrock-runtime; records calls, replays scripted results."""

    def __init__(self, vector=None, errors=0):
        self.vector = vector or [0.1, 0.2, 0.3]
        self.errors = errors
        self.calls: list[dict] = []

    def invoke_model(self, **kwargs):
        self.calls.append(kwargs)
        if self.errors > 0:
            self.errors -= 1
            raise ClientError({"Error": {"Code": "ThrottlingException"}}, "InvokeModel")
        return {"body": FakeBody({"embedding": self.vector})}


def test_embed_text_returns_floats():
    client = FakeBedrock(vector=[1, 2, 3])
    vector = Embedder(client=client).embed_text("hello")
    assert vector == [1.0, 2.0, 3.0]
    assert all(isinstance(v, float) for v in vector)


def test_titan_v2_request_includes_dimensions():
    client = FakeBedrock()
    Embedder(model_id="amazon.titan-embed-text-v2:0", dimension=512, client=client).embed_text("hi")
    body = json.loads(client.calls[0]["body"])
    assert body == {"inputText": "hi", "dimensions": 512, "normalize": True}


def test_non_titan_v2_request_is_plain():
    client = FakeBedrock()
    Embedder(model_id="cohere.embed-english-v3", client=client).embed_text("hi")
    assert json.loads(client.calls[0]["body"]) == {"inputText": "hi"}


@pytest.mark.parametrize("text", ["", "   ", None])
def test_empty_input_rejected(text):
    with pytest.raises(ValueError):
        Embedder(client=FakeBedrock()).embed_text(text)


def test_throttling_is_retried(monkeypatch):
    monkeypatch.setattr("app.ingestion.embeddings.time.sleep", lambda _s: None)
    client = FakeBedrock(errors=2)
    assert Embedder(client=client).embed_text("hello") == [0.1, 0.2, 0.3]
    assert len(client.calls) == 3


def test_non_throttling_error_propagates():
    class Boom(FakeBedrock):
        def invoke_model(self, **kwargs):
            raise ClientError({"Error": {"Code": "AccessDeniedException"}}, "InvokeModel")

    with pytest.raises(ClientError):
        Embedder(client=Boom()).embed_text("hello")


def test_missing_embedding_raises():
    class Empty(FakeBedrock):
        def invoke_model(self, **kwargs):
            return {"body": FakeBody({})}

    with pytest.raises(RuntimeError):
        Embedder(client=Empty()).embed_text("hello")


def test_embed_batch_preserves_order_and_length():
    class Counter(FakeBedrock):
        def invoke_model(self, **kwargs):
            self.calls.append(kwargs)
            n = len(self.calls)
            return {"body": FakeBody({"embedding": [float(n)]})}

    vectors = Embedder(client=Counter()).embed_batch(["a", "b", "c"], batch_size=2)
    assert vectors == [[1.0], [2.0], [3.0]]
