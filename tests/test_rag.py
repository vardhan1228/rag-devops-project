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
    """Distinct doc_ids so derived titles differ per hit."""
    return [
        Hit(
            id=f"uploads/doc{i}.md::0",
            score=1.0 - i / 10,
            text=f"chunk {i}",
            doc_id=f"uploads/doc{i}.md",
            source=f"s3://b/uploads/doc{i}.md",
        )
        for i in range(n)
    ]


def test_build_context_numbers_blocks_and_returns_citations():
    context, citations = rag.build_context(hits(2))
    assert "[1] Doc0" in context
    assert "[2] Doc1" in context
    assert [c["marker"] for c in citations] == [1, 2]
    assert [c["title"] for c in citations] == ["Doc0", "Doc1"]


def test_context_never_leaks_storage_paths():
    """The model must not be handed a bucket path it could quote into an answer."""
    context, citations = rag.build_context(hits(3))
    assert "s3://" not in context
    assert ".md" not in context
    assert all("source" not in c for c in citations)


@pytest.mark.parametrize(
    "doc_id,expected",
    [
        ("uploads/05-fraud-and-disputes.md", "Fraud And Disputes"),
        ("uploads/03-kyc-and-onboarding.md", "KYC And Onboarding"),
        ("uploads/04-payments-and-limits.md", "Payments And Limits"),
        ("01-deposit-account-products.md", "Deposit Account Products"),
        ("notes.txt", "Notes"),
        ("a/b/c/quarterly_report.pdf", "Quarterly Report"),
        ("", "Untitled document"),
    ],
)
def test_document_title(doc_id, expected):
    assert rag.document_title(doc_id) == expected


def test_document_title_falls_back_to_source():
    assert rag.document_title("", "s3://bucket/uploads/07-aml-and-monitoring.md") == "AML And Monitoring"


def test_system_prompt_demands_grounding_and_structure():
    """These instructions are load bearing; losing one changes answer quality."""
    prompt = rag.SYSTEM_PROMPT
    assert "Use only the context" in prompt
    assert "Markdown" in prompt
    assert "Bold every number" in prompt
    assert "[1]" in prompt


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
