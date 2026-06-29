"""Unit tests for answer assembly — offline (no model, no API)."""

from policy_copilot.agent import _extract_citations, _format_context, _should_refuse, cost_usd
from policy_copilot.chunking import Chunk
from policy_copilot.index import SearchHit


def _hit(score: float, chunk_id: str = "AMD_2022_10K::0153") -> SearchHit:
    chunk = Chunk(
        chunk_id=chunk_id, doc_id="AMD_2022_10K", heading="Revenue", text="Net revenue 23,601"
    )
    return SearchHit(chunk=chunk, score=score)


def test_should_refuse_when_no_hits() -> None:
    assert _should_refuse([]) is True


def test_should_refuse_when_top_score_low() -> None:
    assert _should_refuse([_hit(0.30)]) is True


def test_no_refuse_when_top_score_high() -> None:
    assert _should_refuse([_hit(0.70)]) is False


def test_extract_citations_dedupes() -> None:
    text = "Revenue was 23,601 [AMD_2022_10K::0153] per [AMD_2022_10K::0153]."
    assert _extract_citations(text) == ["AMD_2022_10K::0153"]


def test_format_context_includes_id_and_text() -> None:
    rendered = _format_context([_hit(0.7)])
    assert "AMD_2022_10K::0153" in rendered
    assert "Net revenue" in rendered


def test_cost_usd_known_model() -> None:
    # 1M input @ $3 + 1M output @ $15 = $18
    assert cost_usd("claude-sonnet-4-6", 1_000_000, 1_000_000) == 18.0


def test_cost_usd_unknown_model_is_zero() -> None:
    assert cost_usd("some-other-model", 1000, 2000) == 0.0
