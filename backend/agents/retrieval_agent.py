"""Retrieval agent — multi-query embed + tenant-filtered Qdrant + RRF fusion.

ARCHITECTURE §3.2 STEP 3 / §5.1, spec E3 Req 5. Takes the rewrite agent's standalone
queries, embeds all of them in ONE batched call, runs a tenant-filtered Qdrant search
per query in parallel, fuses the ranked lists with `utils.rrf.reciprocal_rank_fusion`,
and returns the top 6 chunks numbered and labeled for citation.

The `tenant_id` payload filter is built in exactly ONE place in this module
(`_search_one`) — call sites never construct their own filter (CLAUDE.md invariant
#2, ARCHITECTURE §5.1). A test asserts the filter is present on every search call and
that tenant A cannot retrieve tenant B's chunks.

Errors degrade, never break (CLAUDE.md invariant #7): the embed call failing takes
down the whole batch (one request for all queries), so it degrades to empty chunks +
low_relevance; a single query's Qdrant search failing degrades to proceeding with
whichever queries succeeded; every search failing also degrades to empty chunks +
low_relevance. This agent never raises.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

from backend.utils.config import get_settings
from backend.utils.embeddings import EmbeddingError, embed
from backend.utils.qdrant_client import get_qdrant
from backend.utils.rrf import reciprocal_rank_fusion

_log = logging.getLogger("helpflow.retrieval_agent")

# Per-query candidate pool before fusion (ARCHITECTURE §3.2 STEP 3: "top-8/query").
_SEARCH_LIMIT_PER_QUERY = 8


@dataclass(frozen=True)
class RetrievedChunk:
    """One fused, citation-numbered chunk (spec Req 5)."""

    n: int  # 1-based citation number, stable across the fused ranking
    id: str
    source_id: str
    source_url: str
    page_title: str
    chunk_index: int
    text: str
    score: float
    citation_label: str


@dataclass(frozen=True)
class RetrievalResult:
    chunks: list[RetrievedChunk]
    low_relevance: bool


# Shared degraded-path result (never an exception out of the agent).
_EMPTY_RESULT = RetrievalResult(chunks=[], low_relevance=True)


def _citation_label(page_title: str, source_url: str) -> str:
    """`"{page_title} — {source_url}"` (ARCHITECTURE §3.2 STEP 3)."""
    title = page_title or source_url
    return f"{title} — {source_url}"


async def _search_one(vector: list[float], tenant_id: str, collection: str) -> list[Any]:
    """The ONE place the mandatory tenant_id filter is built (invariant #2)."""
    from qdrant_client import models

    return await get_qdrant().search(
        collection_name=collection,
        query_vector=vector,
        query_filter=models.Filter(
            must=[models.FieldCondition(key="tenant_id", match=models.MatchValue(value=tenant_id))]
        ),
        limit=_SEARCH_LIMIT_PER_QUERY,
    )


async def _search_all(
    vectors: list[list[float]], tenant_id: str, collection: str
) -> list[list[Any]]:
    """Run one filtered search per query vector in parallel.

    A failing search is logged and dropped, not propagated (a partial failure
    degrades to whatever succeeded).
    """
    results = await asyncio.gather(
        *(_search_one(vector, tenant_id, collection) for vector in vectors),
        return_exceptions=True,
    )
    lists: list[list[Any]] = []
    for result in results:
        if isinstance(result, Exception):
            _log.warning("qdrant search failed; degrading", extra={"error": str(result)})
            continue
        lists.append(result)
    return lists


def _to_chunk(point: Any, n: int) -> RetrievedChunk:
    payload = point.payload or {}
    page_title = payload.get("page_title", "")
    source_url = payload.get("source_url", "")
    return RetrievedChunk(
        n=n,
        id=str(point.id),
        source_id=payload.get("source_id", ""),
        source_url=source_url,
        page_title=page_title,
        chunk_index=payload.get("chunk_index", 0),
        text=payload.get("text", ""),
        score=point.score,
        citation_label=_citation_label(page_title, source_url),
    )


async def retrieve(queries: list[str], tenant_id: str) -> RetrievalResult:
    """Embed `queries`, search Qdrant filtered to `tenant_id`, fuse, and label.

    Never raises: any failure degrades to `RetrievalResult([], low_relevance=True)`.
    """
    if not queries:
        return _EMPTY_RESULT

    settings = get_settings()
    try:
        vectors = await embed(queries)
    except EmbeddingError as exc:
        _log.warning("query embedding failed; degrading", extra={"error": str(exc)})
        return _EMPTY_RESULT

    result_lists = await _search_all(vectors, tenant_id, settings.QDRANT_COLLECTION)
    if not result_lists:
        return _EMPTY_RESULT

    fused = reciprocal_rank_fusion(result_lists)
    if not fused:
        return _EMPTY_RESULT

    best_score = max(point.score for point in fused)
    low_relevance = best_score < settings.RELEVANCE_THRESHOLD

    chunks = [_to_chunk(point, n) for n, point in enumerate(fused, start=1)]
    return RetrievalResult(chunks=chunks, low_relevance=low_relevance)
