"""FinanceBench corpus: real 10-K/10-Q/8-K filings (Phase 1, F1.1+F1.2 upgrade).

Source: HuggingFace ``PatronusAI/financebench`` — 150 expert-written Q&A rows over
real SEC filings, with ``evidence`` (gold supporting text) and ``doc_name`` pointing
to a source PDF. License: CC-BY-NC-4.0 (demonstrator use only; not for production).

For a lean demo we take a subset of documents (most-questioned first), download their
PDFs from the FinanceBench GitHub repo, and parse them to Markdown with pymupdf4llm.
Parsed text is cached under ``data/financebench/parsed`` so re-runs are instant.

Dual-use (PRD §10) still holds: the full filings are the corpus to search; the per-row
``evidence`` is gold context for retrieval evaluation (Phase 6).
"""

from __future__ import annotations

import urllib.request
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pymupdf
import pymupdf4llm
from datasets import load_dataset

DATASET_ID = "PatronusAI/financebench"
PDF_BASE_URL = "https://raw.githubusercontent.com/patronus-ai/financebench/main/pdfs/"

DATA_DIR = Path("data/financebench")
PDF_DIR = DATA_DIR / "pdfs"
PARSED_DIR = DATA_DIR / "parsed"


@dataclass(frozen=True)
class Filing:
    """One parsed source filing in the corpus."""

    doc_id: str  # = doc_name, e.g. "AMD_2022_10K"
    company: str
    doc_type: str
    n_pages: int
    text: str  # parsed Markdown of the full filing


def load_rows() -> list[dict[str, Any]]:
    """Load the 150 FinanceBench Q&A rows as plain dicts."""
    dataset = load_dataset(DATASET_ID)["train"]
    return [dict(row) for row in dataset]


def select_documents(rows: list[dict[str, Any]], n: int = 8) -> list[str]:
    """Pick the ``n`` documents with the most questions (ties: alphabetical)."""
    counts = Counter(str(row["doc_name"]) for row in rows)
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    return [name for name, _ in ranked[:n]]


def questions_for(rows: list[dict[str, Any]], doc_names: list[str]) -> list[dict[str, Any]]:
    """The eval rows whose source document is in the subset (the 'exam')."""
    keep = set(doc_names)
    return [row for row in rows if str(row["doc_name"]) in keep]


def download_pdf(doc_name: str, dest_dir: Path = PDF_DIR) -> Path:
    """Download a filing PDF if not already cached; return its local path."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    path = dest_dir / f"{doc_name}.pdf"
    if not path.exists():
        urllib.request.urlretrieve(PDF_BASE_URL + f"{doc_name}.pdf", str(path))
    return path


def parse_filing(doc_name: str, rows_by_doc: dict[str, dict[str, Any]]) -> Filing:
    """Download + parse one filing to Markdown (cached on disk)."""
    PARSED_DIR.mkdir(parents=True, exist_ok=True)
    md_path = PARSED_DIR / f"{doc_name}.md"
    pdf_path = download_pdf(doc_name)
    n_pages = pymupdf.open(str(pdf_path)).page_count  # type: ignore[no-untyped-call]
    if md_path.exists():
        text = md_path.read_text(encoding="utf-8")
    else:
        text = pymupdf4llm.to_markdown(str(pdf_path))
        md_path.write_text(text, encoding="utf-8")
    meta = rows_by_doc[doc_name]
    return Filing(
        doc_id=doc_name,
        company=str(meta["company"]),
        doc_type=str(meta["doc_type"]),
        n_pages=n_pages,
        text=text,
    )


def build_corpus(rows: list[dict[str, Any]], doc_names: list[str]) -> list[Filing]:
    """Build the document corpus (one Filing per selected document)."""
    rows_by_doc = {str(row["doc_name"]): row for row in rows}
    return [parse_filing(name, rows_by_doc) for name in doc_names]


def main() -> None:
    """Download + parse the lean subset and print a corpus summary."""
    rows = load_rows()
    doc_names = select_documents(rows, n=8)
    questions = questions_for(rows, doc_names)
    print(f"Selected {len(doc_names)} documents covering {len(questions)} questions")
    print("Parsing (download + pymupdf4llm; cached after first run)...\n")

    corpus = build_corpus(rows, doc_names)
    for f in corpus:
        print(f"  {f.doc_id:30} {f.company[:18]:18} {f.n_pages:>4} pages  {len(f.text):>9,} chars")

    total_pages = sum(f.n_pages for f in corpus)
    total_chars = sum(len(f.text) for f in corpus)
    print(f"\nCorpus: {len(corpus)} filings, {total_pages} pages, {total_chars:,} chars")

    sample = corpus[0]
    print(f"\nSample from [{sample.doc_id}] (first 400 chars of Markdown):\n")
    print(sample.text[:400])


if __name__ == "__main__":
    main()
