import pytest

from app.retrieval import rag
from app.retrieval.search import Hit, build_knn_query, reciprocal_rank_fusion


class FakeConverse:
    """Stand-in for bedrock-runtime's Converse API."""

    def __init__(self, text="Terraform provisions the index. [1]"):
        self.text = text
        self.calls: list[dict] = []

    def converse(self, **kwargs):
        self.calls.append(kwargs)
        return {"output": {"message": {"role": "assistant", "content": [{"text": self.text}]}}}


def hits(n=3):
    return [
        Hit(id=f"doc::{i}", score=1.0 - i / 10, text=f"chunk {i}", doc_id="doc", source=f"s3://b/doc{i}.md")
        for i in range(n)
    ]


def test_build_context_numbers_blocks_and_returns_citations():
    context, citations = rag.build_context(hits(2))
    assert "[1] source: s3://b/doc0.md" in context
    assert "[2] source: s3://b/doc1.md" in context
    assert [c["marker"] for c in citations] == [1, 2]


def test_build_context_respects_char_budget():
    context, citations = rag.build_context(hits(5), max_chars=60)
    assert len(citations) < 5
    assert len(context) <= 60


def test_build_prompt_marks_missing_context():
    assert "No context retrieved." in rag.build_prompt("q", "")


def test_answer_question_uses_retrieved_context():
    llm = FakeConverse()
    result = rag.answer_question("who provisions the index?", k=2, search_fn=lambda q, k: hits(2), llm_client=llm)
    assert result.answer == "Terraform provisions the index. [1]"
    assert len(result.citations) == 2
    call = llm.calls[0]
    assert call["inferenceConfig"]["temperature"] == 0.0
    assert "chunk 0" in call["messages"][0]["content"][0]["text"]
    assert call["system"][0]["text"] == rag.SYSTEM_PROMPT


def test_answer_question_without_hits_does_not_call_llm():
    llm = FakeConverse()
    result = rag.answer_question("anything?", search_fn=lambda q, k: [], llm_client=llm)
    assert result.citations == []
    assert llm.calls == []
    assert "could not find" in result.answer


@pytest.mark.parametrize("question", ["", "   ", None])
def test_blank_question_rejected(question):
    with pytest.raises(ValueError):
        rag.answer_question(question, search_fn=lambda q, k: hits())


def test_knn_query_adds_doc_filter():
    plain = build_knn_query([0.1, 0.2], k=3)
    assert plain["query"]["knn"]["vector"]["k"] == 3

    filtered = build_knn_query([0.1, 0.2], k=3, doc_id="a.txt")
    assert filtered["query"]["bool"]["filter"] == [{"term": {"doc_id": "a.txt"}}]


def test_rrf_ranks_documents_found_by_both_retrievers_first():
    dense = [Hit("a", 9.0, "a", "a", ""), Hit("b", 8.0, "b", "b", "")]
    sparse = [Hit("c", 5.0, "c", "c", ""), Hit("b", 4.0, "b", "b", "")]
    merged = reciprocal_rank_fusion(dense, sparse, k=3)
    assert merged[0].id == "b"
    assert {h.id for h in merged} == {"a", "b", "c"}
