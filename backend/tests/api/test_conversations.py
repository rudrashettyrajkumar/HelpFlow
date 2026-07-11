"""`GET /conversations/{id}/messages` · `POST /conversations/{id}/reply|claim|
resolve|handback` (spec E9 Req 1/2) — the console's slice of the frozen stage
machine (helpflow-schema: needs_human->human_assigned->resolved, or ->
ai_handling on handback). `conversation_store`/`services.users` are mocked —
no real Postgres in this test."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

_TENANT_ID = str(uuid.uuid4())
_CONVO_ID = str(uuid.uuid4())
_HEADERS = {"Authorization": "Bearer test-admin-token", "X-Tenant-Id": _TENANT_ID}


def _conversation(**overrides):
    base = {
        "id": _CONVO_ID,
        "tenant_id": _TENANT_ID,
        "channel": "web",
        "status": "needs_human",
        "assigned_agent": None,
        "customer_email": None,
        "low_conf_streak": 0,
    }
    base.update(overrides)
    return base


def _patched(**overrides):
    defaults = {
        "backend.api.conversations.conversation_store.get_conversation": AsyncMock(
            return_value=_conversation()
        ),
        "backend.api.conversations.conversation_store.guarded_transition": AsyncMock(
            return_value=True
        ),
        "backend.api.conversations.conversation_store.guarded_escalation_transition": AsyncMock(
            return_value=True
        ),
        "backend.api.conversations.conversation_store.set_assigned_agent": AsyncMock(),
        "backend.api.conversations.conversation_store.insert_event": AsyncMock(),
        "backend.api.conversations.conversation_store.touch_last_activity": AsyncMock(),
        "backend.api.conversations.conversation_store.insert_message": AsyncMock(
            return_value=str(uuid.uuid4())
        ),
        "backend.api.conversations.load_user": AsyncMock(return_value=None),
    }
    defaults.update(overrides)
    return [patch(target, mock) for target, mock in defaults.items()]


def test_missing_tenant_header_is_400(client):
    resp = client.get(
        f"/conversations/{_CONVO_ID}/messages",
        headers={"Authorization": "Bearer test-admin-token"},
    )
    assert resp.status_code == 400


def test_unknown_conversation_is_404(client):
    with patch(
        "backend.api.conversations.conversation_store.get_conversation",
        AsyncMock(return_value=None),
    ):
        resp = client.get(f"/conversations/{_CONVO_ID}/messages", headers=_HEADERS)
    assert resp.status_code == 404


def test_conversation_owned_by_another_tenant_is_404(client):
    other_tenant_convo = _conversation(tenant_id=str(uuid.uuid4()))
    with patch(
        "backend.api.conversations.conversation_store.get_conversation",
        AsyncMock(return_value=other_tenant_convo),
    ):
        resp = client.get(f"/conversations/{_CONVO_ID}/messages", headers=_HEADERS)
    assert resp.status_code == 404


def test_list_messages_returns_full_transcript(client):
    import datetime

    rows = [
        {
            "id": str(uuid.uuid4()),
            "role": "user",
            "body": "hi",
            "citations": [],
            "confidence": None,
            "created_at": datetime.datetime.now(datetime.UTC),
        }
    ]
    with (
        patch(
            "backend.api.conversations.conversation_store.get_conversation",
            AsyncMock(return_value=_conversation()),
        ),
        patch(
            "backend.api.conversations.conversation_store.list_all_messages",
            AsyncMock(return_value=rows),
        ),
    ):
        resp = client.get(f"/conversations/{_CONVO_ID}/messages", headers=_HEADERS)
    assert resp.status_code == 200
    assert resp.json()[0]["role"] == "user"


def test_claim_transitions_needs_human_to_human_assigned(client):
    mocks = _patched()
    for m in mocks:
        m.start()
    try:
        resp = client.post(f"/conversations/{_CONVO_ID}/claim", headers=_HEADERS)
    finally:
        for m in mocks:
            m.stop()
    assert resp.status_code == 200
    assert resp.json() == {"status": "human_assigned"}


def test_claim_conflict_is_409(client):
    mocks = _patched(
        **{
            "backend.api.conversations.conversation_store.guarded_transition": AsyncMock(
                return_value=False
            )
        }
    )
    for m in mocks:
        m.start()
    try:
        resp = client.post(f"/conversations/{_CONVO_ID}/claim", headers=_HEADERS)
    finally:
        for m in mocks:
            m.stop()
    assert resp.status_code == 409


def test_reply_requires_human_assigned_status(client):
    with patch(
        "backend.api.conversations.conversation_store.get_conversation",
        AsyncMock(return_value=_conversation(status="needs_human")),
    ):
        resp = client.post(
            f"/conversations/{_CONVO_ID}/reply", json={"body": "hi there"}, headers=_HEADERS
        )
    assert resp.status_code == 409


def test_reply_persists_as_agent_role_message(client):
    mocks = _patched(
        **{
            "backend.api.conversations.conversation_store.get_conversation": AsyncMock(
                return_value=_conversation(status="human_assigned")
            )
        }
    )
    for m in mocks:
        m.start()
    try:
        resp = client.post(
            f"/conversations/{_CONVO_ID}/reply", json={"body": "hi there"}, headers=_HEADERS
        )
    finally:
        for m in mocks:
            m.stop()
    assert resp.status_code == 200
    assert resp.json()["role"] == "agent"
    assert resp.json()["body"] == "hi there"


def test_resolve_transitions_human_assigned_to_resolved(client):
    mocks = _patched(
        **{
            "backend.api.conversations.conversation_store.get_conversation": AsyncMock(
                return_value=_conversation(status="human_assigned")
            )
        }
    )
    for m in mocks:
        m.start()
    try:
        resp = client.post(f"/conversations/{_CONVO_ID}/resolve", headers=_HEADERS)
    finally:
        for m in mocks:
            m.stop()
    assert resp.status_code == 200
    assert resp.json() == {"status": "resolved"}


def test_resolve_conflict_is_409(client):
    mocks = _patched(
        **{
            "backend.api.conversations.conversation_store.guarded_transition": AsyncMock(
                return_value=False
            )
        }
    )
    for m in mocks:
        m.start()
    try:
        resp = client.post(f"/conversations/{_CONVO_ID}/resolve", headers=_HEADERS)
    finally:
        for m in mocks:
            m.stop()
    assert resp.status_code == 409


def test_handback_transitions_human_assigned_to_ai_handling(client):
    mocks = _patched(
        **{
            "backend.api.conversations.conversation_store.get_conversation": AsyncMock(
                return_value=_conversation(status="human_assigned")
            )
        }
    )
    for m in mocks:
        m.start()
    try:
        resp = client.post(f"/conversations/{_CONVO_ID}/handback", headers=_HEADERS)
    finally:
        for m in mocks:
            m.stop()
    assert resp.status_code == 200
    assert resp.json() == {"status": "ai_handling"}
