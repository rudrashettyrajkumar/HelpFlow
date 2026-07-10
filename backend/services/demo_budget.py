"""Demo-mode shared daily call budget (ARCHITECTURE §4.3, spec E4 Req 6).

Shared Groq/OpenRouter free-tier keys serve every demo-mode visitor, so a
global daily cap protects Raj's quota from being drained by any one
workspace. `hf:demo:{yyyymmdd}:{chat|embed}` is an atomic Upstash `INCR`,
expiring at midnight UTC, checked BEFORE the provider is ever called — an
exhausted budget must never let the request through to burn what's left of a
rate-limited free tier. A provider-side quota error that slips past the
check (someone else drained the provider itself) maps to the exact same
`demo_exhausted` notice one layer up (chat_pipeline/graph) — the user never
sees a raw provider error.

BYOK requests never touch these counters (gateway/embed_signature only call
this module on the demo-mode path).
"""

from __future__ import annotations

import datetime
import logging
from typing import Literal

from backend.utils.config import get_settings
from backend.utils.redis_client import get_redis, hf_key

_log = logging.getLogger("helpflow.demo_budget")

Kind = Literal["chat", "embed"]

# A little slack past exact midnight so a request racing the rollover isn't
# left with a key that expires a few seconds early.
_EXPIRY_BUFFER_S = 120


class DemoBudgetExceeded(RuntimeError):
    """Today's shared demo-mode budget for `kind` is used up."""

    def __init__(self, kind: Kind) -> None:
        self.kind: Kind = kind
        super().__init__(f"demo {kind} budget exhausted for today")


def _today_key(kind: Kind) -> str:
    day = datetime.datetime.now(datetime.UTC).strftime("%Y%m%d")
    return hf_key("demo", day, kind)


def _seconds_until_midnight_utc() -> int:
    now = datetime.datetime.now(datetime.UTC)
    tomorrow = (now + datetime.timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    return int((tomorrow - now).total_seconds()) + _EXPIRY_BUFFER_S


def _cap_for(kind: Kind) -> int:
    settings = get_settings()
    return settings.DEMO_CHAT_DAILY if kind == "chat" else settings.DEMO_EMBED_DAILY


async def check_and_increment(kind: Kind) -> None:
    """Raise `DemoBudgetExceeded` if today's `kind` cap is already reached;
    otherwise atomically count this call against it.

    Best-effort around Redis: a read/write failure degrades to "allow the
    call" (errors degrade, never break) — the worst case is a slightly
    over-budget day, not a broken demo.
    """
    redis = get_redis()
    key = _today_key(kind)
    cap = _cap_for(kind)
    try:
        current = await redis.incr(key)
        if current == 1:
            await redis.expire(key, _seconds_until_midnight_utc())
    except Exception as exc:  # noqa: BLE001 — a Redis outage must not block the demo
        _log.warning("demo budget check failed; allowing the call", extra={"error": str(exc)})
        return
    if current > cap:
        raise DemoBudgetExceeded(kind)


async def remaining_today(kind: Kind) -> int:
    """Best-effort UI helper: how many `kind` calls are left today (never raises)."""
    cap = _cap_for(kind)
    try:
        raw = await get_redis().get(_today_key(kind))
        used = int(raw) if raw else 0
    except Exception as exc:  # noqa: BLE001 — a display helper must never break a page
        _log.warning("demo budget read failed; reporting full cap", extra={"error": str(exc)})
        return cap
    return max(0, cap - used)
