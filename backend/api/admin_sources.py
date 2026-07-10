"""`POST/GET/POST refresh/DELETE /admin/sources` (spec E2 Req 1/6/7/8,
ARCHITECTURE §3.1/§7.1).

**Validation-before-streaming split** (ported from DocChat `api/documents.py`):
every check that can be settled BEFORE any real work — URL shape, `max_pages`
cap, tenant crawl-job rate limit — runs synchronously and returns a plain JSON
`{error, detail}` body with a real HTTP status code (spec Req 1). Only once
all of that has passed does the endpoint commit to `text/event-stream`; from
then on the only way left to report a failure is the SSE stream's own
terminal `{"stage": "error"}` event.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from backend.channels import conversation_store
from backend.ingestion.errors import IngestValidationError
from backend.ingestion.ingest_service import (
    delete_source_points,
    run_ingestion,
    run_refresh,
)
from backend.llm.runconfig import BYOKError, RunConfig, from_headers
from backend.middleware.rate_limit import check_and_increment_tenant_crawl
from backend.middleware.tenant_auth import require_admin_tenant
from backend.services import embed_signature
from backend.utils import supabase_client
from backend.utils.config import get_settings
from backend.utils.sse import format_event

router = APIRouter()
_log = logging.getLogger("helpflow.api.admin_sources")


def _parse_cfg(request: Request) -> RunConfig:
    """The request's BYOK embed selection (spec E4 Req 3/7) — rejected as 422
    before any crawl work, same validation-before-streaming split as the rest
    of this module."""
    try:
        return from_headers(request.headers)
    except BYOKError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc


async def _check_embed_pin(tenant_id: str, cfg: RunConfig) -> None:
    """409 `embed_mismatch` BEFORE any streaming (spec E4 Req 7, ARCHITECTURE
    §4.5): a tenant's whole corpus lives in ONE embedding space — a crawl
    asking for a different provider/model than the existing pin must be
    rejected up front, not half-ingested into a second space."""
    existing = await embed_signature.get_pin(tenant_id)
    if existing is None:
        return
    requested = embed_signature.signature(embed_signature.request_selection(cfg))
    if existing != requested:
        raise IngestValidationError(
            "embed_mismatch",
            f"This workspace's knowledge base was built with {existing!r}; "
            f"{requested!r} would start a second, incompatible space. "
            "Re-crawl from scratch to switch embedding models, or select "
            f"{existing!r} in Model Studio.",
            status_code=409,
        )


class CreateSourceRequest(BaseModel):
    url: str | None = None
    sitemap_url: str | None = None
    max_pages: int | None = None


def _is_valid_http_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


def _validate_create(body: CreateSourceRequest) -> None:
    target = body.sitemap_url or body.url
    if not target:
        raise IngestValidationError(
            "missing_url", "Provide either `url` or `sitemap_url`.", status_code=400
        )
    if not _is_valid_http_url(target):
        raise IngestValidationError(
            "invalid_url", f"{target!r} is not a valid http(s) URL.", status_code=400
        )
    max_pages = get_settings().MAX_PAGES
    if body.max_pages is not None:
        if body.max_pages < 1 or body.max_pages > max_pages:
            raise IngestValidationError(
                "max_pages_exceeded",
                f"max_pages must be between 1 and {max_pages}.",
                status_code=400,
            )


async def _stream_ingestion(
    *,
    tenant_id: str,
    url: str | None,
    sitemap_url: str | None,
    max_pages: int | None,
    cfg: RunConfig,
    trial_clamped: bool,
) -> AsyncIterator[str]:
    if trial_clamped:
        # Additive to the ingestion SSE vocabulary (this stream isn't FROZEN —
        # only chat/stream is, invariant #10): a friendly heads-up BEFORE
        # "discovering", never a raw truncation the owner has to guess at
        # (spec Req 4, ARCHITECTURE §5.3).
        yield format_event(
            "progress",
            {
                "stage": "info",
                "note": f"Trial workspaces crawl up to {get_settings().MAX_TRIAL_PAGES} pages. "
                "Upgrade to lift the cap.",
            },
        )
    async for event in run_ingestion(
        tenant_id=tenant_id, url=url, sitemap_url=sitemap_url, max_pages=max_pages, cfg=cfg
    ):
        yield format_event("progress", event)


@router.post("/admin/sources", response_model=None)
async def create_source(
    body: CreateSourceRequest,
    request: Request,
    tenant_id: str = Depends(require_admin_tenant),
) -> StreamingResponse | JSONResponse:
    cfg = _parse_cfg(request)
    try:
        _validate_create(body)
        await check_and_increment_tenant_crawl(tenant_id)
        await _check_embed_pin(tenant_id, cfg)
    except IngestValidationError as exc:
        return JSONResponse(
            status_code=exc.status_code, content={"error": exc.error, "detail": exc.detail}
        )

    settings = get_settings()
    tenant = await conversation_store.get_tenant(tenant_id)
    is_trial = bool(tenant and tenant.get("plan") == "trial")
    requested = body.max_pages if body.max_pages is not None else settings.MAX_PAGES
    effective_max_pages = min(requested, settings.MAX_TRIAL_PAGES) if is_trial else requested
    trial_clamped = is_trial and effective_max_pages < requested

    return StreamingResponse(
        _stream_ingestion(
            tenant_id=tenant_id,
            url=body.url,
            sitemap_url=body.sitemap_url,
            max_pages=effective_max_pages,
            cfg=cfg,
            trial_clamped=trial_clamped,
        ),
        media_type="text/event-stream",
    )


@router.get("/admin/sources")
async def list_sources(tenant_id: str = Depends(require_admin_tenant)) -> list[dict]:
    rows = await supabase_client.fetch(
        "SELECT id, url, title, status, chunk_count, crawled_at, error "
        "FROM sources WHERE tenant_id = $1 ORDER BY crawled_at DESC NULLS FIRST",
        tenant_id,
    )
    return [
        {
            "id": str(row["id"]),
            "url": row["url"],
            "title": row["title"],
            "status": row["status"],
            "chunk_count": row["chunk_count"],
            "crawled_at": row["crawled_at"].isoformat() if row["crawled_at"] else None,
            "error": row["error"],
        }
        for row in rows
    ]


async def _load_owned_source(source_id: str, tenant_id: str) -> dict:
    """404 for both "never existed" and "belongs to another tenant" — a 403
    would leak whether the source_id exists in someone else's tenant."""
    row = await supabase_client.fetchrow(
        "SELECT id, tenant_id, url FROM sources WHERE id = $1", source_id
    )
    if row is None or str(row["tenant_id"]) != tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Source not found.")
    return {"id": str(row["id"]), "url": row["url"]}


@router.post("/admin/sources/{source_id}/refresh")
async def refresh_source(
    source_id: str, tenant_id: str = Depends(require_admin_tenant)
) -> dict:
    source = await _load_owned_source(source_id, tenant_id)
    return await run_refresh(tenant_id=tenant_id, source_id=source["id"], url=source["url"])


@router.delete("/admin/sources/{source_id}")
async def delete_source(
    source_id: str, tenant_id: str = Depends(require_admin_tenant)
) -> dict:
    source = await _load_owned_source(source_id, tenant_id)
    await delete_source_points(get_settings().QDRANT_COLLECTION, [source["id"]])
    await supabase_client.execute("DELETE FROM sources WHERE id = $1", source["id"])
    # Releases the tenant's embed-space pin once they have no `ready` sources
    # left (spec E4 Req 7, ARCHITECTURE §4.5) — best-effort, never blocks the delete.
    await embed_signature.release_if_empty(tenant_id)
    return {"deleted": True}
