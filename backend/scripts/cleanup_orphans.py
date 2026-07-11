"""Qdrant orphan-chunk cleanup + keepalive (spec E10 Req 1/9, ARCHITECTURE §9).

Two jobs in one script because both are "touch every store once a day" and
share the same connections:

1. **Keepalive** — Qdrant Cloud free clusters and Supabase free projects both
   pause after a period of inactivity; a cheap daily reachability probe
   (`get_collections()` / `SELECT 1`) is enough to keep them warm. This is the
   ₹0-cost tax for using free tiers (ARCHITECTURE §9), run from
   `.github/workflows/keepalive.yml` since there's no cron primitive in
   FastAPI/n8n cheaper than GitHub Actions' free scheduled runs.
2. **Orphan cleanup** — `delete_source_points` (ingestion) and the workspace/
   source DELETE routes purge Qdrant points best-effort (CLAUDE.md invariant
   #7: never let a Qdrant outage block a Postgres delete). When that purge
   silently fails, points survive in `helpflow_chunks` referencing a
   `source_id`/`tenant_id` that no longer exists in Postgres — dead weight
   that would otherwise pollute retrieval for a re-used tenant id. This
   scrolls the collection, diffs `source_id` against the live `sources`
   table, and deletes anything not accounted for.

Degrades, never breaks (CLAUDE.md invariant #7): either store being
unreachable logs and exits non-zero for the Action to surface, but the script
never partially deletes on best-effort information — it only deletes once it
has successfully read BOTH the full orphan candidate list and the full valid
id set.

Run: python -m backend.scripts.cleanup_orphans [--dry-run]
"""

from __future__ import annotations

import argparse
import asyncio
import logging

from backend.utils import supabase_client
from backend.utils.config import get_settings
from backend.utils.qdrant_client import QDRANT_TIMEOUT_S, get_qdrant

logging.basicConfig(level=logging.INFO)
_log = logging.getLogger("helpflow.cleanup_orphans")

_SCROLL_BATCH = 512


async def keepalive() -> None:
    """Cheap reachability pings — the whole point is traffic, not the result."""
    await asyncio.wait_for(get_qdrant().get_collections(), timeout=QDRANT_TIMEOUT_S)
    _log.info("qdrant keepalive ok")
    await asyncio.wait_for(supabase_client.ping(), timeout=supabase_client.DB_ACQUIRE_TIMEOUT_S)
    _log.info("supabase keepalive ok")


async def _all_source_ids_in_qdrant(collection: str) -> set[str]:
    """Scroll the whole collection collecting distinct `source_id` payload
    values. Payload-only (no vectors) keeps this cheap even at scale."""
    client = get_qdrant()
    seen: set[str] = set()
    offset = None
    while True:
        points, offset = await client.scroll(
            collection_name=collection,
            limit=_SCROLL_BATCH,
            offset=offset,
            with_payload=["source_id"],
            with_vectors=False,
        )
        for p in points:
            sid = (p.payload or {}).get("source_id")
            if sid:
                seen.add(str(sid))
        if offset is None:
            break
    return seen


async def _valid_source_ids() -> set[str]:
    rows = await supabase_client.fetch("SELECT id FROM sources")
    return {str(r["id"]) for r in rows}


async def _delete_orphans(collection: str, orphan_source_ids: set[str]) -> None:
    from qdrant_client import models

    await get_qdrant().delete(
        collection_name=collection,
        points_selector=models.Filter(
            must=[
                models.FieldCondition(
                    key="source_id", match=models.MatchAny(any=sorted(orphan_source_ids))
                )
            ]
        ),
    )


async def cleanup(dry_run: bool = False) -> int:
    """Returns the number of orphaned `source_id`s found (and, unless
    `dry_run`, deleted)."""
    collection = get_settings().QDRANT_COLLECTION
    present = await _all_source_ids_in_qdrant(collection)
    valid = await _valid_source_ids()
    orphans = present - valid

    if not orphans:
        _log.info("no orphans found", extra={"scanned_source_ids": len(present)})
        return 0

    _log.info(
        "orphan source_ids found",
        extra={"orphan_count": len(orphans), "orphan_source_ids": sorted(orphans)},
    )
    if dry_run:
        _log.info("--dry-run: not deleting")
        return len(orphans)

    await _delete_orphans(collection, orphans)
    _log.info("deleted orphan points", extra={"orphan_source_ids": sorted(orphans)})
    return len(orphans)


async def main(dry_run: bool) -> None:
    await keepalive()
    orphan_count = await cleanup(dry_run=dry_run)
    await supabase_client.close_pool()
    if orphan_count:
        _log.info("done", extra={"orphans_handled": orphan_count})
    else:
        _log.info("done: clean")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run", action="store_true", help="Report orphans without deleting"
    )
    args = parser.parse_args()
    asyncio.run(main(args.dry_run))
