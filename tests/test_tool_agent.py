"""Unit tests for the agentic verifier and tool — offline (no model)."""

from policy_copilot.chunking import Chunk
from policy_copilot.index import SearchHit
from policy_copilot.tool_agent import SEARCH_TOOL, _format_hits, verify


def _chunk(chunk_id: str, text: str) -> Chunk:
    return Chunk(chunk_id=chunk_id, doc_id="AMD_2022_10K", heading="Revenue", text=text)


def test_search_tool_schema() -> None:
    assert SEARCH_TOOL["name"] == "search_documents"
    assert "query" in SEARCH_TOOL["input_schema"]["properties"]


def test_verify_passes_when_citation_and_number_match() -> None:
    chunks = [_chunk("AMD_2022_10K::0001", "Net revenue 23,601")]
    v = verify("Revenue was 23,601 [AMD_2022_10K::0001]", chunks)
    assert v.citations_resolve is True
    assert v.numbers_verbatim is True


def test_verify_flags_fabricated_citation() -> None:
    chunks = [_chunk("AMD_2022_10K::0001", "Net revenue 23,601")]
    v = verify("Revenue [AMD_2022_10K::9999]", chunks)  # id not retrieved
    assert v.citations_resolve is False


def test_verify_flags_non_verbatim_number() -> None:
    chunks = [_chunk("AMD_2022_10K::0001", "Net revenue 23,601")]
    v = verify("Revenue was $23.6 billion [AMD_2022_10K::0001]", chunks)
    assert v.numbers_verbatim is False  # 23.6 is a rounding, not verbatim 23,601


def test_format_hits_empty_and_nonempty() -> None:
    assert "No matching" in _format_hits([])
    hit = SearchHit(chunk=_chunk("AMD_2022_10K::0001", "Net revenue 23,601"), score=0.7)
    assert "AMD_2022_10K::0001" in _format_hits([hit])
