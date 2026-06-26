"""Dataset loading and corpus construction (Phase 1, F1.1 + F1.2).

Source: HuggingFace ``llmware/rag_instruct_benchmark_tester`` — 200 enterprise
Q&A rows. Each row: ``query``, ``answer``, ``context``, ``category``
(+ ``sample_number``, ``tokens``).

The inline ``context`` column is reused two ways (the "dual-use" trick, PRD §10):
1. deduplicated into the document corpus the retriever searches (``build_corpus``);
2. kept per-row as gold context for retrieval evaluation (Phase 6).
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any

from datasets import load_dataset

DATASET_ID = "llmware/rag_instruct_benchmark_tester"

# Real category labels in the dataset, mapped to the role each plays in our
# governance evals (verified against the data — names differ from early PRD draft).
CATEGORY_CORE = "core"  # baseline accuracy + faithfulness
CATEGORY_NOT_FOUND = "not_found_classification"  # refusal precision (key trust metric)
CATEGORY_BOOLEAN = "boolean"  # yes/no faithfulness
CATEGORY_MATH = "math_basic"  # numeric correctness within tolerance
CATEGORY_COMPLEX = "complex_qa"  # multi-fact reasoning
CATEGORY_SUMMARY = "summary"  # summarisation grounding


@dataclass(frozen=True)
class Document:
    """One deduplicated source document in the corpus."""

    doc_id: str
    text: str


def load_rows() -> list[dict[str, Any]]:
    """Load the 200 benchmark rows as plain dicts."""
    dataset = load_dataset(DATASET_ID)["train"]
    return [dict(row) for row in dataset]


def category_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    """Count rows per category."""
    return dict(Counter(str(row["category"]) for row in rows))


def build_corpus(rows: list[dict[str, Any]]) -> list[Document]:
    """Deduplicate the ``context`` column into the document corpus.

    Preserves first-occurrence order and assigns stable zero-padded ids
    (``doc_000``, ``doc_001``, ...) so citations are reproducible.
    """
    seen: set[str] = set()
    docs: list[Document] = []
    for row in rows:
        context = str(row["context"])
        if context in seen:
            continue
        seen.add(context)
        docs.append(Document(doc_id=f"doc_{len(docs):03d}", text=context))
    return docs


def main() -> None:
    """Print a human-readable summary of the dataset and corpus."""
    rows = load_rows()
    print(f"Loaded {len(rows)} rows from {DATASET_ID}\n")

    print("Categories:")
    for category, count in sorted(category_counts(rows).items(), key=lambda kv: -kv[1]):
        print(f"  {count:>3}  {category}")

    corpus = build_corpus(rows)
    print(f"\nCorpus after dedup: {len(corpus)} unique documents")

    sample = corpus[0]
    preview = " ".join(sample.text.split())[:200]
    print(f"\nSample document [{sample.doc_id}]:\n  {preview} ...")


if __name__ == "__main__":
    main()
