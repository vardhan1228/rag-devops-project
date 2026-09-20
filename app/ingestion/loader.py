"""Document loading from local disk or S3.

Returns a normalized list of Document dicts:
    {"id": str, "source": str, "text": str, "metadata": dict}
"""

from __future__ import annotations

import io
import os
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Iterable, Iterator

import boto3

SUPPORTED_SUFFIXES = {".txt", ".md", ".pdf"}


@dataclass
class Document:
    id: str
    source: str
    text: str
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


def _decode(raw: bytes) -> str:
    return raw.decode("utf-8", errors="replace")


def _read_pdf(raw: bytes) -> str:
    # Imported lazily so text-only deployments do not pay the import cost.
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(raw))
    pages = [(page.extract_text() or "") for page in reader.pages]
    return "\n\n".join(pages)


def parse_bytes(raw: bytes, source: str) -> str:
    """Turn raw file bytes into plain text based on the file suffix."""
    suffix = Path(source).suffix.lower()
    if suffix not in SUPPORTED_SUFFIXES:
        raise ValueError(f"unsupported file type: {suffix or '<none>'} ({source})")
    if suffix == ".pdf":
        return _read_pdf(raw)
    return _decode(raw)


def load_local(root: str | os.PathLike[str]) -> Iterator[Document]:
    """Yield documents for every supported file under ``root``."""
    root_path = Path(root)
    paths = [root_path] if root_path.is_file() else sorted(root_path.rglob("*"))
    for path in paths:
        if not path.is_file() or path.suffix.lower() not in SUPPORTED_SUFFIXES:
            continue
        text = parse_bytes(path.read_bytes(), path.name)
        if not text.strip():
            continue
        yield Document(
            id=str(path.relative_to(root_path) if root_path.is_dir() else path.name),
            source=str(path),
            text=text,
            metadata={"bytes": path.stat().st_size},
        )


def load_s3(bucket: str, prefix: str = "", client=None) -> Iterator[Document]:
    """Yield documents for every supported object under ``s3://bucket/prefix``."""
    s3 = client or boto3.client("s3")
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if key.endswith("/") or Path(key).suffix.lower() not in SUPPORTED_SUFFIXES:
                continue
            raw = s3.get_object(Bucket=bucket, Key=key)["Body"].read()
            text = parse_bytes(raw, key)
            if not text.strip():
                continue
            yield Document(
                id=key,
                source=f"s3://{bucket}/{key}",
                text=text,
                metadata={"bytes": obj.get("Size", len(raw))},
            )


def load(source: str) -> Iterable[Document]:
    """Dispatch on an ``s3://bucket/prefix`` URI or a local path."""
    if source.startswith("s3://"):
        bucket, _, prefix = source[len("s3://") :].partition("/")
        return load_s3(bucket, prefix)
    return load_local(source)
