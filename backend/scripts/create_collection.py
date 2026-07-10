"""Idempotent Qdrant collection + payload-index setup (spec E1 Req 3,
ARCHITECTURE §5.1).

Run standalone (`python -m backend.scripts.create_collection`) or awaited from
`main.py`'s startup lifespan (Req 3: "called on startup too") — either way it's
a no-op once the collection and its indexes already exist.

`helpflow_chunks`: 768-dim cosine, with payload indexes on `tenant_id`
(tenant-isolation filter — the choke point every search carries), `source_id`
(per-source re-crawl/delete), and `created_at` (numeric range for cleanup crons).
"""

from __future__ import annotations

import asyncio
import logging

from backend.services.embed_signature import EMBED_DIM
from backend.utils.config import get_settings
from backend.utils.qdrant_client import get_qdrant

_log = logging.getLogger("helpflow.create_collection")

# ARCHITECTURE §5.1: tenant_id/source_id are exact-match keyword filters (tenant
# isolation, per-source delete); created_at is a numeric range filter (crons).
_KEYWORD_FIELDS = ("tenant_id", "source_id")
_NUMERIC_FIELDS = ("created_at",)


async def ensure_collection() -> None:
    from qdrant_client import models

    client = get_qdrant()
    name = get_settings().QDRANT_COLLECTION

    if not await client.collection_exists(name):
        await client.create_collection(
            collection_name=name,
            vectors_config=models.VectorParams(
                size=EMBED_DIM, distance=models.Distance.COSINE
            ),
        )
        _log.info("created collection", extra={"collection": name})

    indexes = [(f, models.PayloadSchemaType.KEYWORD) for f in _KEYWORD_FIELDS]
    indexes += [(f, models.PayloadSchemaType.FLOAT) for f in _NUMERIC_FIELDS]
    for field, schema in indexes:
        try:
            await client.create_payload_index(
                collection_name=name, field_name=field, field_schema=schema
            )
        except Exception as exc:  # noqa: BLE001 — "index already exists" is the common case
            _log.debug(
                "payload index already present", extra={"field": field, "error": str(exc)}
            )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(ensure_collection())
