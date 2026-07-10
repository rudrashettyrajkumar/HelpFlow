"""Redis-backed request quotas (ARCHITECTURE §7, spec E2 deliverables).

Ported from DocChat `middleware/rate_limit.py`. One real counter for E2:
crawl jobs/tenant/day, guarding `POST /admin/sources` (spec Req 1). The
message-rate helpers below are the "chat limits stub for E3" the spec calls
for — the Redis counter shape ARCHITECTURE §7 already specifies (30
messages/conversation/hour, 200 messages/tenant/day) is implemented here now
so E3 only has to call them from the chat endpoint, not design them.

All checks raise on rejection so callers can turn a rejection into a friendly
4xx in one place. A Redis OUTAGE is not a rejection: per "errors degrade,
never break", a quota check that can't reach Redis logs a warning and lets
the request proceed rather than surfacing a raw 500 — an unenforced quota
beats a broken request path.
"""

from __future__ import annotations

import logging

from backend.ingestion.errors import IngestValidationError
from backend.utils.config import get_settings
from backend.utils.redis_client import get_redis, hf_key

_log = logging.getLogger("helpflow.rate_limit")

_DAY_TTL_S = 24 * 3600
_HOUR_TTL_S = 3600


class RateLimitExceeded(Exception):
    """A chat-path rate limit was exceeded (E3 catches this into a 429)."""


async def check_and_increment_tenant_crawl(tenant_id: str) -> None:
    """Reject once a tenant has started `RATE_CRAWLS_PER_TENANT_DAY` crawl
    jobs today (spec Req 1). The TTL is set only on the first increment of the
    window so it expires ~24h after that first crawl, not after every one."""
    settings = get_settings()
    redis = get_redis()
    key = hf_key("crawls", tenant_id)
    try:
        count = await redis.incr(key)
        if count == 1:
            await redis.expire(key, _DAY_TTL_S)
    except Exception as exc:  # noqa: BLE001 — Redis outage must not break ingestion
        _log.warning("crawl rate check failed; allowing crawl", extra={"error": str(exc)})
        return
    if count > settings.RATE_CRAWLS_PER_TENANT_DAY:
        raise IngestValidationError(
            "crawl_limit_exceeded",
            f"This tenant has reached today's crawl limit "
            f"({settings.RATE_CRAWLS_PER_TENANT_DAY}/day). Try again tomorrow.",
            status_code=429,
        )


async def check_conversation_message_limit(conversation_id: str) -> None:
    """E3 stub: GET-only pre-check, must run before any LLM call — mirrors
    `check_question_limit` from DocChat. Reads without incrementing."""
    settings = get_settings()
    try:
        raw = await get_redis().get(hf_key("msgs", "convo", conversation_id))
    except Exception as exc:  # noqa: BLE001 — a Redis outage must not break chat
        _log.warning("conversation rate check failed; allowing", extra={"error": str(exc)})
        return
    count = int(raw) if raw else 0
    if count >= settings.RATE_MESSAGES_PER_CONVO_HOUR:
        raise RateLimitExceeded(
            f"This conversation has reached its hourly message limit "
            f"({settings.RATE_MESSAGES_PER_CONVO_HOUR}/hour)."
        )


async def increment_conversation_message_count(conversation_id: str) -> None:
    key = hf_key("msgs", "convo", conversation_id)
    try:
        count = await get_redis().incr(key)
        if count == 1:
            await get_redis().expire(key, _HOUR_TTL_S)
    except Exception as exc:  # noqa: BLE001 — a Redis outage must not break chat
        _log.warning("conversation message count increment failed", extra={"error": str(exc)})


async def check_tenant_message_limit(tenant_id: str) -> None:
    """E3 stub: GET-only pre-check for the tenant's daily message cap."""
    settings = get_settings()
    try:
        raw = await get_redis().get(hf_key("msgs", "tenant", tenant_id))
    except Exception as exc:  # noqa: BLE001 — a Redis outage must not break chat
        _log.warning("tenant rate check failed; allowing", extra={"error": str(exc)})
        return
    count = int(raw) if raw else 0
    if count >= settings.RATE_MESSAGES_PER_TENANT_DAY:
        raise RateLimitExceeded(
            f"This tenant has reached today's message limit "
            f"({settings.RATE_MESSAGES_PER_TENANT_DAY}/day)."
        )


async def increment_tenant_message_count(tenant_id: str) -> None:
    key = hf_key("msgs", "tenant", tenant_id)
    try:
        count = await get_redis().incr(key)
        if count == 1:
            await get_redis().expire(key, _DAY_TTL_S)
    except Exception as exc:  # noqa: BLE001 — a Redis outage must not break chat
        _log.warning("tenant message count increment failed", extra={"error": str(exc)})
