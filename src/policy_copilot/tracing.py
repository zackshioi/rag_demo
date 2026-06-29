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


def send_langfuse(question: str, event: dict[str, Any]) -> None:
    """Mirror one event to a self-hosted Langfuse, if configured (Tier-2).

    No-ops when LANGFUSE_PUBLIC_KEY is unset (CI / offline). Never raises.
    """
    if not os.environ.get("LANGFUSE_PUBLIC_KEY"):
        return
    try:
        from langfuse import get_client

        client: Any = get_client()
        with client.start_as_current_observation(
            as_type="span", name="answer", input={"question": question}
        ):
            client.update_current_span(
                output=event.get("answer"),
                metadata={
                    "model": event.get("model"),
                    "refused": event.get("refused"),
                    "top_score": event.get("top_score"),
                    "citations": event.get("citations"),
                    "input_tokens": event.get("input_tokens"),
                    "output_tokens": event.get("output_tokens"),
                    "cost_usd": event.get("cost_usd"),
                    "error": event.get("error"),
                    "latency_ms": event.get("latency_ms"),
                },
            )
            client.score_current_trace(name="refused", value=int(bool(event.get("refused"))))
            top_score = event.get("top_score")
            if top_score is not None:
                client.score_current_trace(name="top_score", value=float(top_score))
        client.flush()
    except Exception:  # noqa: BLE001 — observability must never break the answer
        pass


def send_langfuse_agentic(
    question: str, event: dict[str, Any], tool_calls: list[dict[str, Any]]
) -> None:
    """Mirror an agentic answer to Langfuse with one child span per tool call.

    No-ops without LANGFUSE_PUBLIC_KEY. Never raises. The nested spans let you
    see the model's search trajectory (search -> search -> answer) in the UI.
    """
    if not os.environ.get("LANGFUSE_PUBLIC_KEY"):
        return
    try:
        from langfuse import get_client

        client: Any = get_client()
        with client.start_as_current_observation(
            as_type="span", name="answer_agentic", input={"question": question}
        ):
            for call in tool_calls:
                with client.start_as_current_observation(
                    as_type="span",
                    name="search_documents",
                    input={"query": call.get("query"), "k": call.get("k")},
                ):
                    client.update_current_span(
                        output={
                            "chunk_ids": call.get("chunk_ids"),
                            "top_score": call.get("top_score"),
                        }
                    )
            client.update_current_span(
                output=event.get("answer"),
                metadata={
                    "model": event.get("model"),
                    "refused": event.get("refused"),
                    "n_tool_calls": event.get("n_tool_calls"),
                    "citations": event.get("citations"),
                    "input_tokens": event.get("input_tokens"),
                    "output_tokens": event.get("output_tokens"),
                    "cost_usd": event.get("cost_usd"),
                    "error": event.get("error"),
                    "latency_ms": event.get("latency_ms"),
                },
            )
            client.score_current_trace(name="refused", value=int(bool(event.get("refused"))))
            client.score_current_trace(
                name="citations_resolve", value=int(bool(event.get("citations_resolve")))
            )
            client.score_current_trace(
                name="numbers_verbatim", value=int(bool(event.get("numbers_verbatim")))
            )
        client.flush()
    except Exception:  # noqa: BLE001 — observability must never break the answer
        pass
