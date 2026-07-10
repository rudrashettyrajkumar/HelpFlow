"""`llm/gateway.py` — the BYOK-aware chokepoint (spec E4 Req 2/6, ARCHITECTURE
§4.6): BYOK gets exactly one deployment and NO server fallback; demo mode
fails over Groq<->OpenRouter; the demo daily budget is checked BEFORE any
demo-mode provider call and never touched by BYOK requests.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from backend.llm import factory, gateway
from backend.llm.runconfig import RunConfig, Selection
from backend.services import demo_budget
from backend.services.demo_budget import DemoBudgetExceeded


class _FakeChatModel:
    """Stand-in for a LangChain chat model: `.content` on the invoke result,
    an async-iterator of chunks for `.astream`."""

    def __init__(self, *, invoke_result=None, invoke_exc=None, stream_tokens=None, stream_exc=None):
        self._invoke_result = invoke_result
        self._invoke_exc = invoke_exc
        self._stream_tokens = stream_tokens or []
        self._stream_exc = stream_exc

    async def ainvoke(self, messages):
        if self._invoke_exc:
            raise self._invoke_exc
        return SimpleNamespace(content=self._invoke_result)

    async def astream(self, messages):
        for token in self._stream_tokens:
            yield SimpleNamespace(content=token)
        if self._stream_exc:
            raise self._stream_exc


@pytest.fixture(autouse=True)
def _no_demo_budget_limit(monkeypatch):
    """Most tests here aren't about the budget — let demo-mode calls through
    by default; specific tests override this."""
    monkeypatch.setattr(demo_budget, "check_and_increment", AsyncMock(return_value=None))


def _byok_cfg(provider="openrouter", model="nvidia/nemotron-3-nano-30b-a3b:free"):
    return RunConfig(chat=Selection(provider=provider, model=model, api_key="user-key"))


# --------------------------------------------------------------------------- BYOK: no fallback


async def test_byok_chat_failure_raises_after_exactly_one_attempt(monkeypatch):
    calls: list[Selection] = []

    def fake_build(selection, *, timeout, streaming=False):
        calls.append(selection)
        return _FakeChatModel(invoke_exc=RuntimeError("bad key"))

    monkeypatch.setattr(factory, "build_chat_model", fake_build)
    cfg = _byok_cfg()

    with pytest.raises(gateway.LLMUnavailable) as exc_info:
        await gateway.complete("answer", [{"role": "user", "content": "hi"}], cfg)

    assert len(calls) == 1  # BYOK: no server-side fallback
    assert calls[0] == cfg.chat
    assert "nemotron-3-nano" in exc_info.value.user_detail


async def test_byok_never_touches_the_demo_budget(monkeypatch):
    budget_mock = AsyncMock(return_value=None)
    monkeypatch.setattr(demo_budget, "check_and_increment", budget_mock)
    monkeypatch.setattr(
        factory, "build_chat_model", lambda selection, **kw: _FakeChatModel(invoke_result="hi")
    )

    await gateway.complete("answer", [{"role": "user", "content": "hi"}], _byok_cfg())

    budget_mock.assert_not_awaited()


# --------------------------------------------------------------------------- demo: failover chain


async def test_demo_mode_fails_over_to_the_second_deployment(monkeypatch):
    primary = Selection(provider="groq", model="llama-3.3-70b-versatile", api_key="groq-key")
    fallback = Selection(
        provider="openrouter", model="nvidia/nemotron-3-super-120b-a12b:free", api_key="or-key"
    )
    monkeypatch.setattr(factory, "demo_chain", lambda role: [primary, fallback])

    def fake_build(selection, *, timeout, streaming=False):
        if selection == primary:
            return _FakeChatModel(invoke_exc=RuntimeError("groq down"))
        return _FakeChatModel(invoke_result="served by fallback")

    monkeypatch.setattr(factory, "build_chat_model", fake_build)

    result = await gateway.complete("answer", [{"role": "user", "content": "hi"}])
    assert result == "served by fallback"


async def test_demo_mode_all_deployments_failing_raises_unavailable(monkeypatch):
    chain = [
        Selection(provider="groq", model="llama-3.3-70b-versatile", api_key="groq-key"),
        Selection(
            provider="openrouter", model="nvidia/nemotron-3-super-120b-a12b:free", api_key="or-key"
        ),
    ]
    monkeypatch.setattr(factory, "demo_chain", lambda role: chain)
    monkeypatch.setattr(
        factory,
        "build_chat_model",
        lambda selection, **kw: _FakeChatModel(invoke_exc=RuntimeError("down")),
    )

    with pytest.raises(gateway.LLMUnavailable):
        await gateway.complete("answer", [{"role": "user", "content": "hi"}])


# --------------------------------------------------------------------------- demo: budget gate


async def test_demo_budget_checked_before_any_deployment_is_built(monkeypatch):
    build_mock = AsyncMock()
    monkeypatch.setattr(factory, "build_chat_model", build_mock)
    monkeypatch.setattr(
        demo_budget, "check_and_increment", AsyncMock(side_effect=DemoBudgetExceeded("chat"))
    )

    with pytest.raises(DemoBudgetExceeded):
        await gateway.complete("answer", [{"role": "user", "content": "hi"}])

    build_mock.assert_not_called()  # exhausted BEFORE any provider is touched


async def test_stream_holds_semaphore_and_raises_stream_interrupted_mid_stream(monkeypatch):
    monkeypatch.setattr(
        factory,
        "build_chat_model",
        lambda selection, **kw: _FakeChatModel(
            stream_tokens=["hel", "lo"], stream_exc=RuntimeError("dropped")
        ),
    )
    monkeypatch.setattr(factory, "demo_chain", lambda role: [
        Selection(provider="groq", model="llama-3.3-70b-versatile", api_key="k")
    ])

    tokens = []
    with pytest.raises(gateway.StreamInterrupted) as exc_info:
        async for token in gateway.stream("answer", [{"role": "user", "content": "hi"}]):
            tokens.append(token)

    assert tokens == ["hel", "lo"]
    assert exc_info.value.partial_tokens == ["hel", "lo"]
