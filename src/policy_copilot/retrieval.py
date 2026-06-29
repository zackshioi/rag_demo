"""Retrieval backend selection — local FAISS (default) or Bedrock Knowledge Base.

The pipeline calls `retrieve(query, k)` and gets back `SearchHit`s either way;
only the *source* differs. Switch with `RETRIEVAL_BACKEND=kb` (+ `KB_ID`).

- **FAISS** (Phase 1): local bge-base index over our parsed chunks.
- **Bedrock KB** (Phase 4): managed chunk/embed/index in S3 Vectors. The `Retrieve`
  API returns excerpts with native source attribution (the S3 object); we map each
  to our `[DOC::NNNN]` citation id (doc = S3 filename stem) so the rest of the loop
  — refusal pre-check, prompt context, citation verifier — is unchanged.

Note: KB relevance scores are on a different scale than FAISS cosine, so
`REFUSAL_THRESHOLD` is FAISS-calibrated; revisit it for KB in Phase 6 tuning.
"""

from __future__ import annotations

import os
from pathlib import PurePosixPath
from typing import Any

from policy_copilot.chunking import Chunk
from policy_copilot.index import SearchHit, load_index
from policy_copilot.index import search as faiss_search

BACKEND = os.environ.get("RETRIEVAL_BACKEND", "faiss")
KB_ID = os.environ.get("KB_ID", "")
AWS_REGION = os.environ.get("AWS_REGION", "ap-southeast-2")

_FAISS: tuple[Any, list[Chunk]] | None = None


def retrieve(
    query: str,
    k: int = 5,
    index: Any = None,
    chunks: list[Chunk] | None = None,
) -> list[SearchHit]:
    """Top-k excerpts for a query, from the configured backend.

    Callers may pass a preloaded (index, chunks) to reuse across a batch (FAISS);
    otherwise the local index is loaded once and cached. Ignored in KB mode.
    """
    if BACKEND == "kb":
        return _kb_retrieve(query, k)
    global _FAISS
    if index is None or chunks is None:
        if _FAISS is None:
            _FAISS = load_index()
        index, chunks = _FAISS
    return faiss_search(index, chunks, query, k)


def _kb_retrieve(query: str, k: int) -> list[SearchHit]:
    """Query the Bedrock Knowledge Base and map results to SearchHits."""
    import boto3

    client = boto3.client("bedrock-agent-runtime", region_name=AWS_REGION)
    response = client.retrieve(
        knowledgeBaseId=KB_ID,
        retrievalQuery={"text": query},
        retrievalConfiguration={"vectorSearchConfiguration": {"numberOfResults": k}},
    )
    hits: list[SearchHit] = []
    for i, result in enumerate(response.get("retrievalResults", [])):
        text = (result.get("content") or {}).get("text", "")
        uri = ((result.get("location") or {}).get("s3Location") or {}).get("uri", "")
        doc_id = PurePosixPath(uri).stem or "KB"
        chunk = Chunk(chunk_id=f"{doc_id}::{i:04d}", doc_id=doc_id, heading="", text=text)
        hits.append(SearchHit(chunk=chunk, score=float(result.get("score", 0.0))))
    return hits
