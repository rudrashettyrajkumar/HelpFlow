"""Qdrant Cloud client — async singleton.

Ported from DocChat `utils/qdrant_client.py`. The async client is shared
process-wide (one HTTP connection pool) and built on first use, so the import
stays out of cold-start and off the import path of tests that don't need it.
Hard 2s timeout per call (errors degrade, never break — CLAUDE.md invariant #7).
"""

from typing import TYPE_CHECKING

from backend.utils.config import get_settings

if TYPE_CHECKING:
    from qdrant_client import AsyncQdrantClient

# Retrieval sits on the hot path; a slow/unreachable Qdrant must fail fast so the
# pipeline can degrade rather than hang. Default 2s is right for Railway->Qdrant
# (same-cloud); the actual value is `settings.QDRANT_TIMEOUT_S` (config.py) so
# local WSL dev (slower network path, and ingestion's bulk upserts aren't
# hot-path) can override it without touching prod's default.
QDRANT_TIMEOUT_S = 2

_client: "AsyncQdrantClient | None" = None


def get_qdrant() -> "AsyncQdrantClient":
    """Return the shared async Qdrant client, building it once."""
    global _client
    if _client is None:
        from qdrant_client import AsyncQdrantClient

        settings = get_settings()
        _client = AsyncQdrantClient(
            url=settings.QDRANT_URL,
            api_key=settings.QDRANT_API_KEY,
            timeout=settings.QDRANT_TIMEOUT_S,
        )
    return _client
