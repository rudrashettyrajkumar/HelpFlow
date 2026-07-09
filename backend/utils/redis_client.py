"""Upstash Redis over its REST API (not redis://).

Ported from DocChat `utils/redis_client.py`, re-prefixed `hf:` (ARCHITECTURE §5:
rate limits + WhatsApp message-id dedup ONLY; no business state in Redis). REST
fits the free tier and a single small container: no connection pool to keep
warm, just HTTPS calls authenticated with a bearer token. Each command is POSTed
as a JSON array (`["INCR", key]`) and the reply is `{"result": ...}`.

Every HelpFlow key is prefixed `hf:` so it shares the Upstash instance with the
other projects (`dc:`, …) without collision — see `hf_key()`.
"""

from collections.abc import Sequence
from typing import Any

import httpx

from backend.utils.config import get_settings

# Upstash REST calls are tiny once warm (~200ms), but the FIRST call pays the
# full TLS handshake — measured >2s cold. 2.5s absorbs the cold start while still
# keeping a wedged cache from stalling the request path (errors degrade, never
# break); `warm_up()` at app startup pays the handshake before user traffic.
REDIS_TIMEOUT_S = 2.5


def hf_key(*parts: str) -> str:
    """Build an `hf:`-prefixed Redis key from parts, e.g. `hf_key("rl", convo)`."""
    return ":".join(("hf", *parts))


class UpstashRedis:
    """Thin async wrapper over the Upstash REST command endpoint."""

    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def _command(self, *args: Any) -> Any:
        """POST one Redis command and return its `result` field."""
        resp = await self._client.post("/", json=[str(a) for a in args])
        resp.raise_for_status()
        return resp.json()["result"]

    async def get(self, key: str) -> str | None:
        return await self._command("GET", key)

    async def set(self, key: str, value: Any) -> str:
        return await self._command("SET", key, value)

    async def setex(self, key: str, seconds: int, value: Any) -> str:
        return await self._command("SETEX", key, seconds, value)

    async def incr(self, key: str) -> int:
        return await self._command("INCR", key)

    async def expire(self, key: str, seconds: int) -> int:
        return await self._command("EXPIRE", key, seconds)

    async def delete(self, key: str) -> int:
        return await self._command("DEL", key)

    async def exists(self, key: str) -> int:
        return await self._command("EXISTS", key)

    async def pipeline(self, *commands: Sequence[Any]) -> list[Any]:
        """Send several commands in ONE HTTP round-trip via Upstash's `/pipeline`
        endpoint. Each command is a sequence like `("INCR", key)`; the body is a
        JSON array of those arrays and Upstash replies with one `{"result": ...}`
        per command, in order. Every arg is stringified, as with `_command`.
        """
        body = [[str(a) for a in cmd] for cmd in commands]
        resp = await self._client.post("/pipeline", json=body)
        resp.raise_for_status()
        return [item["result"] for item in resp.json()]


_redis: UpstashRedis | None = None


def get_redis() -> UpstashRedis:
    """Return the shared Upstash REST client, building it once."""
    global _redis
    if _redis is None:
        settings = get_settings()
        client = httpx.AsyncClient(
            base_url=settings.UPSTASH_URL or "",
            headers={"Authorization": f"Bearer {settings.UPSTASH_TOKEN}"},
            timeout=REDIS_TIMEOUT_S,
        )
        _redis = UpstashRedis(client)
    return _redis


async def warm_up() -> None:
    """Pay the TLS handshake at app startup so the first user request doesn't.

    Best-effort: a failure is logged by the caller's boundary and boot continues
    — the cache warms on first use instead (errors degrade, never break).
    """
    await get_redis().get(hf_key("health", "ping"))
