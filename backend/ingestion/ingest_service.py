"""Orchestrates discover → fetch/extract → chunk → embed → upsert, yielding
SSE-ready progress dicts (ARCHITECTURE §3.1, spec E2 Req 2-8).

Validation (bad url, over-cap `max_pages`, tenant rate limit) happens in
`api/admin_sources.py` BEFORE this generator starts, per the same
validation-before-streaming split DocChat used: every failure detectable up
front is a plain 4xx JSON response. Once this generator is running, the HTTP
response has already committed to `text/event-stream`, so the only way left
to report a failure is a terminal `{"stage": "error", ...}` event.

Unlike DocChat (one `doc_id` per upload), HelpFlow's crawl unit is the PAGE —
one `sources` row and one Qdrant `source_id` per URL (ARCHITECTURE §5.2). So:
  * fetch+extract+chunk run PER PAGE, concurrency-limited by a semaphore
    (spec Req 3, default 5);
  * embedding batches across ALL of this crawl's chunks together (spec Req 5:
    "batches of 100"), because that's what actually amortizes the embedding
    gateway's per-request overhead;
  * a rollback therefore targets every `source_id` touched by this crawl, via
    a `MatchAny` Qdrant filter (there is no `crawl_id` field in the §5.1
    payload to filter on directly) — every one of those `sources` rows is also
    flipped to `status='error'` so nothing is left stuck at `'crawling'`.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

from backend.ingestion.chunker import Chunk, chunk_page
from backend.ingestion.crawler import discover
from backend.ingestion.extractor import extract_page
from backend.llm.runconfig import DEFAULT, RunConfig
from backend.services import embed_signature
from backend.services.demo_budget import DemoBudgetExceeded
from backend.services.embed_signature import EmbeddingError
from backend.utils import supabase_client
from backend.utils.config import get_settings
from backend.utils.qdrant_client import get_qdrant

_DEMO_EXHAUSTED_DETAIL = (
    "HelpFlow's demo runs on shared free-tier keys and today's shared embedding "
    "quota is used up. It resets at midnight UTC — or add your own free Groq/"
    "OpenRouter key in Model Studio for unthrottled ingestion."
)

_log = logging.getLogger("helpflow.ingest_service")

# Fetch/extract concurrency (spec Req 3: "concurrency limited, default 5").
FETCH_CONCURRENCY = 5


@dataclass
class _PageResult:
    source_id: str
    url: str
    ok: bool
    title: str | None = None
    chunks: list[Chunk] = field(default_factory=list)
    error: str | None = None


def _point_id(source_id: str, chunk_index: int) -> str:
    """Deterministic point id (spec Req 6): UUID5 of the source + chunk index,
    so re-running ingestion for the same source_id/chunk_index overwrites
    cleanly (refresh)."""
    return str(uuid.uuid5(uuid.UUID(source_id), str(chunk_index)))


def _payload(chunk: Chunk, *, tenant_id: str, source_id: str, created_at: float) -> dict[str, Any]:
    """Exactly the fields ARCHITECTURE §5.1 specifies — no more, no less."""
    return {
        "tenant_id": tenant_id,
        "source_id": source_id,
        "source_url": chunk.source_url,
        "page_title": chunk.page_title,
        "chunk_index": chunk.chunk_index,
        "text": chunk.text,
        "created_at": created_at,
    }


async def delete_source_points(collection: str, source_ids: list[str]) -> None:
    """Remove every point for the given `source_id`s (spec Req 5 rollback,
    spec Req 7 refresh/delete). Best-effort: a second failure here (Qdrant
    itself unreachable) must not propagate — the caller still needs to yield
    its own terminal event (errors degrade, never break)."""
    from qdrant_client import models

    if not source_ids:
        return
    try:
        await get_qdrant().delete(
            collection_name=collection,
            points_selector=models.Filter(
                must=[
                    models.FieldCondition(
                        key="source_id", match=models.MatchAny(any=source_ids)
                    )
                ]
            ),
        )
    except Exception as exc:  # noqa: BLE001 — rollback is best-effort, never re-raises
        _log.warning(
            "rollback delete failed; some points may be orphaned",
            extra={"source_ids": source_ids, "error": str(exc)},
        )


async def _insert_source_row(tenant_id: str, url: str) -> str:
    source_id = str(uuid.uuid4())  # server-generated — never trust a client id
    await supabase_client.execute(
        "INSERT INTO sources (id, tenant_id, url, type, status) "
        "VALUES ($1, $2, $3, 'page', 'crawling')",
        source_id,
        tenant_id,
        url,
    )
    return source_id


async def _mark_ready(source_id: str, *, title: str, chunk_count: int) -> None:
    await supabase_client.execute(
        "UPDATE sources SET status='ready', title=$2, chunk_count=$3, "
        "crawled_at=now(), error=NULL WHERE id=$1",
        source_id,
        title,
        chunk_count,
    )


async def _mark_error(source_id: str, *, error: str) -> None:
    try:
        await supabase_client.execute(
            "UPDATE sources SET status='error', error=$2, crawled_at=now() WHERE id=$1",
            source_id,
            error,
        )
    except Exception as exc:  # noqa: BLE001 — already on a failure path; must not raise again
        _log.warning(
            "failed to record source error status",
            extra={"source_id": source_id, "error": str(exc)},
        )


async def _process_page(url: str, *, tenant_id: str, sem: asyncio.Semaphore) -> _PageResult:
    """Fetch+extract+chunk ONE page (spec Req 3/4). Any failure is recorded on
    that page's own `sources` row and returned as `ok=False` — never raises,
    so one bad page can never abort the whole crawl (spec Req 3)."""
    async with sem:
        source_id = await _insert_source_row(tenant_id, url)
        try:
            result = await extract_page(url)
        except Exception as exc:  # noqa: BLE001 — a single page's failure must degrade, not abort
            _log.warning("extraction raised unexpectedly", extra={"url": url, "error": str(exc)})
            result = None

        if result is None:
            await _mark_error(source_id, error="no extractable text")
            return _PageResult(source_id=source_id, url=url, ok=False, error="no extractable text")

        chunks = chunk_page(source_url=url, page_title=result.title, text=result.text)
        if not chunks:
            await _mark_error(source_id, error="no extractable text")
            return _PageResult(source_id=source_id, url=url, ok=False, error="no extractable text")

        return _PageResult(source_id=source_id, url=url, ok=True, title=result.title, chunks=chunks)


async def _abort_crawl(source_ids: list[str], *, reason: str) -> None:
    """Flip every touched `sources` row to `status='error'` after a rollback
    (spec Req 5: "no half-ingested tenant") — nothing is left at `'crawling'`."""
    for source_id in source_ids:
        await _mark_error(source_id, error=reason)


async def run_ingestion(
    *,
    tenant_id: str,
    url: str | None = None,
    sitemap_url: str | None = None,
    max_pages: int | None = None,
    cfg: RunConfig = DEFAULT,
) -> AsyncIterator[dict[str, Any]]:
    """Yield progress events per spec Req 8's exact shapes:

    `{"stage": "discovering"}` → `{"stage": "fetching", "done": N, "total": M}`
    (once per completed page) → `{"stage": "embedding", "pct": P}` (once per
    embed batch) → terminal `{"stage": "ready", "pages", "chunks"}` or
    `{"stage": "error", "detail"}`.

    Embeds through the BYOK factory (spec E4 Req 7): `cfg`'s embed selection
    (or the demo env default) is resolved ONCE for the whole crawl — the
    embed-space MISMATCH check (409, before any streaming) already happened
    in `api/admin_sources.py`, so this generator only needs to embed and, on
    full success, pin the tenant to whatever selection it used.
    """
    settings = get_settings()
    collection = settings.QDRANT_COLLECTION
    cap = max_pages if max_pages is not None else settings.MAX_PAGES
    selection = embed_signature.request_selection(cfg)
    is_demo = embed_signature.is_demo_embed(cfg)

    yield {"stage": "discovering"}
    urls = await discover(url or sitemap_url or "", sitemap_url=sitemap_url, max_pages=cap)

    total = len(urls)
    if total == 0:
        yield {"stage": "error", "detail": "No crawlable pages were found at that URL."}
        return

    sem = asyncio.Semaphore(FETCH_CONCURRENCY)
    tasks = [asyncio.ensure_future(_process_page(u, tenant_id=tenant_id, sem=sem)) for u in urls]

    results: list[_PageResult] = []
    done = 0
    for task in asyncio.as_completed(tasks):
        results.append(await task)
        done += 1
        yield {"stage": "fetching", "done": done, "total": total}

    ok_results = [r for r in results if r.ok]
    all_chunks: list[tuple[_PageResult, Chunk]] = [(r, c) for r in ok_results for c in r.chunks]

    if not all_chunks:
        # Every page failed extraction. Each failure is already recorded on
        # its own sources row (spec Req 3: degrade, continue) — a crawl that
        # discovers pages but extracts nothing usable is a completed (empty)
        # crawl, not a hard error.
        yield {"stage": "ready", "pages": total, "chunks": 0}
        return

    created_at = time.time()
    batch_size = settings.EMBED_BATCH_SIZE
    total_chunks = len(all_chunks)
    embedded = 0
    touched_source_ids: set[str] = set()

    for start in range(0, total_chunks, batch_size):
        batch = all_chunks[start : start + batch_size]
        texts = [c.text for _, c in batch]

        try:
            vectors = await embed_signature.embed(texts, selection, is_demo=is_demo)
        except DemoBudgetExceeded:
            _log.info(
                "demo embed budget exhausted; rolling back crawl", extra={"tenant_id": tenant_id}
            )
            await delete_source_points(collection, list(touched_source_ids))
            await _abort_crawl(
                [r.source_id for r in ok_results], reason="demo embed budget exhausted"
            )
            yield {"stage": "error", "detail": _DEMO_EXHAUSTED_DETAIL}
            return
        except EmbeddingError:
            try:
                vectors = await embed_signature.embed(
                    texts, selection, is_demo=is_demo
                )  # one retry, spec Req 5
            except DemoBudgetExceeded:
                await delete_source_points(collection, list(touched_source_ids))
                await _abort_crawl(
                    [r.source_id for r in ok_results], reason="demo embed budget exhausted"
                )
                yield {"stage": "error", "detail": _DEMO_EXHAUSTED_DETAIL}
                return
            except EmbeddingError as exc:
                _log.warning(
                    "embedding failed twice; rolling back crawl", extra={"tenant_id": tenant_id}
                )
                await delete_source_points(collection, list(touched_source_ids))
                await _abort_crawl(
                    [r.source_id for r in ok_results], reason=f"embedding failed: {exc}"
                )
                yield {"stage": "error", "detail": f"Embedding failed: {exc}"}
                return

        from qdrant_client import models

        points = [
            models.PointStruct(
                id=_point_id(page.source_id, chunk.chunk_index),
                vector=vector,
                payload=_payload(
                    chunk, tenant_id=tenant_id, source_id=page.source_id, created_at=created_at
                ),
            )
            for (page, chunk), vector in zip(batch, vectors, strict=True)
        ]

        try:
            await get_qdrant().upsert(collection_name=collection, points=points)
        except Exception as exc:  # noqa: BLE001 — any upsert failure must roll back cleanly
            _log.warning("upsert failed; rolling back crawl", extra={"tenant_id": tenant_id})
            await delete_source_points(collection, list(touched_source_ids))
            await _abort_crawl(
                [r.source_id for r in ok_results], reason=f"storage failed: {exc}"
            )
            yield {"stage": "error", "detail": f"Storage failed: {exc}"}
            return

        touched_source_ids.update(page.source_id for page, _ in batch)
        embedded += len(batch)
        pct = int(100 * embedded / total_chunks) if total_chunks else 100
        yield {"stage": "embedding", "pct": pct}

    # All batches succeeded — mark every ingested page's sources row ready.
    # A page's chunks may span more than one embed batch, so this only
    # happens once we know the WHOLE crawl succeeded.
    chunk_counts: dict[str, int] = {}
    titles: dict[str, str] = {}
    for page, _chunk in all_chunks:
        chunk_counts[page.source_id] = chunk_counts.get(page.source_id, 0) + 1
        titles[page.source_id] = page.title or page.url
    for source_id, count in chunk_counts.items():
        await _mark_ready(source_id, title=titles[source_id], chunk_count=count)

    # The FIRST successful ingest pins the tenant's embedding space (spec Req 7,
    # ARCHITECTURE §4.5); re-setting the same pin on later crawls is a no-op.
    await embed_signature.pin(tenant_id, selection)

    yield {"stage": "ready", "pages": total, "chunks": total_chunks}


async def run_refresh(
    *, tenant_id: str, source_id: str, url: str, cfg: RunConfig = DEFAULT
) -> dict[str, Any]:
    """Re-crawl a single already-known source: delete its Qdrant points, then
    re-fetch/extract/chunk/embed/upsert just that one URL (spec Req 7).

    Synchronous (no SSE) — a single page is fast enough that a plain JSON
    response is simpler than a one-event stream, and the interface table
    (§7.1) doesn't require SSE for refresh, only for the initial crawl. Embeds
    in the tenant's PINNED space (`query_selection`), not whatever the
    request currently has selected — a refresh must never silently create a
    second embedding space for one source.
    """
    settings = get_settings()
    collection = settings.QDRANT_COLLECTION

    await delete_source_points(collection, [source_id])

    result = await extract_page(url)
    if result is None:
        await _mark_error(source_id, error="no extractable text")
        return {"status": "error", "detail": "no extractable text"}

    chunks = chunk_page(source_url=url, page_title=result.title, text=result.text)
    if not chunks:
        await _mark_error(source_id, error="no extractable text")
        return {"status": "error", "detail": "no extractable text"}

    created_at = time.time()
    texts = [c.text for c in chunks]
    selection = await embed_signature.query_selection(tenant_id, cfg)
    is_demo = embed_signature.is_demo_embed(cfg)
    try:
        vectors = await embed_signature.embed(texts, selection, is_demo=is_demo)
    except DemoBudgetExceeded:
        await _mark_error(source_id, error="demo embed budget exhausted")
        return {"status": "error", "detail": _DEMO_EXHAUSTED_DETAIL}
    except EmbeddingError:
        try:
            vectors = await embed_signature.embed(texts, selection, is_demo=is_demo)
        except DemoBudgetExceeded:
            await _mark_error(source_id, error="demo embed budget exhausted")
            return {"status": "error", "detail": _DEMO_EXHAUSTED_DETAIL}
        except EmbeddingError as exc:
            await _mark_error(source_id, error=f"embedding failed: {exc}")
            return {"status": "error", "detail": str(exc)}

    from qdrant_client import models

    points = [
        models.PointStruct(
            id=_point_id(source_id, chunk.chunk_index),
            vector=vector,
            payload=_payload(
                chunk, tenant_id=tenant_id, source_id=source_id, created_at=created_at
            ),
        )
        for chunk, vector in zip(chunks, vectors, strict=True)
    ]
    try:
        await get_qdrant().upsert(collection_name=collection, points=points)
    except Exception as exc:  # noqa: BLE001 — a failed re-ingest must not corrupt the row
        await _mark_error(source_id, error=f"storage failed: {exc}")
        return {"status": "error", "detail": str(exc)}

    await _mark_ready(source_id, title=result.title, chunk_count=len(chunks))
    return {"status": "ready", "chunks": len(chunks)}
