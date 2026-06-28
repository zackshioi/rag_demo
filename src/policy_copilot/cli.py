"""Interactive CLI for Policy Copilot (Phase 1, F1.8).

  uv run python -m policy_copilot.cli                 # REPL
  uv run python -m policy_copilot.cli "your question" # one-shot

Each question is answered with citations (or NOT FOUND) and a trace is recorded
to data/traces/traces.jsonl — open notebooks/error_analysis.ipynb to review them.
"""

from __future__ import annotations

import sys

from policy_copilot.agent import Answer, answer
from policy_copilot.index import load_index


def _show(result: Answer) -> None:
    if result.refused:
        print("NOT FOUND")
    else:
        print(result.text)
        if result.citations:
            print("sources:", ", ".join(result.citations))


def main() -> None:
    index, chunks = load_index()
    args = sys.argv[1:]
    if args:  # one-shot mode
        _show(answer(" ".join(args), index, chunks))
        return

    print("Policy Copilot — ask about the indexed filings. Type 'exit' to quit.")
    while True:
        try:
            question = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not question or question.lower() in {"exit", "quit"}:
            break
        _show(answer(question, index, chunks))


if __name__ == "__main__":
    main()
