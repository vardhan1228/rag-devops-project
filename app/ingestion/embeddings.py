"""Amazon Bedrock text embeddings with batching and retry."""

from __future__ import annotations

import json
import os
import time
from typing import Sequence

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

EMBED_MODEL_ID = os.getenv("EMBED_MODEL_ID", "amazon.titan-embed-text-v2:0")
EMBED_DIMENSION = int(os.getenv("EMBED_DIMENSION", "1024"))
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")

_THROTTLE_CODES = {"ThrottlingException", "TooManyRequestsException", "ServiceUnavailableException"}


def _client():
    return boto3.client(
        "bedrock-runtime",
        region_name=AWS_REGION,
        config=Config(retries={"max_attempts": 3, "mode": "standard"}),
    )


class Embedder:
    """Thin wrapper around a Bedrock embedding model.

    The client is created lazily so importing this module never requires
    credentials (useful in unit tests and at container build time).
    """

    def __init__(self, model_id: str = EMBED_MODEL_ID, dimension: int = EMBED_DIMENSION, client=None):
        self.model_id = model_id
        self.dimension = dimension
        self._client = client

    @property
    def client(self):
        if self._client is None:
            self._client = _client()
        return self._client

    def embed_text(self, text: str) -> list[float]:
        if not text or not text.strip():
            raise ValueError("cannot embed empty text")
        body = {"inputText": text}
        if "titan-embed-text-v2" in self.model_id:
            body["dimensions"] = self.dimension
            body["normalize"] = True

        for attempt in range(4):
            try:
                response = self.client.invoke_model(
                    modelId=self.model_id,
                    body=json.dumps(body),
                    accept="application/json",
                    contentType="application/json",
                )
                break
            except ClientError as exc:
                code = exc.response.get("Error", {}).get("Code", "")
                if code not in _THROTTLE_CODES or attempt == 3:
                    raise
                time.sleep(2**attempt)

        payload = json.loads(response["body"].read())
        vector = payload.get("embedding") or payload.get("embeddings", [None])[0]
        if not vector:
            raise RuntimeError(f"no embedding returned by {self.model_id}")
        return [float(v) for v in vector]

    def embed_batch(self, texts: Sequence[str], batch_size: int = 16) -> list[list[float]]:
        """Embed many texts. Bedrock Titan is single-input, so this loops in slices
        to keep memory bounded and make throttling backoff predictable."""
        vectors: list[list[float]] = []
        for start in range(0, len(texts), batch_size):
            for text in texts[start : start + batch_size]:
                vectors.append(self.embed_text(text))
        return vectors


_default: Embedder | None = None


def get_embedder() -> Embedder:
    global _default
    if _default is None:
        _default = Embedder()
    return _default
