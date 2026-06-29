"""Interactive CLI for Policy Copilot (Phase 1 F1.8 + Phase 2 agentic mode).

  uv run python -m policy_copilot.cli                       # direct RAG, REPL
  uv run python -m policy_copilot.cli "question"            # direct RAG, one-shot
  uv run python -m policy_copilot.cli --agentic "question"  # agentic (Claude drives search)

Each question is answered with citations (or NOT FOUND) and a trace is recorded
to data/traces/traces.jsonl (+ Langfuse if configured).
"""

from __future__ import annotations

import sys

from policy_copilot.index import load_index


def _show(refused: bool, text: str, citations: list[str]) -> None:
    if refused:
        print("NOT FOUND")
        return
    print(text)
    if citations:
        print("sources:", ", ".join(citations))


def main() -> None:
    args = sys.argv[1:]
    agentic = args[:1] == ["--agentic"]
    if agentic:
        args = args[1:]
    index, chunks = load_index()

    def ask(question: str) -> None:
        if agentic:
            from policy_copilot.tool_agent import answer_agentic

            result = answer_agentic(question, index, chunks)
            _show(result.refused, result.text, result.citations)
            verified = result.verdict.citations_resolve and result.verdict.numbers_verbatim
            print(f"[agentic: {len(result.tool_calls)} search(es); verified={verified}]")
        else:
            from policy_copilot.agent import answer

            direct = answer(question, index, chunks)
            _show(direct.refused, direct.text, direct.citations)

    if args:  # one-shot
        ask(" ".join(args))
        return

    print(f"Policy Copilot ({'agentic' if agentic else 'direct'}) — ask away. Type 'exit' to quit.")
    while True:
        try:
            question = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not question or question.lower() in {"exit", "quit"}:
            break
        ask(question)


if __name__ == "__main__":
    main()
