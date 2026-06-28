"""Embedding + FAISS vector index (Phase 1, F1.4) and basic search (F1.5 seed).

Each chunk is embedded with a local sentence-transformers model (`bge-base`,
768-dim) — no data leaves the machine. Vectors are L2-normalised and stored in a
flat FAISS index, so inner-product search == cosine similarity (exact at our
scale of a few thousand chunks). Index + chunk metadata persist under `data/`.

bge models want a short instruction prefixed to the *query* (not the passages)
for retrieval — see `QUERY_INSTRUCTION`.

Heavy deps (torch via sentence-transformers, faiss) are imported lazily so the
offline test suite and linters don't need them loaded.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from policy_copilot.chunking import Chunk

EMBED_MODEL = "BAAI/bge-base-en-v1.5"
QUERY_INSTRUCTION = "Represent this sentence for searching relevant passages: "
INDEX_DIR = Path("data/financebench/index")

_model: Any = None


@dataclass(frozen=True)
class SearchHit:
    """A retrieved chunk with its similarity score."""

    chunk: Chunk
    score: float


def _model_instance() -> Any:
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer

        _model = SentenceTransformer(EMBED_MODEL)
    return _model


def _embed(texts: list[str]) -> Any:
    """Embed and L2-normalise a list of texts (returns a float32 ndarray)."""
    return _model_instance().encode(texts, normalize_embeddings=True, convert_to_numpy=True)


def build_index(chunks: list[Chunk]) -> Any:
    """Embed all chunks and build a flat cosine-similarity FAISS index."""
    import faiss

    vectors = _embed([c.text for c in chunks])
    index = faiss.IndexFlatIP(vectors.shape[1])
    index.add(vectors)
    return index


def search(index: Any, chunks: list[Chunk], query: str, k: int = 5) -> list[SearchHit]:
    """Return the top-k chunks most similar to the query."""
    vector = _embed([QUERY_INSTRUCTION + query])
    scores, ids = index.search(vector, k)
    hits: list[SearchHit] = []
    for score, idx in zip(scores[0], ids[0], strict=False):
        if int(idx) == -1:
            continue
        hits.append(SearchHit(chunk=chunks[int(idx)], score=float(score)))
    return hits


def save_index(index: Any, chunks: list[Chunk], index_dir: Path = INDEX_DIR) -> None:
    """Persist the FAISS index and chunk metadata to disk."""
    import faiss

    index_dir.mkdir(parents=True, exist_ok=True)
    faiss.write_index(index, str(index_dir / "faiss.index"))
    payload = [asdict(c) for c in chunks]
    (index_dir / "chunks.json").write_text(json.dumps(payload), encoding="utf-8")


def load_index(index_dir: Path = INDEX_DIR) -> tuple[Any, list[Chunk]]:
    """Load a persisted FAISS index and its chunk metadata."""
    import faiss

    index = faiss.read_index(str(index_dir / "faiss.index"))
    payload = json.loads((index_dir / "chunks.json").read_text(encoding="utf-8"))
    chunks = [Chunk(**c) for c in payload]
    return index, chunks


def main() -> None:
    """Build + persist the index over the lean subset and run demo searches."""
    from policy_copilot.chunking import chunk_filings
    from policy_copilot.financebench import build_corpus, load_rows, select_documents

    rows = load_rows()
    corpus = build_corpus(rows, select_documents(rows, n=8))
    chunks = chunk_filings(corpus)
    print(f"{len(corpus)} filings -> {len(chunks)} chunks")

    print("Embedding + building FAISS index (first run downloads the model)...")
    index = build_index(chunks)
    save_index(index, chunks)
    print(f"Index built: {index.ntotal} vectors\n")

    demos = [
        "What was AMD's total net revenue in fiscal 2022?",  # in corpus
        "What is the capital of France?",  # out of corpus -> should be weak
    ]
    for query in demos:
        print(f"Q: {query}")
        for hit in search(index, chunks, query, k=3):
            preview = " ".join(hit.chunk.text.split())[:90]
            print(f"  {hit.score:.3f}  [{hit.chunk.chunk_id}] {preview}")
        print()


if __name__ == "__main__":
    main()
