from app.ingestion.chunker import (
    DEFAULT_CHUNK_SIZE,
    chunk_documents,
    normalize,
    split_text,
)

import pytest


def test_normalize_collapses_whitespace_but_keeps_paragraphs():
    assert normalize("a  \t b\r\n\n\n\nc") == "a b\n\nc"


def test_empty_text_yields_no_chunks():
    assert split_text("   \n\n  ") == []


def test_short_text_is_a_single_chunk():
    chunks = split_text("Hello world.")
    assert chunks == ["Hello world."]


def test_chunks_respect_max_size():
    text = " ".join(f"Sentence number {i} about pipelines." for i in range(400))
    chunks = split_text(text, chunk_size=200, overlap=40)
    assert len(chunks) > 1
    assert all(len(c) <= 200 for c in chunks)


def test_overlap_carries_context_between_chunks():
    text = " ".join(f"Fact {i} matters." for i in range(60))
    chunks = split_text(text, chunk_size=120, overlap=40)
    tail = chunks[0][-20:]
    assert tail in chunks[1]


def test_oversized_single_unit_is_hard_split():
    chunks = split_text("x" * 500, chunk_size=100, overlap=0)
    assert len(chunks) == 5
    assert all(len(c) == 100 for c in chunks)


@pytest.mark.parametrize("size,overlap", [(0, 0), (100, 100), (100, 150), (100, -1)])
def test_invalid_parameters_raise(size, overlap):
    with pytest.raises(ValueError):
        split_text("some text", chunk_size=size, overlap=overlap)


def test_chunk_documents_assigns_stable_ids_and_metadata():
    docs = [
        {"id": "a.txt", "source": "s3://b/a.txt", "text": "one. two. three.", "metadata": {"bytes": 16}},
        {"id": "b.txt", "source": "s3://b/b.txt", "text": "four. five.", "metadata": {}},
    ]
    chunks = chunk_documents(docs, chunk_size=DEFAULT_CHUNK_SIZE, overlap=0)
    assert [c.doc_id for c in chunks] == ["a.txt", "b.txt"]
    assert chunks[0].id == "a.txt::0"
    assert chunks[0].metadata == {"bytes": 16}
    assert chunks[0].source == "s3://b/a.txt"


def test_chunk_documents_skips_blank_documents():
    assert chunk_documents([{"id": "empty", "text": "  "}]) == []
