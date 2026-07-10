"""`services/embed_signature.py` — per-tenant embedding-space pin (spec E4 Req
7, ARCHITECTURE §4.5): first-pin-wins, `query_selection` follows the PIN not
the request, and the pin releases once a tenant has no `ready` sources left.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from backend.llm.runconfig import RunConfig, Selection
from backend.services import embed_signature


@pytest.fixture
def fake_redis(monkeypatch):
    store: dict[str, str] = {}

    class _Redis:
        async def get(self, key):
            return store.get(key)

        async def set(self, key, value):
            store[key] = value

        async def delete(self, key):
            store.pop(key, None)

    monkeypatch.setattr(embed_signature, "get_redis", lambda: _Redis())
    return store


async def test_pin_then_get_pin_round_trips(fake_redis):
    sel = Selection(provider="openrouter", model="nvidia/nemotron-embed-vl-1b:free", api_key="k")
    await embed_signature.pin("tenant-a", sel)
    got = await embed_signature.get_pin("tenant-a")
    assert got == "openrouter/nvidia/nemotron-embed-vl-1b:free"


async def test_no_pin_yet_query_selection_uses_the_request_selection(fake_redis):
    cfg = RunConfig(embed=Selection(provider="openai", model="text-embedding-3-small", api_key="k"))
    selection = await embed_signature.query_selection("tenant-a", cfg)
    assert selection.provider == "openai"


async def test_pin_matches_request_uses_the_requests_own_key(fake_redis):
    sel = Selection(provider="openai", model="text-embedding-3-small", api_key="user-key")
    await embed_signature.pin("tenant-a", sel)
    cfg = RunConfig(embed=sel)
    selection = await embed_signature.query_selection("tenant-a", cfg)
    assert selection.api_key == "user-key"


async def test_pin_mismatch_falls_back_to_pins_provider_with_requests_key(fake_redis):
    """Pinned to openai, but this request only brought an openrouter key — the
    pinned PROVIDER wins (same-provider key reuse), never a wrong-space embed."""
    pinned = Selection(provider="openai", model="text-embedding-3-large", api_key="orig-key")
    await embed_signature.pin("tenant-a", pinned)
    requested = Selection(provider="openai", model="text-embedding-3-small", api_key="new-key")
    cfg = RunConfig(embed=requested)
    selection = await embed_signature.query_selection("tenant-a", cfg)
    assert selection.provider == "openai"
    assert selection.model == "text-embedding-3-large"  # the PIN's model, not the request's
    assert selection.api_key == "new-key"  # the request's own key


async def test_redis_outage_degrades_to_no_pin(monkeypatch):
    async def _raise(*args, **kwargs):
        raise RuntimeError("redis unreachable")

    class _Redis:
        get = staticmethod(_raise)

    monkeypatch.setattr(embed_signature, "get_redis", lambda: _Redis())
    assert await embed_signature.get_pin("tenant-a") is None


async def test_release_if_empty_drops_the_pin_when_no_ready_sources_remain(fake_redis, monkeypatch):
    await embed_signature.pin(
        "tenant-a", Selection(provider="openai", model="text-embedding-3-small", api_key="k")
    )
    monkeypatch.setattr(
        embed_signature.supabase_client, "fetchrow", AsyncMock(return_value={"n": 0})
    )
    await embed_signature.release_if_empty("tenant-a")
    assert await embed_signature.get_pin("tenant-a") is None


async def test_release_if_empty_keeps_the_pin_when_ready_sources_remain(fake_redis, monkeypatch):
    await embed_signature.pin(
        "tenant-a", Selection(provider="openai", model="text-embedding-3-small", api_key="k")
    )
    monkeypatch.setattr(
        embed_signature.supabase_client, "fetchrow", AsyncMock(return_value={"n": 3})
    )
    await embed_signature.release_if_empty("tenant-a")
    assert await embed_signature.get_pin("tenant-a") is not None


async def test_embed_demo_mode_checks_the_budget_first(monkeypatch):
    budget_mock = AsyncMock(side_effect=embed_signature.demo_budget.DemoBudgetExceeded("embed"))
    monkeypatch.setattr(embed_signature.demo_budget, "check_and_increment", budget_mock)

    sel = Selection(provider="openrouter", model="m", api_key="k")
    with pytest.raises(embed_signature.demo_budget.DemoBudgetExceeded):
        await embed_signature.embed(["hello"], sel, is_demo=True)


async def test_embed_byok_never_touches_the_demo_budget(monkeypatch):
    budget_mock = AsyncMock()
    monkeypatch.setattr(embed_signature.demo_budget, "check_and_increment", budget_mock)

    async def fake_batch(texts, selection):
        return [[0.1] * 768 for _ in texts]

    monkeypatch.setattr(embed_signature, "_embed_batch", fake_batch)

    sel = Selection(provider="openai", model="text-embedding-3-small", api_key="k")
    await embed_signature.embed(["hello"], sel, is_demo=False)
    budget_mock.assert_not_awaited()
