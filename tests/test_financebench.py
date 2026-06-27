"""Unit tests for FinanceBench subset selection — offline (no download)."""

from policy_copilot.financebench import questions_for, select_documents

FAKE_ROWS = [
    {"doc_name": "DOC_A", "company": "x"},
    {"doc_name": "DOC_A", "company": "x"},
    {"doc_name": "DOC_B", "company": "y"},
    {"doc_name": "DOC_C", "company": "z"},
]


def test_select_documents_ranks_by_question_count() -> None:
    # DOC_A has 2 questions; DOC_B/DOC_C have 1 each -> tie broken alphabetically.
    assert select_documents(FAKE_ROWS, n=2) == ["DOC_A", "DOC_B"]


def test_questions_for_filters_to_subset() -> None:
    rows = questions_for(FAKE_ROWS, ["DOC_A"])
    assert len(rows) == 2
    assert all(r["doc_name"] == "DOC_A" for r in rows)
