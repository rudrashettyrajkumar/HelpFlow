"""Conversation persistence — find-or-create, guarded transitions, message/event
persistence (ARCHITECTURE §5.2, spec E3 Req 2/6/8/9).

Every stage transition is a guarded `UPDATE ... WHERE id=$1 AND status=$2` (LeadFlow's
guarded-transition pattern, ported verbatim per CLAUDE.md invariant #4): affecting 0
rows means someone already moved the conversation — a safe no-op, not an error. This
module is the ONLY place that writes `conversations`/`messages`/`escalations`/`events`.
"""

from __future__ import annotations

import uuid
from typing import Any

from backend.utils import supabase_client


class ConversationNotFound(Exception):
    """`conversation_id` was supplied but doesn't exist, or belongs to another tenant."""


def _row(record: Any) -> dict[str, Any]:
    return dict(record)


async def get_tenant(tenant_id: str) -> dict[str, Any] | None:
    import json

    row = await supabase_client.fetchrow(
        "SELECT id, name, widget_config, sensitive_intents, plan FROM tenants WHERE id = $1",
        tenant_id,
    )
    if row is None:
        return None
    tenant = _row(row)
    widget_config = tenant.get("widget_config")
    if isinstance(widget_config, str):
        tenant["widget_config"] = json.loads(widget_config)
    return tenant


async def count_ready_sources(tenant_id: str) -> int:
    """How many crawled pages this tenant has ready (spec Req 12: 0 -> no_sources)."""
    row = await supabase_client.fetchrow(
        "SELECT count(*) AS n FROM sources WHERE tenant_id = $1 AND status = 'ready'",
        tenant_id,
    )
    return int(row["n"]) if row else 0


async def get_conversation(conversation_id: str) -> dict[str, Any] | None:
    row = await supabase_client.fetchrow(
        "SELECT id, tenant_id, channel, external_ref, status, assigned_agent, "
        "customer_email, low_conf_streak, last_activity_at, created_at, updated_at "
        "FROM conversations WHERE id = $1",
        conversation_id,
    )
    return _row(row) if row else None


async def load_or_create(
    *, tenant_id: str, conversation_id: str | None, channel: str = "web"
) -> dict[str, Any]:
    """Load an existing conversation by id (tenant-scoped) or create a new one.

    Raises `ConversationNotFound` if `conversation_id` is given but doesn't exist or
    belongs to another tenant (404 at the API layer, never leaking cross-tenant data —
    same "404 for both cases" pattern as `admin_sources._load_owned_source`).

    A NEW web conversation self-assigns `external_ref = its own id` (no natural
    dedupe key like a WhatsApp phone number exists for a fresh widget session) so the
    `UNIQUE (tenant_id, channel, external_ref)` constraint is trivially satisfied.
    """
    if conversation_id is not None:
        convo = await get_conversation(conversation_id)
        if convo is None or str(convo["tenant_id"]) != str(tenant_id):
            raise ConversationNotFound(conversation_id)
        return convo

    new_id = str(uuid.uuid4())
    row = await supabase_client.fetchrow(
        "INSERT INTO conversations (id, tenant_id, channel, external_ref) "
        "VALUES ($1, $2, $3, $1) "
        "RETURNING id, tenant_id, channel, external_ref, status, assigned_agent, "
        "customer_email, low_conf_streak, last_activity_at, created_at, updated_at",
        new_id,
        tenant_id,
        channel,
    )
    return _row(row)


async def guarded_transition(
    conversation_id: str, *, expected_status: str, new_status: str
) -> bool:
    """`UPDATE conversations SET status=$2 WHERE id=$1 AND status=$3` — True iff this
    call won the race (1 row affected); False is a safe no-op (§5.2)."""
    tag = await supabase_client.execute(
        "UPDATE conversations SET status = $2 WHERE id = $1 AND status = $3",
        conversation_id,
        new_status,
        expected_status,
    )
    return tag.endswith(" 1")


async def set_assigned_agent(conversation_id: str, agent: str | None) -> None:
    """Not a stage transition (no guard needed) — console's claim/handback
    (spec E9) set/clear the display name shown in the widget's agent
    messages; the CONVERSATION status guard is the authoritative gate for
    those actions, this just tags along."""
    await supabase_client.execute(
        "UPDATE conversations SET assigned_agent = $2 WHERE id = $1",
        conversation_id,
        agent,
    )


async def guarded_escalation_transition(
    conversation_id: str, *, expected_status: str, new_status: str
) -> bool:
    """Same guarded-UPDATE pattern as `guarded_transition`, on the OPEN
    escalation row for this conversation (helpflow-schema: "same rule on
    escalations.status"). Best-effort bookkeeping — callers don't fail the
    conversation-level action if this returns False (e.g. WF-H hasn't
    notified yet, so there's no 'notified' row to claim)."""
    tag = await supabase_client.execute(
        "UPDATE escalations SET status = $3 "
        "WHERE conversation_id = $1 AND status = $2",
        conversation_id,
        expected_status,
        new_status,
    )
    return tag.endswith(" 1")


async def update_low_conf_streak(conversation_id: str, streak: int) -> None:
    """Not a stage transition (no guard needed) — a plain counter on the row the
    caller already loaded this turn; only the answer engine ever writes it."""
    await supabase_client.execute(
        "UPDATE conversations SET low_conf_streak = $2 WHERE id = $1",
        conversation_id,
        streak,
    )


async def touch_last_activity(conversation_id: str) -> None:
    await supabase_client.execute(
        "UPDATE conversations SET last_activity_at = now() WHERE id = $1",
        conversation_id,
    )


async def insert_message(
    conversation_id: str,
    *,
    role: str,
    body: str,
    citations: list[dict[str, Any]] | None = None,
    confidence: str | None = None,
) -> str:
    import json

    row = await supabase_client.fetchrow(
        "INSERT INTO messages (conversation_id, role, body, citations, confidence) "
        "VALUES ($1, $2, $3, $4::jsonb, $5) RETURNING id",
        conversation_id,
        role,
        body,
        json.dumps(citations or []),
        confidence,
    )
    return str(row["id"])


async def insert_event(
    conversation_id: str, event_type: str, detail: dict[str, Any] | None = None
) -> str:
    import json

    row = await supabase_client.fetchrow(
        "INSERT INTO events (conversation_id, type, detail) "
        "VALUES ($1, $2, $3::jsonb) RETURNING id",
        conversation_id,
        event_type,
        json.dumps(detail or {}),
    )
    return str(row["id"])


async def insert_escalation(conversation_id: str, reason: str) -> str:
    row = await supabase_client.fetchrow(
        "INSERT INTO escalations (conversation_id, reason) VALUES ($1, $2) RETURNING id",
        conversation_id,
        reason,
    )
    return str(row["id"])


async def list_all_messages(conversation_id: str) -> list[dict[str, Any]]:
    """The FULL transcript, oldest-first — the console's `GET
    /conversations/{id}/messages` (spec E9 Req 2). Distinct from
    `recent_history` (LLM-context-shaped `{role, content}`, capped) and
    `list_messages_since` (agent-only, for the widget's `/chat/subscribe`)."""
    import json

    rows = await supabase_client.fetch(
        "SELECT id, role, body, citations, confidence, created_at FROM messages "
        "WHERE conversation_id = $1 ORDER BY created_at ASC",
        conversation_id,
    )
    messages = [_row(r) for r in rows]
    for message in messages:
        citations = message.get("citations")
        if isinstance(citations, str):
            message["citations"] = json.loads(citations)
    return messages


async def recent_history(conversation_id: str, *, limit: int = 6) -> list[dict[str, Any]]:
    """The last `limit` user/assistant/agent turns, oldest-first, as `{role, content}`
    dicts — the short-term window `rewrite_agent`/`answer_agent` show a model
    (ARCHITECTURE §3.2). System-role rows (none exist yet) would be excluded too."""
    rows = await supabase_client.fetch(
        "SELECT role, body FROM messages WHERE conversation_id = $1 "
        "AND role IN ('user','assistant','agent') "
        "ORDER BY created_at DESC LIMIT $2",
        conversation_id,
        limit,
    )
    return [{"role": r["role"], "content": r["body"]} for r in reversed(rows)]


async def list_messages_since(
    conversation_id: str, *, after: Any, roles: tuple[str, ...] = ("agent",)
) -> list[dict[str, Any]]:
    """Messages of `roles` newer than `after` (exclusive), oldest first —
    `subscribe.py`'s poll cursor (ARCHITECTURE §3.3)."""
    rows = await supabase_client.fetch(
        "SELECT id, role, body, citations, confidence, created_at FROM messages "
        "WHERE conversation_id = $1 AND role = ANY($2::text[]) "
        "AND ($3::timestamptz IS NULL OR created_at > $3) "
        "ORDER BY created_at ASC",
        conversation_id,
        list(roles),
        after,
    )
    return [_row(r) for r in rows]
