"""`build_chat_model`/`demo_chain` provider wiring — real LangChain construction
(no network). Regression coverage for DocChat's highest-impact live finding
(ARCHITECTURE §4.6, spec E4 Req 1): OpenRouter's free "reasoning" models
(Nemotron, gpt-oss, Qwen3) burn an unbounded hidden thinking budget before the
first visible token — measured 70+s of silence — so every OpenRouter call
binds `reasoning.enabled=false`. That field is OpenRouter-only: Groq 400s on
it (confirmed live), so it must never leak to Groq/OpenAI/Anthropic/Gemini
calls.
"""

from __future__ import annotations

from types import SimpleNamespace

from backend.llm import factory
from backend.llm.factory import build_chat_model, demo_chain
from backend.llm.runconfig import Selection


def _settings(**over):
    base = {
        "DEMO_REWRITER_MODEL": "groq/llama-3.3-70b-versatile",
        "DEMO_ANSWERER_MODEL": "groq/llama-3.3-70b-versatile",
        "OPENROUTER_API_KEY": "or-key",
        "GROQ_API_KEY": "groq-key",
    }
    base.update(over)
    return SimpleNamespace(**base)


def test_demo_chain_groq_primary_openrouter_fallback(monkeypatch):
    """Default demo config: chat on Groq, diverse fallback to OpenRouter."""
    monkeypatch.setattr(factory, "get_settings", lambda: _settings())
    chain = demo_chain("answer")
    assert [(s.provider, s.model) for s in chain] == [
        ("groq", "llama-3.3-70b-versatile"),
        ("openrouter", "nvidia/nemotron-3-super-120b-a12b:free"),
    ]


def test_demo_chain_openrouter_primary_falls_back_to_groq(monkeypatch):
    """If a deploy pins an OpenRouter chat model, the fallback flips to Groq."""
    monkeypatch.setattr(
        factory,
        "get_settings",
        lambda: _settings(DEMO_ANSWERER_MODEL="openrouter/nvidia/nemotron-3-super-120b-a12b:free"),
    )
    chain = demo_chain("answer")
    assert [s.provider for s in chain] == ["openrouter", "groq"]


def test_demo_chain_drops_provider_with_no_key(monkeypatch):
    """A missing fallback key drops that deployment rather than crashing."""
    monkeypatch.setattr(factory, "get_settings", lambda: _settings(OPENROUTER_API_KEY=None))
    chain = demo_chain("answer")
    assert [s.provider for s in chain] == ["groq"]


def test_rewrite_role_uses_its_own_env_field(monkeypatch):
    monkeypatch.setattr(
        factory,
        "get_settings",
        lambda: _settings(DEMO_REWRITER_MODEL="openrouter/nvidia/nemotron-3-nano-30b-a3b:free"),
    )
    chain = demo_chain("rewrite")
    assert chain[0].provider == "openrouter"
    assert chain[0].model == "nvidia/nemotron-3-nano-30b-a3b:free"


# --------------------------------------------------------------------------- reasoning-off


def test_openrouter_binds_reasoning_disabled():
    sel = Selection(provider="openrouter", model="nvidia/nemotron-3-nano-30b-a3b:free", api_key="k")
    model = build_chat_model(sel, timeout=5.0)
    assert getattr(model, "kwargs", None) == {"reasoning": {"enabled": False}}


def test_groq_does_not_bind_reasoning():
    sel = Selection(provider="groq", model="llama-3.3-70b-versatile", api_key="k")
    model = build_chat_model(sel, timeout=5.0)
    assert not hasattr(model, "kwargs")


def test_openai_does_not_bind_reasoning():
    sel = Selection(provider="openai", model="gpt-4o-mini", api_key="k")
    model = build_chat_model(sel, timeout=5.0)
    assert not hasattr(model, "kwargs")


def test_anthropic_does_not_bind_reasoning():
    sel = Selection(provider="anthropic", model="claude-haiku-4-5-20251001", api_key="k")
    model = build_chat_model(sel, timeout=5.0)
    assert not hasattr(model, "kwargs")


def test_gemini_does_not_bind_reasoning():
    sel = Selection(provider="gemini", model="gemini-3.1-flash-lite", api_key="k")
    model = build_chat_model(sel, timeout=5.0)
    assert not hasattr(model, "kwargs")
