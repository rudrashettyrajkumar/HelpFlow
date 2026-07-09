"""Health endpoint — per-dependency status (ARCHITECTURE §7/§9; spec E1 Req 6).

UptimeRobot polls `/health` every 5 min, so every check is cheap: Qdrant
`/collections`, a Postgres `SELECT 1`, a Redis GET, and the LLM gateway's
`/models` list — reachability + auth, never a paid completion call.

Aggregation: one or more deps down ⇒ `degraded` (still HTTP 200, the app can
serve whatever still works); every dep down ⇒ 503 (truly dark). Each probe has a
hard timeout and degrades to "down" on any error — a health check never 500s on
a dependency failure (spec E1 Req 6 / acceptance).
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from backend.utils import supabase_client
from backend.utils.llm_router import liveness
from backend.utils.qdrant_client import QDRANT_TIMEOUT_S, get_qdrant
from backend.utils.redis_client import REDIS_TIMEOUT_S, get_redis, hf_key

router = APIRouter()
_log = logging.getLogger("helpflow.health")

_OK = "ok"
_DOWN = "down"


async def _check_qdrant() -> bool:
    await asyncio.wait_for(get_qdrant().get_collections(), timeout=QDRANT_TIMEOUT_S)
    return True


async def _check_supabase() -> bool:
    await asyncio.wait_for(supabase_client.ping(), timeout=supabase_client.DB_ACQUIRE_TIMEOUT_S)
    return True


async def _check_redis() -> bool:
    # A GET of a throwaway key exercises auth + round-trip without writing.
    await asyncio.wait_for(get_redis().get(hf_key("health", "ping")), timeout=REDIS_TIMEOUT_S)
    return True


async def _check_llm() -> bool:
    # OpenRouter's model catalog is a free, no-token GET — reachability + key.
    await asyncio.wait_for(liveness(), timeout=3.0)
    return True


async def _probe(name: str, check: Callable[[], Awaitable[bool]]) -> str:
    """Run one check, degrading any failure to "down" (never raises)."""
    try:
        await check()
        return _OK
    except Exception as exc:  # noqa: BLE001 — a probe must absorb everything
        _log.warning("health check failed", extra={"dep": name, "error": str(exc)})
        return _DOWN


@router.get("/health")
async def health() -> JSONResponse:
    qdrant, supabase, redis, llm = await asyncio.gather(
        _probe("qdrant", _check_qdrant),
        _probe("supabase", _check_supabase),
        _probe("redis", _check_redis),
        _probe("llm", _check_llm),
    )
    deps = {"qdrant": qdrant, "supabase": supabase, "redis": redis, "llm": llm}
    down = [v for v in deps.values() if v == _DOWN]

    if len(down) == len(deps):
        status_str, code = "degraded", 503  # everything dark
    elif down:
        status_str, code = "degraded", 200
    else:
        status_str, code = "ok", 200

    return JSONResponse(status_code=code, content={"status": status_str, **deps})
