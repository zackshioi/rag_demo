"""Agentic tool-use loop (Phase 2, F2.1–F2.3) with a deterministic verifier.

Instead of always retrieving (Phase 1 `answer()`), here Claude is given a
`search_documents` tool and *decides* when and how often to call it — a manual
ReAct-style harness loop (own the control flow, bounded iterations, trace every
tool call). After the model answers, a deterministic verifier checks the answer
against the retrieved excerpts (citations must resolve; numbers should be verbatim).

Best-practice harness design (see EVALUATION.md / Phase 2 notes):
- one bounded while-loop; explicit max rounds (no runaway)
- one well-documented tool (the agent-computer interface)
- tool errors fed back to the model, not raised
- every tool call traced (JSONL + optional Langfuse nested spans)
- a deterministic verifier > trusting the model to self-check
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from langfuse import observe

from policy_copilot.agent import MODEL, REFUSAL_TEXT, _extract_citations, cost_usd
from policy_copilot.chunking import Chunk
from policy_copilot.index import load_index, search
from policy_copilot.tracing import finalize_langfuse, record

load_dotenv()

PROMPT_PATH = Path(__file__).resolve().parents[2] / "prompts" / "system_prompt_agentic.md"
MAX_ROUNDS = 4

SEARCH_TOOL: dict[str, Any] = {
    "name": "search_documents",
    "description": (
        "Search the indexed company filings for excerpts relevant to a query. "
        "Returns ranked excerpts, each labelled with a citable id like [AMD_2022_10K::0153]."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "What to search for, in natural language."},
            "k": {"type": "integer", "description": "How many excerpts to return (default 5)."},
        },
        "required": ["query"],
    },
}

_NUMBER = re.compile(r"\$?\d[\d,]*(?:\.\d+)?")


@dataclass(frozen=True)
class Verdict:
    """Deterministic post-check of an answer against the retrieved excerpts."""

    citations_resolve: bool  # every cited id was actually retrieved (no fabricated citation)
    numbers_verbatim: bool  # every number in the answer appears verbatim in the excerpts


@dataclass(frozen=True)
class AgenticAnswer:
    """An agentic answer plus its tool-call trajectory and verdict."""

    text: str
    refused: bool
    citations: list[str]
    tool_calls: list[dict[str, Any]]
    verdict: Verdict
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    error: str | None = None


def _format_hits(hits: list[Any]) -> str:
    if not hits:
        return "No matching excerpts found."
    return "\n\n".join(
        f"[{h.chunk.chunk_id}] (score {h.score:.2f})\n{h.chunk.text[:1200]}" for h in hits
    )


def verify(answer_text: str, retrieved: list[Chunk]) -> Verdict:
    """Deterministically check the answer against the excerpts it was given."""
    corpus_ids = {c.chunk_id for c in retrieved}
    cited = set(_extract_citations(answer_text))
    citations_resolve = cited.issubset(corpus_ids)  # empty set resolves trivially

    corpus = " ".join(c.text for c in retrieved).replace(",", "")
    # Strip citation tokens first so their digits (e.g. ::0153) aren't read as numbers.
    body = re.sub(r"\[[A-Za-z0-9_]+::\d+\]", " ", answer_text)
    numbers = _NUMBER.findall(body)
    numbers_verbatim = all(n.replace("$", "").replace(",", "") in corpus for n in numbers)
    return Verdict(citations_resolve=citations_resolve, numbers_verbatim=numbers_verbatim)


@observe(name="answer_agentic", capture_input=False, capture_output=False)
def answer_agentic(
    question: str,
    index: Any = None,
    chunks: list[Any] | None = None,
    max_rounds: int = MAX_ROUNDS,
) -> AgenticAnswer:
    """Let Claude drive retrieval via the search tool, then verify the answer."""
    import anthropic

    started = time.monotonic()
    if index is None or chunks is None:
        index, chunks = load_index()
    client: Any = anthropic.Anthropic()
    system = PROMPT_PATH.read_text(encoding="utf-8")

    messages: list[Any] = [{"role": "user", "content": question}]
    tool_calls: list[dict[str, Any]] = []
    retrieved: dict[str, Chunk] = {}
    final_text = REFUSAL_TEXT
    refused = True
    input_tokens = 0
    output_tokens = 0
    error: str | None = None

    for _ in range(max_rounds):
        try:
            response = client.messages.create(
                model=MODEL, max_tokens=1024, system=system, tools=[SEARCH_TOOL], messages=messages
            )
        except anthropic.APIError as exc:  # API failure -> safe refusal, traced as error
            error = type(exc).__name__
            break
        input_tokens += int(response.usage.input_tokens)
        output_tokens += int(response.usage.output_tokens)
        if response.stop_reason == "refusal":
            break
        if response.stop_reason != "tool_use":
            final_text = "".join(b.text for b in response.content if b.type == "text").strip()
            refused = final_text.upper().startswith(REFUSAL_TEXT)
            break

        messages.append({"role": "assistant", "content": response.content})
        results: list[Any] = []
        for block in response.content:
            if block.type != "tool_use" or block.name != "search_documents":
                continue
            tool_input = block.input if isinstance(block.input, dict) else {}
            query = str(tool_input.get("query", ""))
            k = int(tool_input.get("k", 5))
            hits = search(index, chunks, query, max(1, min(k, 10)))
            for h in hits:
                retrieved[h.chunk.chunk_id] = h.chunk
            tool_calls.append(
                {
                    "query": query,
                    "k": k,
                    "chunk_ids": [h.chunk.chunk_id for h in hits],
                    "top_score": round(hits[0].score, 4) if hits else None,
                }
            )
            results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": _format_hits(hits),
                    "is_error": not hits,
                }
            )
        messages.append({"role": "user", "content": results})

    retrieved_chunks = list(retrieved.values())
    verdict = verify(final_text, retrieved_chunks) if not refused else Verdict(True, True)
    # Hard gate: a citation that wasn't retrieved is a fabrication -> refuse.
    if not refused and not verdict.citations_resolve:
        final_text, refused = REFUSAL_TEXT, True

    citations = _extract_citations(final_text) if not refused else []
    result = AgenticAnswer(
        text=final_text,
        refused=refused,
        citations=citations,
        tool_calls=tool_calls,
        verdict=verdict,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=cost_usd(MODEL, input_tokens, output_tokens),
        error=error,
    )
    _trace(question, result, (time.monotonic() - started) * 1000)
    return result


def _trace(question: str, result: AgenticAnswer, latency_ms: float) -> None:
    event = {
        "mode": "agentic",
        "question": question,
        "model": MODEL,
        "refused": result.refused,
        "answer": result.text,
        "citations": result.citations,
        "n_tool_calls": len(result.tool_calls),
        "tool_calls": result.tool_calls,
        "citations_resolve": result.verdict.citations_resolve,
        "numbers_verbatim": result.verdict.numbers_verbatim,
        "input_tokens": result.input_tokens,
        "output_tokens": result.output_tokens,
        "cost_usd": result.cost_usd,
        "error": result.error,
        "latency_ms": round(latency_ms, 1),
    }
    record(event)
    finalize_langfuse(question, event)


def main() -> None:
    """Demo: a question that needs a search, and one out of corpus."""
    index, chunks = load_index()
    for question in [
        "What was AMD's total net revenue in fiscal 2022, and how did it change from 2021?",
        "What was Netflix's subscriber count in 2023?",  # out of corpus
    ]:
        result = answer_agentic(question, index, chunks)
        print(f"Q: {question}")
        print(
            f"  tool calls : {len(result.tool_calls)} -> {[t['query'] for t in result.tool_calls]}"
        )
        print(f"  refused    : {result.refused}")
        print(
            f"  verdict    : citations_resolve={result.verdict.citations_resolve} "
            f"numbers_verbatim={result.verdict.numbers_verbatim}"
        )
        print(f"  answer     : {result.text[:300]}")
        print(f"  cited      : {result.citations}\n")


if __name__ == "__main__":
    main()
