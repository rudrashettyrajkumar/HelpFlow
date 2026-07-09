"""Batched embeddings — the canonical gateway, shared by ingestion and retrieval.

Ported from MyShiva `utils/embeddings.py`. Ingestion (E2) and query embedding
(E3) MUST use the SAME `gemini-embedding-001` model at 768 dims, served VIA
OpenRouter — mixing models or gateways puts the two vectors in different spaces
and silently wrecks retrieval, so every provider quirk lives HERE, in one place.

OpenRouter gotcha: POST OpenRouter's OpenAI-compatible `/embeddings` with raw
httpx, sending `dimensions=768`. litellm rejects `dimensions` for `openrouter/*`
(would silently return full-dim vectors) and the openai SDK defaults to base64,
so raw httpx is deliberate. A 200 can still carry an `{"error": ...}` body — a
paid-credit wall (fail fast) or a transient hiccup. A hard dimension check turns
a provider that ignores `dimensions` into a clear error, not poisoned vectors.
"""

from __future__ import annotations

import httpx

from backend.utils.config import get_settings

EMBED_DIM = 768
# OpenRouter's OpenAI-compatible base (not a secret; the key comes from config).
_OPENROUTER_BASE = "https://openrouter.ai/api/v1"
# Sits on the ingest path (chunks) and the pre-answer hot path (queries); cap it
# tight so a slow gateway degrades rather than hangs (CLAUDE.md invariant #7).
EMBED_TIMEOUT_S = 10.0


class EmbeddingError(RuntimeError):
    """Embedding could not be produced (gateway error, credit wall, bad dims).

    Callers (retrieval_agent, ingest_service) catch this and degrade — the chat
    path answers without quoted sources rather than hanging.
    """


async def _embed_batch(texts: list[str]) -> list[list[float]]:
    """One OpenAI-compatible `/embeddings` call for a single batch, order-preserving."""
    settings = get_settings()
    model = settings.EMBED_MODEL
    if not model.startswith("openrouter/"):
        # Container is OpenRouter-only; a stray bare id is a config error, not
        # something to silently route around.
        raise EmbeddingError(f"EMBED_MODEL must be an openrouter/* id, got {model!r}")

    try:
        async with httpx.AsyncClient(timeout=EMBED_TIMEOUT_S) as http:
            resp = await http.post(
                f"{_OPENROUTER_BASE}/embeddings",
                headers={"Authorization": f"Bearer {settings.OPENROUTER_API_KEY}"},
                json={
                    "model": model.removeprefix("openrouter/"),
                    "input": texts,
                    "dimensions": EMBED_DIM,
                },
            )
            resp.raise_for_status()
            body = resp.json()
    except (httpx.HTTPError, ValueError) as exc:  # network, timeout, 4xx/5xx, bad JSON
        raise EmbeddingError(f"embedding request failed: {exc}") from exc

    rows = body.get("data")
    if not rows:
        # OpenRouter can return 200 with an {"error": ...} body instead of a status code.
        err = body.get("error") or {}
        msg = err.get("message", body) if isinstance(err, dict) else err
        raise EmbeddingError(f"openrouter returned no embedding data: {msg}")
    rows = sorted(rows, key=lambda row: row.get("index", 0))
    vectors = [row["embedding"] for row in rows]
    for vector in vectors:
        if len(vector) != EMBED_DIM:
            raise EmbeddingError(
                f"{model} returned {len(vector)}-dim vectors; HelpFlow requires "
                f"{EMBED_DIM} — pick an embedding model that supports {EMBED_DIM} dims"
            )
    return vectors


async def embed(texts: list[str]) -> list[list[float]]:
    """Embed `texts` → 768-dim vectors, batching `EMBED_BATCH_SIZE` per request.

    Order-preserving: returns vectors aligned to `texts`. Raises `EmbeddingError`
    on any failure (empty body, credit wall, wrong dims, network) so the caller
    can degrade.
    """
    if not texts:
        return []
    batch_size = get_settings().EMBED_BATCH_SIZE
    vectors: list[list[float]] = []
    for start in range(0, len(texts), batch_size):
        batch = texts[start : start + batch_size]
        vectors.extend(await _embed_batch(batch))
    return vectors
