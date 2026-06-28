"""Unit tests for chunking — offline (no model, no network)."""

from policy_copilot.chunking import Chunk, chunk_text


def test_chunk_text_splits_long_text() -> None:
    text = "\n\n".join(f"Paragraph {i} " + "x" * 300 for i in range(20))
    chunks = chunk_text("DOC", text, target_chars=600, overlap_chars=100)
    assert len(chunks) > 1
    assert all(isinstance(c, Chunk) for c in chunks)
    assert all(c.doc_id == "DOC" for c in chunks)


def test_chunk_ids_are_sequential() -> None:
    text = "\n\n".join("y" * 500 for _ in range(6))
    chunks = chunk_text("D", text, target_chars=600, overlap_chars=0)
    assert [c.chunk_id for c in chunks] == [f"D::{i:04d}" for i in range(len(chunks))]


def test_heading_is_tracked() -> None:
    chunks = chunk_text("D", "# Revenue\n\nSome paragraph about revenue.")
    assert chunks[0].heading == "Revenue"
