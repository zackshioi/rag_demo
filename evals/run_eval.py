"""Offline diagnose (EDD step 3): run the agent over the golden set and categorise.

For each golden case, run ``agent.answer`` and score the outcome against the
expected behaviour, then print a per-category summary and the failing cases.
Failures are the raw material for new golden cases / prompt fixes — the loop that
makes EDD *improve* rather than just *measure*. See EVALUATION.md.

Usage:  uv run python evals/run_eval.py [N]   # N = max cases (default: all)
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from policy_copilot.agent import answer
from policy_copilot.index import load_index

GOLDEN = Path("evals/golden.jsonl")


def _load() -> list[dict]:
    text = GOLDEN.read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def _classify(case: dict, res: Any) -> tuple[str, str]:
    """Map an answer to a diagnose category + a short note."""
    if case["type"] == "refusal":
        return ("ok", "") if res.refused else ("should_have_refused", res.text[:60])
    if res.refused:
        return "wrongly_refused", "agent said NOT FOUND"
    expected = case.get("expected_contains") or []
    if expected and not any(e in res.text for e in expected):
        return "missing_expected", f"want one of {expected}"
    if not res.citations:
        return "no_citation", res.text[:60]
    return "ok", ""


def main() -> None:
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 10**9
    cases = _load()
    answerable = [c for c in cases if c["type"] == "answerable"][: max(0, limit - 4)]
    refusals = [c for c in cases if c["type"] == "refusal"]
    sample = answerable + refusals

    index, chunks = load_index()
    counts: Counter[str] = Counter()
    failures: list[tuple[str, str, str, str]] = []
    for case in sample:
        res = answer(case["question"], index, chunks)
        category, note = _classify(case, res)
        counts[category] += 1
        if category != "ok":
            failures.append((case["id"], category, case["question"][:55], note))

    print(f"\n=== diagnose over {len(sample)} cases ===")
    for category, n in counts.most_common():
        print(f"  {category:20s} {n}")
    print("\n=== failures (-> next golden cases / prompt fixes) ===")
    for fid, category, question, note in failures:
        print(f"  [{fid}] {category}: {question}  -- {note}")


if __name__ == "__main__":
    main()
