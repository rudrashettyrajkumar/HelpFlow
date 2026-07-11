"""Supabase Postgres client — server-side, service-role (RLS-bypassing) only.

DESIGN NOTE (flagged in the E1 session summary): unlike MyShiva/DocChat, which
talk to Supabase over PostgREST (`supabase-py`), the HelpFlow brain uses an
**asyncpg connection pool** against the Supabase SESSION POOLER. Two hard
requirements from ARCHITECTURE force raw Postgres:

  * guarded stage transitions — `UPDATE conversations SET status=$2 WHERE id=$1
    AND status=$3` (§5.2, ported from LeadFlow) are raw parameterised SQL; and
  * live human-reply delivery uses Postgres `LISTEN/NOTIFY` (§3.3),

neither of which PostgREST does well. Connecting via `SUPABASE_DB_URL` uses a
privileged database role that bypasses RLS — which IS the "service-role,
server-only" contract (spec E1 Req 2). The anon key never appears here; the
console reaches the masked views over PostgREST separately.

The pool is a lazy singleton: the `asyncpg` import and the connection handshake
happen on first use, keeping cold-start featherweight and letting unit tests run
without a database (they mock this module).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from backend.utils.config import get_settings

if TYPE_CHECKING:
    import asyncpg

# Small pool — Railway Hobby is a single small container and the Supabase free
# session pooler is itself capacity-limited. The acquire timeout itself is
# `settings.DB_ACQUIRE_TIMEOUT_S` (config.py) — a wedged pool must fail fast so
# the request path degrades rather than hangs (CLAUDE.md invariant #7).
POOL_MIN_SIZE = 1
POOL_MAX_SIZE = 8

_pool: asyncpg.Pool | None = None


async def get_pool() -> asyncpg.Pool:
    """Return the shared asyncpg pool, building it once."""
    global _pool
    if _pool is None:
        import asyncpg

        settings = get_settings()
        _pool = await asyncpg.create_pool(
            dsn=settings.SUPABASE_DB_URL,
            min_size=POOL_MIN_SIZE,
            max_size=POOL_MAX_SIZE,
            timeout=settings.DB_ACQUIRE_TIMEOUT_S,
            # Supabase's transaction/session pooler does not support server-side
            # prepared-statement caching across pooled connections; disabling the
            # cache avoids "prepared statement already exists" under pgbouncer.
            statement_cache_size=0,
        )
    return _pool


async def fetch(query: str, *args: Any) -> list[asyncpg.Record]:
    """Run a read query and return all rows."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetch(query, *args)


async def fetchrow(query: str, *args: Any) -> asyncpg.Record | None:
    """Run a read query and return the first row (or None)."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchrow(query, *args)


async def execute(query: str, *args: Any) -> str:
    """Run a write and return asyncpg's status tag (e.g. 'UPDATE 1').

    Callers of guarded transitions read the row count out of the tag: a
    trailing '0' means the guard did not match (someone already moved the row)
    — a safe no-op, not an error (ARCHITECTURE §5.2).
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.execute(query, *args)


async def ping() -> bool:
    """Cheap liveness check for /health — `SELECT 1` through the pool."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.fetchval("SELECT 1")
    return True


async def close_pool() -> None:
    """Close the pool on app shutdown (best-effort)."""
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None
