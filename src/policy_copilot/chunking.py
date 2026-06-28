"""Structure-aware chunking (Phase 1, F1.3).

Splits a parsed filing (Markdown) into retrievable passages. We pack whole
paragraphs up to a target size (so words/sentences are never cut mid-way) and
carry a small overlap into the next chunk so an answer straddling a boundary is
not lost. Each chunk remembers its `doc_id` and the nearest Markdown heading,
so a retrieved answer can cite "AMD_2022_10K · Revenue".

Target size is in characters (~4 chars/token), kept well under the embedding
model's 512-token limit (~1,600 chars ≈ 400 tokens).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from policy_copilot.financebench import Filing

_PARAGRAPH = re.compile(r"\n\s*\n")


@dataclass(frozen=True)
class Chunk:
    """One retrievable passage."""

    chunk_id: str  # f"{doc_id}::{index:04d}"
    doc_id: str
    heading: str  # nearest preceding Markdown heading (for citations)
    text: str


def chunk_text(
    doc_id: str, text: str, target_chars: int = 1600, overlap_chars: int = 240
) -> list[Chunk]:
    """Split one document's Markdown into overlapping, paragraph-aligned chunks."""
    paragraphs = [p.strip() for p in _PARAGRAPH.split(text) if p.strip()]
    chunks: list[Chunk] = []
    current: list[str] = []
    current_len = 0
    heading = ""

    def emit() -> None:
        if not current:
            return
        chunks.append(
            Chunk(
                chunk_id=f"{doc_id}::{len(chunks):04d}",
                doc_id=doc_id,
                heading=heading,
                text="\n\n".join(current),
            )
        )

    for para in paragraphs:
        if para.lstrip().startswith("#"):
            heading = para.lstrip("# ").strip()[:120]
        if current and current_len + len(para) > target_chars:
            emit()
            # carry a small tail forward as overlap
            tail: list[str] = []
            tail_len = 0
            for prev in reversed(current):
                if tail_len + len(prev) > overlap_chars:
                    break
                tail.insert(0, prev)
                tail_len += len(prev)
            current = tail
            current_len = tail_len
        current.append(para)
        current_len += len(para) + 2

    emit()
    return chunks


def chunk_filings(filings: list[Filing]) -> list[Chunk]:
    """Chunk a whole corpus of filings into one flat list."""
    out: list[Chunk] = []
    for filing in filings:
        out.extend(chunk_text(filing.doc_id, filing.text))
    return out
