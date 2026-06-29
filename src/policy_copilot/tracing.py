"""Tracing — the 'trace' stage of the EDD loop.

Tier-1 (always on): every answer() appends a JSON line to data/traces/traces.jsonl
(git-ignored) — the raw material for error analysis and CI.

Tier-2 (optional): if a self-hosted Langfuse is configured (LANGFUSE_* env vars),
the same event is mirrored there for a web UI. Best-effort and fully decoupled —
no keys => no-op, and it never blocks or breaks an answer.

In production both are replaced by Bedrock model-invocation logging -> CloudWatch.
See docs/EVALUATION.md.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

TRACE_DIR = Path("data/traces")
TRACE_FILE = TRACE_DIR / "traces.jsonl"

_instrumented = False


def setup_auto_instrumentation() -> None:
    """Auto-instrument the Anthropic SDK -> Langfuse (native model/token/cost).

    OpenTelemetry auto-instrumentation: every Claude call becomes a `generation`
    observation with model + usage, so Langfuse computes native cost. Idempotent;
    no-op without LANGFUSE_PUBLIC_KEY. Our manual spans still add business
    semantics (trajectory, verdict) on top.
    """
    global _instrumented
    if _instrumented or not os.environ.get("LANGFUSE_PUBLIC_KEY"):
        return
    try:
        from langfuse import get_client
        from opentelemetry.instrumentation.anthropic import AnthropicInstrumentor

        get_client()  # sets up the Langfuse OTEL tracer provider from env
        AnthropicInstrumentor().instrument()
        _instrumented = True
    except Exception:  # noqa: BLE001 — observability must never break the answer
        pass


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


# Metadata keys mirrored onto the Langfuse span (whichever the event carries).
_META_KEYS = (
    "model",
    "refused",
    "top_score",
    "n_tool_calls",
    "citations",
    "input_tokens",
    "output_tokens",
    "cost_usd",
    "error",
    "latency_ms",
)
# Numeric/boolean event fields published as Langfuse scores (skipped if absent).
_SCORE_KEYS = ("top_score", "citations_resolve", "numbers_verbatim")


def finalize_langfuse(question: str, event: dict[str, Any]) -> None:
    """Attach business semantics to the *current* @observe span/trace (Tier-2).

    Called from inside an `@observe`-decorated answer function, so the
    auto-instrumented Claude `generation`s already nest under this span — giving
    one clean trace (business span -> generations) instead of two separate ones.
    No-op without LANGFUSE_PUBLIC_KEY; never raises.
    """
    if not os.environ.get("LANGFUSE_PUBLIC_KEY"):
        return
    try:
        from langfuse import get_client

        client: Any = get_client()
        client.set_current_trace_io(input={"question": question}, output=event.get("answer"))
        client.update_current_span(metadata={k: event.get(k) for k in _META_KEYS})
        client.score_current_trace(name="refused", value=int(bool(event.get("refused"))))
        for key in _SCORE_KEYS:
            value = event.get(key)
            if value is not None:
                client.score_current_trace(name=key, value=float(value))
    except Exception:  # noqa: BLE001 — observability must never break the answer
        pass
