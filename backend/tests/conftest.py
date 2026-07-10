"""Shared fixtures. External services are mocked here so tests never hit real
APIs (CLAUDE.md code conventions)."""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

# A full set of required env vars so `create_app()` never warns/fails during
# collection, independent of whatever the developer's real .env holds.
_TEST_ENV = {
    "ENV": "dev",
    "OPENROUTER_API_KEY": "test-openrouter-key",
    "GROQ_API_KEY": "test-groq-key",
    "QDRANT_URL": "http://qdrant.test",
    "QDRANT_API_KEY": "test-qdrant-key",
    "SUPABASE_DB_URL": "postgresql://test:test@db.test:5432/postgres",
    "UPSTASH_URL": "http://upstash.test",
    "UPSTASH_TOKEN": "test-upstash-token",
    "ADMIN_TOKEN": "test-admin-token",
    "HANDOFF_TOKEN": "test-handoff-token",
    # Disabled in tests: FlashRank downloads its ONNX model on first use, which
    # would make the suite network-dependent and flaky. `test_reranker.py`
    # flips this on per-test where it specifically exercises the ranker.
    "RERANK_ENABLED": "false",
}


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    """Populate required env vars and clear the settings cache per test.

    Also disables reading the developer's real `.env` so tests are hermetic
    (the "missing key" config test can actually observe a key as missing).
    """
    from backend.utils.config import Settings, get_settings

    # Clear ambient values for fields we don't explicitly pin so defaults are
    # honoured (an eagerly-imported dep can run load_dotenv()).
    for field in Settings.model_fields:
        if field not in _TEST_ENV:
            monkeypatch.delenv(field, raising=False)
    for key, value in _TEST_ENV.items():
        monkeypatch.setenv(key, value)

    monkeypatch.setitem(Settings.model_config, "env_file", None)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def app():
    from backend.main import create_app

    return create_app()


@pytest.fixture
def client(app):
    return TestClient(app)


async def _raise_redis_unavailable(self, *args, **kwargs):
    raise RuntimeError("redis unavailable in tests — no real network calls")


@pytest.fixture(autouse=True)
def _no_real_redis(monkeypatch):
    """No test env has a real Upstash instance; every public `UpstashRedis`
    method funnels through `_command`, so patching it there (once, on the
    class) makes every consumer (`demo_budget`, `embed_signature`, `health`,
    rate limiting, ...) degrade exactly like a Redis outage — deterministic
    and network-free, instead of racing a real DNS failure against
    `http://upstash.test` per test.
    """
    from backend.utils.redis_client import UpstashRedis

    monkeypatch.setattr(UpstashRedis, "_command", _raise_redis_unavailable)


class _LLMCallGuard:
    """Counts how many times the LLM boundary was hit. `call_count` stays 0 on
    any path that must never touch a model (e.g. the guardrail rail)."""

    def __init__(self) -> None:
        self.call_count = 0


@pytest.fixture
def assert_no_llm_calls():
    """Patch every LLM entry point with a counter and yield the guard.

    Exercise the code under test, then `assert guard.call_count == 0`. Patches
    the gateway's public calls (`complete`/`stream`) — what agents use. The
    stubs return inert values instead of raising so a swallowing try/except
    can't hide the call from the count.
    """
    from backend.llm import gateway

    guard = _LLMCallGuard()

    async def _async(*args, **kwargs):
        guard.call_count += 1
        return None

    async def _agen(*args, **kwargs):
        guard.call_count += 1
        if False:  # pragma: no cover — make this an async generator
            yield ""

    with (
        patch.object(gateway, "complete", _async),
        patch.object(gateway, "stream", _agen),
    ):
        yield guard
