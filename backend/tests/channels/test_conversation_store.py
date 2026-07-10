"""Conversation store: find-or-create, guarded transitions are a no-op on an
unexpected current status (concurrent double-escalate affects one row), and
tenant-scoped load (spec E3 Required tests)."""

import uuid
from unittest.mock import AsyncMock, patch

import pytest

from backend.channels import conversation_store
from backend.channels.conversation_store import ConversationNotFound


async def test_load_or_create_creates_new_conversation_when_no_id_given():
    tenant_id = str(uuid.uuid4())
    new_id = str(uuid.uuid4())

    async def fake_fetchrow(query, *args):
        assert "INSERT INTO conversations" in query
        return {
            "id": new_id,
            "tenant_id": tenant_id,
            "channel": "web",
            "external_ref": new_id,
            "status": "ai_handling",
            "assigned_agent": None,
            "customer_email": None,
            "low_conf_streak": 0,
            "last_activity_at": None,
            "created_at": None,
            "updated_at": None,
        }

    with patch("backend.utils.supabase_client.fetchrow", fake_fetchrow):
        convo = await conversation_store.load_or_create(tenant_id=tenant_id, conversation_id=None)

    assert convo["id"] == new_id
    assert convo["status"] == "ai_handling"


async def test_load_or_create_loads_existing_conversation_for_owning_tenant():
    tenant_id = str(uuid.uuid4())
    convo_id = str(uuid.uuid4())

    async def fake_fetchrow(query, *args):
        return {
            "id": convo_id,
            "tenant_id": tenant_id,
            "channel": "web",
            "external_ref": convo_id,
            "status": "needs_human",
            "assigned_agent": None,
            "customer_email": None,
            "low_conf_streak": 1,
            "last_activity_at": None,
            "created_at": None,
            "updated_at": None,
        }

    with patch("backend.utils.supabase_client.fetchrow", fake_fetchrow):
        convo = await conversation_store.load_or_create(
            tenant_id=tenant_id, conversation_id=convo_id
        )

    assert convo["status"] == "needs_human"


async def test_load_or_create_rejects_conversation_owned_by_another_tenant():
    tenant_id = str(uuid.uuid4())
    other_tenant_id = str(uuid.uuid4())
    convo_id = str(uuid.uuid4())

    async def fake_fetchrow(query, *args):
        return {
            "id": convo_id,
            "tenant_id": other_tenant_id,
            "channel": "web",
            "external_ref": convo_id,
            "status": "ai_handling",
            "assigned_agent": None,
            "customer_email": None,
            "low_conf_streak": 0,
            "last_activity_at": None,
            "created_at": None,
            "updated_at": None,
        }

    with (
        patch("backend.utils.supabase_client.fetchrow", fake_fetchrow),
        pytest.raises(ConversationNotFound),
    ):
        await conversation_store.load_or_create(tenant_id=tenant_id, conversation_id=convo_id)


async def test_load_or_create_rejects_unknown_conversation_id():
    async def fake_fetchrow(query, *args):
        return None

    with (
        patch("backend.utils.supabase_client.fetchrow", fake_fetchrow),
        pytest.raises(ConversationNotFound),
    ):
        await conversation_store.load_or_create(
            tenant_id=str(uuid.uuid4()), conversation_id=str(uuid.uuid4())
        )


async def test_guarded_transition_true_when_it_wins_the_race():
    fake_execute = AsyncMock(return_value="UPDATE 1")
    with patch("backend.utils.supabase_client.execute", fake_execute):
        moved = await conversation_store.guarded_transition(
            "convo-1", expected_status="ai_handling", new_status="needs_human"
        )
    assert moved is True
    fake_execute.assert_awaited_once_with(
        "UPDATE conversations SET status = $2 WHERE id = $1 AND status = $3",
        "convo-1",
        "needs_human",
        "ai_handling",
    )


async def test_guarded_transition_is_a_safe_no_op_when_status_already_moved():
    """Simulates a concurrent double-escalate: the row was already moved by
    another request, so this guarded UPDATE affects 0 rows — a safe no-op, not
    an error (invariant #4)."""
    fake_execute = AsyncMock(return_value="UPDATE 0")
    with patch("backend.utils.supabase_client.execute", fake_execute):
        moved = await conversation_store.guarded_transition(
            "convo-1", expected_status="ai_handling", new_status="needs_human"
        )
    assert moved is False


async def test_get_tenant_parses_widget_config_json_string():
    async def fake_fetchrow(query, *args):
        return {
            "id": "tenant-1",
            "name": "Acme",
            "widget_config": '{"tone": "playful"}',
            "sensitive_intents": [],
        }

    with patch("backend.utils.supabase_client.fetchrow", fake_fetchrow):
        tenant = await conversation_store.get_tenant("tenant-1")

    assert tenant["widget_config"] == {"tone": "playful"}


async def test_get_tenant_returns_none_when_missing():
    async def fake_fetchrow(query, *args):
        return None

    with patch("backend.utils.supabase_client.fetchrow", fake_fetchrow):
        tenant = await conversation_store.get_tenant("missing-tenant")

    assert tenant is None
