"""`services/demo_budget.py` — the shared daily demo-mode call budget (spec E4
Req 6, ARCHITECTURE §4.3): checked BEFORE any demo-mode provider call, chat
and embed counters independent, and a Redis outage degrades to "allow the
call" rather than breaking the demo.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend.services import demo_budget
from backend.services.demo_budget import DemoBudgetExceeded


class _FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, int] = {}

    async def incr(self, key: str) -> int:
        self.store[key] = self.store.get(key, 0) + 1
        return self.store[key]

    async def expire(self, key: str, seconds: int) -> int:
        return 1

    async def get(self, key: str) -> str | None:
        value = self.store.get(key)
        return str(value) if value is not None else None


@pytest.fixture
def fake_redis(monkeypatch):
    redis = _FakeRedis()
    monkeypatch.setattr(demo_budget, "get_redis", lambda: redis)
    return redis


def _caps(chat=150, embed=100):
    return lambda: SimpleNamespace(DEMO_CHAT_DAILY=chat, DEMO_EMBED_DAILY=embed)


async def test_calls_under_the_cap_are_allowed(fake_redis, monkeypatch):
    monkeypatch.setattr(demo_budget, "get_settings", _caps(chat=2))
    await demo_budget.check_and_increment("chat")
    await demo_budget.check_and_increment("chat")  # exactly at the cap — still allowed


async def test_the_call_that_crosses_the_cap_raises(fake_redis, monkeypatch):
    monkeypatch.setattr(demo_budget, "get_settings", _caps(chat=2))
    await demo_budget.check_and_increment("chat")
    await demo_budget.check_and_increment("chat")
    with pytest.raises(DemoBudgetExceeded) as exc_info:
        await demo_budget.check_and_increment("chat")
    assert exc_info.value.kind == "chat"


async def test_chat_and_embed_counters_are_independent(fake_redis, monkeypatch):
    monkeypatch.setattr(demo_budget, "get_settings", _caps(chat=1, embed=1))
    await demo_budget.check_and_increment("chat")
    await demo_budget.check_and_increment("embed")  # separate key — must not also be exhausted


async def test_redis_outage_degrades_to_allowing_the_call(monkeypatch):
    async def _raise(*args, **kwargs):
        raise RuntimeError("redis unreachable")

    monkeypatch.setattr(demo_budget, "get_redis", lambda: SimpleNamespace(incr=_raise))
    monkeypatch.setattr(demo_budget, "get_settings", _caps(chat=1))

    await demo_budget.check_and_increment("chat")  # must not raise


async def test_remaining_today_reports_cap_minus_used(fake_redis, monkeypatch):
    monkeypatch.setattr(demo_budget, "get_settings", _caps(chat=150))
    await demo_budget.check_and_increment("chat")
    assert await demo_budget.remaining_today("chat") == 149


async def test_remaining_today_degrades_to_full_cap_on_redis_outage(monkeypatch):
    async def _raise(*args, **kwargs):
        raise RuntimeError("redis unreachable")

    monkeypatch.setattr(demo_budget, "get_redis", lambda: SimpleNamespace(get=_raise))
    monkeypatch.setattr(demo_budget, "get_settings", _caps(chat=150))

    assert await demo_budget.remaining_today("chat") == 150
