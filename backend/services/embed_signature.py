"""BYOK embeddings + per-tenant embedding-space pinning (ARCHITECTURE §4.5,
spec E4 Req 7). Replaces `utils/embeddings.py` (deleted by this epic).

A tenant's whole corpus must live in ONE embedding space: query vectors are
only comparable to chunk vectors from the same model. So the FIRST successful
ingest pins `provider/model` at `hf:embedsig:{tenant}`; later crawls with a
different `X-Embed-*` selection are rejected up front (409, before any
streaming — enforced in `api/admin_sources.py`), and query-time embedding
always follows the PIN, not whatever the browser currently has selected.
Deleting a tenant's last `ready` source releases the pin.

Every embedding provider speaks OpenAI's `/embeddings` wire protocol —
OpenRouter natively, OpenAI natively, Gemini via its OpenAI-compatible
endpoint — so one httpx code path covers all three (ported from DocChat v3's
`utils/embeddings.py`, `dc:` -> `hf:`, `session` -> `tenant`). Every request
pins `dimensions=768` (Matryoshka truncation), which is what lets ONE
`helpflow_chunks` collection serve every provider.

Everything here is best-effort around Redis (errors degrade, never break): a
pin read failure degrades to "no pin", which at worst embeds a query in the
tenant's currently-selected space — the same failure mode the app had before
pinning existed.
"""

from __future__ import annotations

import logging

import httpx

from backend.llm import factory
from backend.llm.runconfig import RunConfig, Selection
from backend.services import demo_budget
from backend.utils import supabase_client
from backend.utils.config import get_settings
from backend.utils.redis_client import get_redis, hf_key

_log = logging.getLogger("helpflow.embed_signature")

EMBED_DIM = 768
# OpenAI-compatible bases per embedding provider (not secrets; keys come from
# the request or config).
_BASES: dict[str, str] = {
    "openrouter": "https://openrouter.ai/api/v1",
    "openai": "https://api.openai.com/v1",
    "gemini": "https://generativelanguage.googleapis.com/v1beta/openai",
}
# Sits on the pre-reply hot path for queries and on the ingest path for
# chunks; cap it tight so a slow gateway degrades rather than hangs.
EMBED_TIMEOUT_S = 10.0


class EmbeddingError(RuntimeError):
    """Embedding could not be produced (gateway error, credit wall, bad dims).

    Callers (retrieval_agent, ingest_service) catch this and degrade — e.g.
    the chat path answers without quoted sources rather than hanging.
    """


def _key(tenant_id: str) -> str:
    return hf_key("embedsig", tenant_id)


def server_default_selection() -> Selection:
    """Demo-mode embedding selection from env (`DEMO_EMBED_MODEL`)."""
    s = get_settings()
    provider, model = factory.parse_env_model(s.DEMO_EMBED_MODEL)
    keys = {"openrouter": s.OPENROUTER_API_KEY, "openai": None, "gemini": s.GEMINI_API_KEY}
    return Selection(provider=provider, model=model, api_key=keys.get(provider) or "")


def signature(selection: Selection) -> str:
    """The pinning identity of an embedding space: `provider/model`."""
    return f"{selection.provider}/{selection.model}"


def request_selection(cfg: RunConfig) -> Selection:
    """The embedding selection this request ASKS for (BYOK header or demo env)."""
    return cfg.embed or server_default_selection()


def is_demo_embed(cfg: RunConfig) -> bool:
    """True when this request brought no `X-Embed-*` header (demo-budget billing)."""
    return cfg.embed is None


async def _embed_batch(texts: list[str], selection: Selection) -> list[list[float]]:
    """One OpenAI-compatible `/embeddings` call for a single batch, order-preserving."""
    base = _BASES.get(selection.provider)
    if base is None:
        raise EmbeddingError(f"provider {selection.provider!r} cannot serve embeddings")
    try:
        async with httpx.AsyncClient(timeout=EMBED_TIMEOUT_S) as http:
            resp = await http.post(
                f"{base}/embeddings",
                headers={"Authorization": f"Bearer {selection.api_key}"},
                json={"model": selection.model, "input": texts, "dimensions": EMBED_DIM},
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
        raise EmbeddingError(f"{selection.provider} returned no embedding data: {msg}")
    rows = sorted(rows, key=lambda row: row.get("index", 0))
    vectors = [row["embedding"] for row in rows]
    for vector in vectors:
        if len(vector) != EMBED_DIM:
            raise EmbeddingError(
                f"{signature(selection)} returned {len(vector)}-dim vectors; HelpFlow "
                f"requires {EMBED_DIM} — pick an embedding model that supports "
                f"{EMBED_DIM} dimensions"
            )
    return vectors


async def embed(
    texts: list[str], selection: Selection | None = None, *, is_demo: bool = True
) -> list[list[float]]:
    """Embed `texts` → 768-dim vectors, batching `EMBED_BATCH_SIZE` per request.

    `is_demo` (the caller's `cfg.embed is None`, NOT inferred from `selection`
    — a BYOK user who happens to pick the same model as the demo default must
    never be charged against the shared budget) gates the shared daily embed
    budget check FIRST (spec Req 6) — over cap raises
    `demo_budget.DemoBudgetExceeded` before any provider is touched.
    Order-preserving: returns vectors aligned to `texts`. Raises
    `EmbeddingError` on any provider failure so the caller can degrade.
    """
    if not texts:
        return []
    sel = selection or server_default_selection()
    if is_demo:
        await demo_budget.check_and_increment("embed")
    batch_size = get_settings().EMBED_BATCH_SIZE
    vectors: list[list[float]] = []
    for start in range(0, len(texts), batch_size):
        batch = texts[start : start + batch_size]
        vectors.extend(await _embed_batch(batch, sel))
    return vectors


# --------------------------------------------------------------------------- pin


async def get_pin(tenant_id: str) -> str | None:
    """The tenant's pinned `provider/model` signature, or None (best-effort)."""
    try:
        return await get_redis().get(_key(tenant_id))
    except Exception as exc:  # noqa: BLE001 — a Redis outage must not block embedding
        _log.warning("embed pin read failed; degrading to none", extra={"error": str(exc)})
        return None


async def pin(tenant_id: str, selection: Selection) -> None:
    """Pin the tenant to `selection`'s embedding space (best-effort, idempotent)."""
    try:
        await get_redis().set(_key(tenant_id), signature(selection))
    except Exception as exc:  # noqa: BLE001 — the vectors are already stored; degrade
        _log.warning("embed pin write failed", extra={"error": str(exc)})


async def release_if_empty(tenant_id: str) -> None:
    """Drop the pin once the tenant has no `ready` sources left (frees them to
    switch embedding models without support intervention)."""
    try:
        row = await supabase_client.fetchrow(
            "SELECT count(*) AS n FROM sources WHERE tenant_id = $1 AND status = 'ready'",
            tenant_id,
        )
        if row is None or int(row["n"]) == 0:
            await get_redis().delete(_key(tenant_id))
    except Exception as exc:  # noqa: BLE001 — pin cleanup is never worth a 500
        _log.warning("embed pin release failed", extra={"error": str(exc)})


async def query_selection(tenant_id: str, cfg: RunConfig) -> Selection:
    """The selection to embed QUERIES with: the pin's model, the request's key.

    If the pinned provider matches the request's embed provider, the user's
    key serves the query. Otherwise fall back to the server default when the
    pin is in the server's space; as a last resort use the request selection
    (wrong space, but retrieval already degrades to low-relevance rather than
    erroring — same contract as every other retrieval failure).
    """
    requested = request_selection(cfg)
    pinned = await get_pin(tenant_id)
    if pinned is None or pinned == signature(requested):
        return requested

    provider, _, model = pinned.partition("/")
    if requested.provider == provider:
        return Selection(provider=provider, model=model, api_key=requested.api_key)

    try:
        server = server_default_selection()
        if signature(server) == pinned:
            return server
    except EmbeddingError:
        pass

    _log.warning(
        "pinned embed space unreachable with this request's keys; using requested space",
        extra={"pinned": pinned, "requested": signature(requested)},
    )
    return requested
