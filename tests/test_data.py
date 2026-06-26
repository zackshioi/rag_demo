"""Unit tests for corpus construction — offline (no dataset download)."""

from policy_copilot.data import Document, build_corpus, category_counts

FAKE_ROWS = [
    {"category": "core", "context": "Doc A text"},
    {"category": "core", "context": "Doc A text"},  # duplicate context
    {"category": "boolean", "context": "Doc B text"},
]


def test_category_counts() -> None:
    assert category_counts(FAKE_ROWS) == {"core": 2, "boolean": 1}


def test_build_corpus_dedups_contexts() -> None:
    docs = build_corpus(FAKE_ROWS)
    assert [d.text for d in docs] == ["Doc A text", "Doc B text"]


def test_build_corpus_assigns_stable_ids() -> None:
    docs = build_corpus(FAKE_ROWS)
    assert [d.doc_id for d in docs] == ["doc_000", "doc_001"]
    assert isinstance(docs[0], Document)
