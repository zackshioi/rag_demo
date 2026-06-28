"""Answer generation with citations, refusal, and tracing (Phase 1, F1.6 + F1.7).

The flow: retrieve chunks (F1.5) -> if the top score is too low, refuse cheaply
without calling the model -> otherwise feed the chunks to Claude under a
governance system prompt that forces grounded, cited answers and "NOT FOUND"
when unsupported. Numbers must be quoted verbatim from the context. Every call
records a trace (the 'trace' stage of the EDD loop — see docs/EVALUATION.md).

Uses the Anthropic SDK (Pillar 1) with the local `Anthropic` client; the API key
is read from the environment (`.env` via python-dotenv). Phase 3 swaps this for
`AnthropicBedrock` with the same loop.
"""

from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import anthropic
from anthropic.types import TextBlock
from dotenv import load_dotenv

from policy_copilot.index import SearchHit, load_index, search
from policy_copilot.tracing import record

load_dotenv()

MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")
PROMPT_PATH = Path(__file__).resolve().parents[2] / "prompts" / "system_prompt.md"
# Top score below this -> refuse without calling the model (tuned in Phase 6).
REFUSAL_THRESHOLD = 0.45
REFUSAL_TEXT = "NOT FOUND"

_CITATION = re.compile(r"\[([A-Za-z0-9_]+::\d{3,})\]")


@dataclass(frozen=True)
class Answer:
    """A generated answer with provenance."""

    text: str
    refused: bool
    citations: list[str]
    hits: list[SearchHit]


def _should_refuse(hits: list[SearchHit]) -> bool:
    """Cheap pre-check: refuse if nothing retrieved or the best match is weak."""
    return not hits or hits[0].score < REFUSAL_THRESHOLD


def _format_context(hits: list[SearchHit]) -> str:
    """Render retrieved chunks as labelled excerpts for the prompt."""
    blocks = [
        f"[{h.chunk.chunk_id}] (from {h.chunk.doc_id} · {h.chunk.heading})\n{h.chunk.text}"
        for h in hits
    ]
    return "\n\n---\n\n".join(blocks)


def _extract_citations(text: str) -> list[str]:
    """Pull cited chunk ids (e.g. [AMD_2022_10K::0153]) out of the answer."""
    return sorted(set(_CITATION.findall(text)))


def _trace(question: str, result: Answer, latency_ms: float) -> Answer:
    """Record one trace event, then return the answer unchanged."""
    record(
        {
            "question": question,
            "model": MODEL,
            "refused": result.refused,
            "answer": result.text,
            "citations": result.citations,
            "top_score": round(result.hits[0].score, 4) if result.hits else None,
            "retrieved": [
                {"chunk_id": h.chunk.chunk_id, "score": round(h.score, 4)} for h in result.hits
            ],
            "latency_ms": round(latency_ms, 1),
        }
    )
    return result


def answer(
    question: str,
    index: Any = None,
    chunks: list[Any] | None = None,
    k: int = 5,
) -> Answer:
    """Answer a question from the corpus, with citations or an explicit refusal."""
    started = time.monotonic()
    if index is None or chunks is None:
        index, chunks = load_index()
    hits = search(index, chunks, question, k=k)

    if _should_refuse(hits):
        result = Answer(text=REFUSAL_TEXT, refused=True, citations=[], hits=hits)
        return _trace(question, result, (time.monotonic() - started) * 1000)

    client = anthropic.Anthropic()
    user = f"Context:\n\n{_format_context(hits)}\n\nQuestion: {question}"
    response = client.messages.create(
        model=MODEL,
        max_tokens=1024,
        system=PROMPT_PATH.read_text(encoding="utf-8"),
        messages=[{"role": "user", "content": user}],
    )
    if response.stop_reason == "refusal":
        result = Answer(text=REFUSAL_TEXT, refused=True, citations=[], hits=hits)
        return _trace(question, result, (time.monotonic() - started) * 1000)

    text = "".join(b.text for b in response.content if isinstance(b, TextBlock)).strip()
    refused = text.upper().startswith(REFUSAL_TEXT)
    citations = [] if refused else _extract_citations(text)
    result = Answer(text=text, refused=refused, citations=citations, hits=hits)
    return _trace(question, result, (time.monotonic() - started) * 1000)


def main() -> None:
    """Demo: ask a couple of questions (one answerable, one out of corpus)."""
    index, chunks = load_index()
    questions = [
        "What was AMD's total net revenue in fiscal 2022?",  # in corpus -> answer
        "What is the capital of France?",  # out of corpus -> refuse
    ]
    for question in questions:
        result = answer(question, index, chunks)
        print(f"Q: {question}")
        print(f"  refused : {result.refused}")
        print(f"  answer  : {result.text[:300]}")
        print(f"  cited   : {result.citations}")
        print()


if __name__ == "__main__":
    main()
