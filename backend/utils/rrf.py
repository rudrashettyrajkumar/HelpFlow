"""Reciprocal Rank Fusion — the multi-query merge (ARCHITECTURE §3.2 STEP 3 / §5.4).

Ported verbatim from DocChat `utils/rrf.py`. Pure, dependency-free list math:
given several ranked result lists (one per Qdrant search, one per rewritten
query), fuse them into one ranking and return the top-k. No reranker, no
model, no I/O.

Rank-based, NOT score-based, on purpose: cosine scores across different query
searches are not directly comparable, but ranks always are. A chunk that
surfaces for more than one query accumulates score from each list and
naturally outranks a chunk seen for only one.
"""

from __future__ import annotations

from typing import Any, Protocol

# ARCHITECTURE §3.2 STEP 3 constants: k=60, fused top 6 chunks handed to the answerer.
RRF_K = 60
RRF_TOP_K = 6


class _HasId(Protocol):
    """Anything with a stable `id` — a Qdrant ScoredPoint or a test stub."""

    id: Any


def reciprocal_rank_fusion(
    result_lists: list[list[_HasId]],
    k: int = RRF_K,
    top_k: int = RRF_TOP_K,
) -> list[Any]:
    """Fuse ranked lists into one top-k ranking.

    ``score[id] += 1 / (k + rank + 1)`` accumulated across every list the chunk
    appears in (rank is 0-based within each list); chunks are de-duplicated by
    ``id``. Ties keep first-seen order (Python sort is stable). Empty lists and
    empty input are fine — an all-empty input returns ``[]``.
    """
    scores: dict[Any, float] = {}
    chunks: dict[Any, Any] = {}
    for results in result_lists:
        for rank, chunk in enumerate(results):
            scores[chunk.id] = scores.get(chunk.id, 0.0) + 1.0 / (k + rank + 1)
            chunks[chunk.id] = chunk
    ranked = sorted(scores, key=lambda cid: scores[cid], reverse=True)
    return [chunks[cid] for cid in ranked[:top_k]]
