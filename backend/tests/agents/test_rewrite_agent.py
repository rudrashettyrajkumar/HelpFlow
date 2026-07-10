"""Rewrite agent: parse failure -> safe default (never raises), and the
sensitive-intent override that forces `route=handoff` in Python even when the
model's own route disagrees (spec E3 Required tests)."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from backend.agents.rewrite_agent import rewrite


def _fake_response(content: str):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])


async def _patched_rewrite(content=None, side_effect=None, **kwargs):
    mock = (
        AsyncMock(side_effect=side_effect)
        if side_effect
        else AsyncMock(return_value=_fake_response(content))
    )
    with patch("backend.agents.rewrite_agent.llm_router.complete", mock):
        return await rewrite("do you ship to Canada?", **kwargs)


@pytest.mark.asyncio
async def test_llm_call_failure_falls_back_to_default():
    result = await _patched_rewrite(side_effect=TimeoutError("boom"))
    assert result.route == "retrieve"
    assert result.queries == ["do you ship to Canada?"]
    assert result.handoff_reason is None
    assert result.intent == "question"


@pytest.mark.asyncio
async def test_malformed_json_falls_back_to_default():
    result = await _patched_rewrite(content="not json at all")
    assert result.route == "retrieve"
    assert result.queries == ["do you ship to Canada?"]


@pytest.mark.asyncio
async def test_missing_required_field_falls_back_to_default():
    result = await _patched_rewrite(content=json.dumps({"route": "retrieve"}))
    assert result.route == "retrieve"
    assert result.queries == ["do you ship to Canada?"]


@pytest.mark.asyncio
async def test_query_count_out_of_range_for_retrieve_falls_back():
    content = json.dumps(
        {"route": "retrieve", "queries": [], "handoff_reason": None, "intent": "question"}
    )
    result = await _patched_rewrite(content=content)
    # zero queries for route=retrieve is out of the 1-3 range -> safe default.
    assert result.queries == ["do you ship to Canada?"]


@pytest.mark.asyncio
async def test_valid_retrieve_response_parsed_through():
    content = json.dumps(
        {
            "route": "retrieve",
            "queries": ["does the business ship to Canada"],
            "handoff_reason": None,
            "intent": "question",
        }
    )
    result = await _patched_rewrite(content=content)
    assert result.route == "retrieve"
    assert result.queries == ["does the business ship to Canada"]
    assert result.intent == "question"


@pytest.mark.asyncio
async def test_explicit_human_request_sets_handoff_and_user_requested():
    content = json.dumps(
        {"route": "handoff", "queries": [], "handoff_reason": "user_requested", "intent": "human"}
    )
    result = await _patched_rewrite(content=content)
    assert result.route == "handoff"
    assert result.handoff_reason == "user_requested"
    assert result.intent == "human"


@pytest.mark.asyncio
async def test_sensitive_intent_forces_handoff_even_if_model_route_disagrees():
    """Defense in depth: the model said `retrieve` for a refund question, but
    `refund` is in the sensitive set -> Python overrides to `handoff` anyway."""
    content = json.dumps(
        {
            "route": "retrieve",
            "queries": ["refund policy"],
            "handoff_reason": None,
            "intent": "refund",
        }
    )
    result = await _patched_rewrite(
        content=content, sensitive_intents=frozenset({"refund", "complaint", "cancel", "human"})
    )
    assert result.route == "handoff"
    assert result.intent == "refund"


@pytest.mark.asyncio
async def test_non_sensitive_intent_keeps_model_route():
    content = json.dumps(
        {"route": "direct", "queries": [], "handoff_reason": None, "intent": "chitchat"}
    )
    result = await _patched_rewrite(
        content=content, sensitive_intents=frozenset({"refund", "complaint", "cancel", "human"})
    )
    assert result.route == "direct"
