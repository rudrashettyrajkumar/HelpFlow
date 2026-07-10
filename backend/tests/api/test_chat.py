"""`/chat/stream`, `/chat`, `/chat/subscribe` API tests (spec E3 Required tests):
the SSE contract shapes exactly match what E5 binds to. `chat_pipeline`/
`conversation_store`/`rate_limit` are mocked — no real network, Qdrant, Postgres,
or Redis in this test."""

import json
import uuid
from unittest.mock import AsyncMock, patch

from backend.channels.conversation_store import ConversationNotFound
from backend.middleware.rate_limit import RateLimitExceeded

_TENANT_ID = str(uuid.uuid4())
_HEADERS = {"X-Widget-Key": _TENANT_ID}


def _parse_sse(text: str) -> list[dict]:
    events = []
    for block in text.split("\n\n"):
        lines = [line for line in block.splitlines() if line]
        if not lines:
            continue
        event = next((line[len("event: ") :] for line in lines if line.startswith("event: ")), None)
        data = next((line[len("data: ") :] for line in lines if line.startswith("data: ")), None)
        if event and data:
            events.append({"event": event, "data": json.loads(data)})
    return events


def _tenant():
    return {"id": _TENANT_ID, "name": "Acme", "widget_config": {}, "sensitive_intents": []}


def _conversation(**overrides):
    base = {
        "id": str(uuid.uuid4()),
        "tenant_id": _TENANT_ID,
        "status": "ai_handling",
        "low_conf_streak": 0,
    }
    base.update(overrides)
    return base


async def _no_op(*args, **kwargs):
    return None


def test_missing_widget_key_is_401(client):
    resp = client.post("/chat/stream", json={"message": "hi"})
    assert resp.status_code == 401


def test_unknown_tenant_is_404(client):
    with patch("backend.api.chat.conversation_store.get_tenant", AsyncMock(return_value=None)):
        resp = client.post("/chat/stream", json={"message": "hi"}, headers=_HEADERS)
    assert resp.status_code == 404


def test_tenant_rate_limited_is_429(client):
    async def _reject(tenant_id):
        raise RateLimitExceeded("daily limit reached")

    with (
        patch("backend.api.chat.conversation_store.get_tenant", AsyncMock(return_value=_tenant())),
        patch("backend.api.chat.check_tenant_message_limit", _reject),
    ):
        resp = client.post("/chat/stream", json={"message": "hi"}, headers=_HEADERS)
    assert resp.status_code == 429


def test_unknown_conversation_id_is_404(client):
    async def _raise_not_found(*, tenant_id, conversation_id):
        raise ConversationNotFound(conversation_id)

    with (
        patch("backend.api.chat.conversation_store.get_tenant", AsyncMock(return_value=_tenant())),
        patch("backend.api.chat.check_tenant_message_limit", _no_op),
        patch("backend.api.chat.conversation_store.load_or_create", _raise_not_found),
    ):
        resp = client.post(
            "/chat/stream",
            json={"conversation_id": str(uuid.uuid4()), "message": "hi"},
            headers=_HEADERS,
        )
    assert resp.status_code == 404


def test_conversation_rate_limited_is_429(client):
    convo = _conversation()

    async def _reject(conversation_id):
        raise RateLimitExceeded("hourly limit reached")

    with (
        patch("backend.api.chat.conversation_store.get_tenant", AsyncMock(return_value=_tenant())),
        patch("backend.api.chat.check_tenant_message_limit", _no_op),
        patch("backend.api.chat.conversation_store.load_or_create", AsyncMock(return_value=convo)),
        patch("backend.api.chat.check_conversation_message_limit", _reject),
    ):
        resp = client.post("/chat/stream", json={"message": "hi"}, headers=_HEADERS)
    assert resp.status_code == 429


def test_chat_stream_happy_path_matches_frozen_sse_contract(client):
    convo = _conversation()

    async def fake_run_chat_stream(*, tenant, conversation, message, background_tasks):
        yield 'id: 0\nevent: token\ndata: {"seq": 0, "t": "Hi"}\n\n'
        yield 'event: sources\ndata: {"sources": []}\n\n'
        yield "event: done\ndata: {}\n\n"

    with (
        patch("backend.api.chat.conversation_store.get_tenant", AsyncMock(return_value=_tenant())),
        patch("backend.api.chat.check_tenant_message_limit", _no_op),
        patch("backend.api.chat.conversation_store.load_or_create", AsyncMock(return_value=convo)),
        patch("backend.api.chat.check_conversation_message_limit", _no_op),
        patch("backend.api.chat.increment_tenant_message_count", _no_op),
        patch("backend.api.chat.increment_conversation_message_count", _no_op),
        patch("backend.api.chat.run_chat_stream", fake_run_chat_stream),
    ):
        resp = client.post("/chat/stream", json={"message": "hi"}, headers=_HEADERS)

    assert resp.status_code == 200
    events = _parse_sse(resp.text)
    assert events == [
        {"event": "token", "data": {"seq": 0, "t": "Hi"}},
        {"event": "sources", "data": {"sources": []}},
        {"event": "done", "data": {}},
    ]


def test_chat_once_happy_path_returns_json(client):
    convo = _conversation()
    expected = {
        "reply": "We ship to Canada [1].",
        "sources": [{"n": 1, "source_url": "https://acme.example", "cited": True}],
        "escalated": False,
        "reason": None,
        "conversation_id": convo["id"],
        "status": "ai_handling",
    }

    with (
        patch("backend.api.chat.conversation_store.get_tenant", AsyncMock(return_value=_tenant())),
        patch("backend.api.chat.check_tenant_message_limit", _no_op),
        patch("backend.api.chat.conversation_store.load_or_create", AsyncMock(return_value=convo)),
        patch("backend.api.chat.check_conversation_message_limit", _no_op),
        patch("backend.api.chat.increment_tenant_message_count", _no_op),
        patch("backend.api.chat.increment_conversation_message_count", _no_op),
        patch("backend.api.chat.run_chat_once", AsyncMock(return_value=expected)),
    ):
        resp = client.post("/chat", json={"message": "do you ship to Canada?"}, headers=_HEADERS)

    assert resp.status_code == 200
    assert resp.json() == expected


def test_chat_subscribe_unknown_conversation_is_404(client):
    with patch(
        "backend.api.chat.conversation_store.get_conversation", AsyncMock(return_value=None)
    ):
        resp = client.get(f"/chat/subscribe?conversation_id={uuid.uuid4()}")
    assert resp.status_code == 404


def test_chat_subscribe_known_conversation_streams(client):
    convo_id = str(uuid.uuid4())

    async def fake_stream(_conversation_id):
        yield 'event: status\ndata: {"status": "ai_handling"}\n\n'

    with (
        patch(
            "backend.api.chat.conversation_store.get_conversation",
            AsyncMock(return_value=_conversation()),
        ),
        patch("backend.api.chat.stream_conversation_events", fake_stream),
    ):
        resp = client.get(f"/chat/subscribe?conversation_id={convo_id}")

    assert resp.status_code == 200
    events = _parse_sse(resp.text)
    assert events == [{"event": "status", "data": {"status": "ai_handling"}}]
