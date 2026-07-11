"""Seed a demo tenant and crawl a real public docs/help site into it (spec E2
deliverable) — gives the E5/E6 demo something real to answer questions about.

Idempotent tenant lookup-by-name so re-running doesn't fork duplicate demo
tenants; the crawl itself is exactly `run_ingestion` (spec Req 2-6), so this
script doubles as a live smoke test of the whole ingestion pipeline.

Run: python -m backend.scripts.seed_demo_tenant --url https://example-docs.site --max-pages 20
"""

from __future__ import annotations

import argparse
import asyncio
import logging

from backend.ingestion.ingest_service import run_ingestion
from backend.scripts.create_collection import ensure_collection
from backend.utils import supabase_client

logging.basicConfig(level=logging.INFO)
_log = logging.getLogger("helpflow.seed_demo_tenant")


async def _get_or_create_tenant(name: str, website_url: str) -> str:
    row = await supabase_client.fetchrow("SELECT id FROM tenants WHERE name = $1", name)
    if row is not None:
        return str(row["id"])
    # plan='demo' explicitly (E5, ARCHITECTURE §5.2): this tenant has no
    # owner_user_id, so the column DEFAULT ('trial') would mislabel it as a
    # customer's trial workspace rather than Raj's own seeded demo.
    row = await supabase_client.fetchrow(
        "INSERT INTO tenants (name, website_url, plan) VALUES ($1, $2, 'demo') RETURNING id",
        name,
        website_url,
    )
    assert row is not None
    return str(row["id"])


async def seed(*, name: str, url: str, max_pages: int) -> tuple[str, int, int]:
    await ensure_collection()
    tenant_id = await _get_or_create_tenant(name, url)
    _log.info("seeding demo tenant", extra={"tenant_id": tenant_id, "tenant_name": name, "url": url})

    pages = chunks = 0
    async for event in run_ingestion(tenant_id=tenant_id, url=url, max_pages=max_pages):
        _log.info("progress", extra=event)
        if event.get("stage") == "ready":
            pages, chunks = event["pages"], event["chunks"]
        elif event.get("stage") == "error":
            raise SystemExit(f"demo crawl failed: {event.get('detail')}")

    print(f"tenant_id={tenant_id} name={name!r} url={url} pages={pages} chunks={chunks}")
    return tenant_id, pages, chunks


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name", default="HelpFlow Demo")
    parser.add_argument("--url", required=True, help="Docs/help site to crawl")
    parser.add_argument("--max-pages", type=int, default=20)
    args = parser.parse_args()
    asyncio.run(seed(name=args.name, url=args.url, max_pages=args.max_pages))


if __name__ == "__main__":
    main()
