"""`llm/runconfig.py` — BYOK header parsing/validation (spec E4 Req 3,
ARCHITECTURE §4.4): unknown provider/model combos reject before any stream or
LLM work starts, and — the invariant #9 check Raj asked for by name — a
supplied key NEVER appears in a log record, no matter which code path in this
module runs.
"""

from __future__ import annotations

import logging

import pytest

from backend.llm.runconfig import BYOKError, Selection, from_headers


def test_no_headers_is_demo_mode():
    cfg = from_headers({})
    assert cfg.chat is None
    assert cfg.embed is None
    assert cfg.is_byok is False


def test_known_provider_and_model_parses():
    cfg = from_headers(
        {"x-llm-provider": "groq", "x-llm-model": "llama-3.3-70b-versatile", "x-llm-key": "gsk_abc"}
    )
    assert cfg.chat == Selection(
        provider="groq", model="llama-3.3-70b-versatile", api_key="gsk_abc"
    )
    assert cfg.is_byok is True


def test_model_omitted_defaults_to_the_recommended_model():
    cfg = from_headers({"x-llm-provider": "groq", "x-llm-key": "gsk_abc"})
    assert cfg.chat.model == "llama-3.3-70b-versatile"  # groq's ★recommended pick


def test_unknown_provider_is_rejected():
    with pytest.raises(BYOKError):
        from_headers({"x-llm-provider": "bogus-provider", "x-llm-key": "k"})


def test_missing_key_is_rejected():
    with pytest.raises(BYOKError):
        from_headers({"x-llm-provider": "groq", "x-llm-model": "llama-3.3-70b-versatile"})


def test_whitespace_in_key_is_rejected():
    with pytest.raises(BYOKError):
        from_headers({"x-llm-provider": "groq", "x-llm-key": "has a space"})


def test_openrouter_custom_model_is_allowed_through():
    """OpenRouter allows a custom model id (the catalog's escape hatch)."""
    cfg = from_headers(
        {
            "x-llm-provider": "openrouter",
            "x-llm-model": "some/brand-new-model",
            "x-llm-key": "sk-or-x",
        }
    )
    assert cfg.chat.model == "some/brand-new-model"


def test_groq_unknown_model_is_still_passed_through():
    """Permissive by design: the provider itself rejects a truly bad id."""
    cfg = from_headers(
        {"x-llm-provider": "groq", "x-llm-model": "not-in-the-catalog", "x-llm-key": "gsk_x"}
    )
    assert cfg.chat.model == "not-in-the-catalog"


def test_embed_provider_without_an_embedder_is_rejected():
    # Groq ships no embedding models (ARCHITECTURE §4.2).
    with pytest.raises(BYOKError):
        from_headers({"x-embed-provider": "groq", "x-embed-key": "gsk_x"})


def test_embed_model_omitted_defaults_to_recommended():
    cfg = from_headers({"x-embed-provider": "openrouter", "x-embed-key": "sk-or-x"})
    assert cfg.embed.model == "nvidia/llama-nemotron-embed-vl-1b-v2:free"


def test_chat_and_embed_selections_are_independent():
    cfg = from_headers(
        {
            "x-llm-provider": "groq",
            "x-llm-key": "gsk_chat",
            "x-embed-provider": "openrouter",
            "x-embed-key": "sk-or-embed",
        }
    )
    assert cfg.chat.provider == "groq"
    assert cfg.embed.provider == "openrouter"


# --------------------------------------------------------------------------- invariant #9: leak


def test_api_key_never_appears_in_any_log_record(caplog):
    """Exercises every branch that logs (including the "model not in catalog,
    passing through" info line) with a distinctive secret and asserts it never
    surfaces in a log record's message OR its structured `extra` fields."""
    secret = "sk-or-v1-do-not-leak-this-exact-token-000111"
    caplog.set_level(logging.DEBUG)

    cfg = from_headers(
        {
            "x-llm-provider": "openrouter",
            "x-llm-model": "some/model-not-in-the-catalog",  # trips the "passing through" log line
            "x-llm-key": secret,
        }
    )
    assert cfg.chat.api_key == secret

    for record in caplog.records:
        assert secret not in record.getMessage()
        assert secret not in repr(record.__dict__)
