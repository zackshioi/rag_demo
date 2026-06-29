"""Build the evaluation golden set (``evals/golden.jsonl``).

Answerable cases come from FinanceBench rows whose ``doc_name`` is in our loaded
corpus (8 filings -> 40 rows), each carrying the gold ``answer`` and ``evidence``
(for RAGAS / correctness in Phase 6). Refusal (out-of-corpus) cases are
hand-authored and **preserved** from the existing golden file — FinanceBench has
none. This is the "auto-build from FinanceBench" half of how the golden set grows
(the other half is diagnose: real failures become new cases). See EVALUATION.md.

Run:  uv run python evals/build_golden.py
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from datasets import load_dataset

GOLDEN = Path("evals/golden.jsonl")
PDF_DIR = Path("data/financebench/pdfs")
DATASET_ID = "PatronusAI/financebench"
# Numeric tokens (e.g. "23,601", "$1.2 billion" -> "1.2", "44%") for deterministic checks.
_NUMBER = re.compile(r"\$?\d[\d,]*(?:\.\d+)?%?")


def _corpus_docs() -> set[str]:
    """The doc_names we actually loaded (one per PDF in the corpus)."""
    return {p.stem for p in PDF_DIR.glob("*.pdf")}


def _evidence_text(row: dict) -> str:
    """Join FinanceBench gold evidence snippets into one context string."""
    ev = row.get("evidence") or []
    texts = [e.get("evidence_text", "") for e in ev if isinstance(e, dict)]
    return "\n\n".join(t for t in texts if t).strip()


def _expected_contains(answer: str) -> list[str]:
    """Distinct numeric tokens from the gold answer (deterministic numeric check)."""
    seen: set[str] = set()
    out: list[str] = []
    for token in _NUMBER.findall(answer or ""):
        if len(token) > 1 and token not in seen:  # skip lone digits
            seen.add(token)
            out.append(token)
    return out[:5]


def _preserved_refusals() -> list[dict]:
    """Keep hand-authored out-of-corpus refusal cases from the current golden file."""
    if not GOLDEN.exists():
        return []
    text = GOLDEN.read_text(encoding="utf-8")
    rows = [json.loads(line) for line in text.splitlines() if line.strip()]
    return [r for r in rows if r.get("type") == "refusal"]


def build() -> list[dict]:
    """Assemble golden cases: FinanceBench answerable rows + preserved refusals."""
    docs = _corpus_docs()
    dataset = load_dataset(DATASET_ID, split="train")
    rows = sorted(
        (r for r in dataset if r.get("doc_name") in docs),
        key=lambda r: (r["doc_name"], r["question"]),
    )
    cases: list[dict] = [
        {
            "id": f"fb{i:03d}",
            "type": "answerable",
            "doc_name": row["doc_name"],
            "question": row["question"].strip(),
            "expected_contains": _expected_contains(row.get("answer", "")),
            "gold_answer": (row.get("answer") or "").strip(),
            "evidence": _evidence_text(row),
        }
        for i, row in enumerate(rows, 1)
    ]
    cases.extend(_preserved_refusals())
    return cases


def main() -> None:
    cases = build()
    GOLDEN.parent.mkdir(parents=True, exist_ok=True)
    with GOLDEN.open("w", encoding="utf-8") as fh:
        for case in cases:
            fh.write(json.dumps(case, ensure_ascii=False) + "\n")
    n_ans = sum(1 for c in cases if c["type"] == "answerable")
    n_ref = sum(1 for c in cases if c["type"] == "refusal")
    print(f"wrote {len(cases)} golden cases -> {GOLDEN} ({n_ans} answerable, {n_ref} refusal)")


if __name__ == "__main__":
    main()
