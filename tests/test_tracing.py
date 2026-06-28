"""Unit tests for tracing — offline."""

from pathlib import Path

import pytest

from policy_copilot import tracing


def test_record_and_load(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    trace_file = tmp_path / "traces.jsonl"
    monkeypatch.setattr(tracing, "TRACE_DIR", tmp_path)
    monkeypatch.setattr(tracing, "TRACE_FILE", trace_file)

    tracing.record({"question": "q", "refused": True})
    rows = tracing.load_traces(trace_file)

    assert len(rows) == 1
    assert rows[0]["question"] == "q"
    assert "ts" in rows[0]  # timestamp is stamped automatically


def test_load_traces_missing_file(tmp_path: Path) -> None:
    assert tracing.load_traces(tmp_path / "nope.jsonl") == []
