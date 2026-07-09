"""Config: fail-fast in prod on a missing required key; defaults populate;
env-driven overrides; the sensitive-intent set parses (spec E1 Required tests)."""

import pytest

from backend.utils.config import REQUIRED_IN_PROD, Settings, get_settings


def test_defaults_populate():
    s = get_settings()
    assert s.QDRANT_COLLECTION == "helpflow_chunks"
    assert s.RELEVANCE_THRESHOLD == 0.30
    assert s.MAX_PAGES == 50
    assert s.MAX_CONCURRENT_LLM_CALLS == 8
    assert s.ROUTER_MODEL.startswith("openrouter/")
    assert s.ANSWER_MODEL.startswith("openrouter/")
    assert s.EMBED_MODEL.startswith("openrouter/")


def test_sensitive_intents_parses():
    s = get_settings()
    assert s.sensitive_intents == frozenset({"refund", "complaint", "cancel", "human"})


def test_sensitive_intents_override(monkeypatch):
    monkeypatch.setenv("SENSITIVE_INTENTS", "refund, Legal ,human")
    get_settings.cache_clear()
    assert get_settings().sensitive_intents == frozenset({"refund", "legal", "human"})


def test_missing_required_key_fails_fast_in_prod(monkeypatch):
    # A prod box missing a load-bearing key must refuse to boot with a clear message.
    monkeypatch.setenv("ENV", "prod")
    monkeypatch.delenv("QDRANT_URL", raising=False)
    with pytest.raises(ValueError, match="QDRANT_URL"):
        Settings()


def test_missing_key_only_warns_in_dev(monkeypatch):
    # A half-configured dev box still boots so the developer can work.
    monkeypatch.setenv("ENV", "dev")
    monkeypatch.delenv("QDRANT_URL", raising=False)
    s = Settings()  # no raise
    assert s.QDRANT_URL is None


def test_all_required_keys_are_real_fields():
    # Guard against a typo in REQUIRED_IN_PROD silently never being enforced.
    for key in REQUIRED_IN_PROD:
        assert key in Settings.model_fields, f"{key} is not a Settings field"
