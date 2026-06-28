"""Lightweight local tracing — the 'trace' stage of the EDD loop (Tier-1).

Every `agent.answer()` call appends one JSON line to `data/traces/traces.jsonl`
(git-ignored). These traces are the raw material for error analysis (diagnose)
and online sampling. In production this is replaced by Bedrock model-invocation
logging -> CloudWatch/S3 with the same record shape. See `docs/EVALUATION.md`.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

TRACE_DIR = Path("data/traces")
TRACE_FILE = TRACE_DIR / "traces.jsonl"


def record(event: dict[str, Any]) -> None:
    """Append one trace event as a JSON line. Best-effort — never raises."""
    try:
        TRACE_DIR.mkdir(parents=True, exist_ok=True)
        stamped = {"ts": datetime.now(UTC).isoformat(), **event}
        with TRACE_FILE.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(stamped, ensure_ascii=False) + "\n")
    except OSError:
        pass


def load_traces(path: Path = TRACE_FILE) -> list[dict[str, Any]]:
    """Read all trace events (for error analysis / diagnose)."""
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]
