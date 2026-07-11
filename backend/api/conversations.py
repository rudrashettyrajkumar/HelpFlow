"""`GET /conversations/{id}/messages` · `POST /conversations/{id}/reply|claim|
resolve|handback` (ARCHITECTURE §5.4/§7.1, spec E9 Req 1/2).

DESIGN CHOICE (flagged, spec E9): this module didn't exist before E9 — E5's
`require_admin_tenant` docstring already flagged it as reusable-but-unwired.
No `GET /conversations` (list) here: the inbox LIST reads `v_conversations`
directly via the Supabase anon key + RLS (spec Req 1, ARCHITECTURE §5.5) —
masked, no full transcript. The FULL transcript is exactly the thing that
split exists to keep off the anon path (`v_conversations` only ever exposes a
140-char preview), so it needs a JWT-owner-scoped, service-role read — this
module. Two read paths for two sensitivity levels, not a redundant one.

Every write here is the console's own slice of the frozen stage machine
(helpflow-schema skill): `needs_human -> human_assigned` (claim),
`human_assigned -> resolved` (resolve), `human_assigned -> ai_handling`
(handback) — guarded, one owner per transition, 0-rows-affected is a safe
409, never a 500.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, status
from jose import JWTError
from pydantic import BaseModel, Field

from backend.channels import conversation_store
from backend.middleware.tenant_auth import require_admin_tenant
from backend.services.users import load_user
from backend.utils.security import decode_jwt

router = APIRouter()


async def _optional_user_id(authorization: str | None = Header(default=None)) -> str | None:
    """Best-effort identity for the `assigned_agent` display name (spec E9
    Req 2) — `require_admin_tenant` already authorizes the ADMIN_TOKEN OR a
    JWT; the ADMIN_TOKEN path has no "user", so this is never a 401, same
    permissive pattern as `premium.py`'s `_optional_user_id`."""
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    try:
        return decode_jwt(authorization[7:].strip()).get("sub")
    except JWTError:
        return None


async def _load_owned_conversation(conversation_id: str, tenant_id: str) -> dict:
    """404 for both "never existed" and "belongs to another tenant" — same
    leak-nothing pattern as `admin_sources._load_owned_source`."""
    convo = await conversation_store.get_conversation(conversation_id)
    if convo is None or str(convo["tenant_id"]) != str(tenant_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Conversation not found.")
    return convo


def _conflict(detail: str) -> HTTPException:
    return HTTPException(status.HTTP_409_CONFLICT, detail=detail)


@router.get("/conversations/{conversation_id}/messages")
async def list_messages(
    conversation_id: str, tenant_id: str = Depends(require_admin_tenant)
) -> list[dict]:
    await _load_owned_conversation(conversation_id, tenant_id)
    rows = await conversation_store.list_all_messages(conversation_id)
    for row in rows:
        row["created_at"] = row["created_at"].isoformat()
    return rows


class ReplyRequest(BaseModel):
    body: str = Field(min_length=1, max_length=4000)


@router.post("/conversations/{conversation_id}/reply")
async def reply(
    conversation_id: str,
    request_body: ReplyRequest,
    tenant_id: str = Depends(require_admin_tenant),
) -> dict:
    convo = await _load_owned_conversation(conversation_id, tenant_id)
    if convo["status"] != "human_assigned":
        raise _conflict("Claim this conversation before replying.")

    message_id = await conversation_store.insert_message(
        conversation_id, role="agent", body=request_body.body
    )
    await conversation_store.touch_last_activity(conversation_id)
    await conversation_store.insert_event(conversation_id, "agent_reply")
    return {"id": message_id, "role": "agent", "body": request_body.body}


@router.post("/conversations/{conversation_id}/claim")
async def claim(
    conversation_id: str,
    tenant_id: str = Depends(require_admin_tenant),
    user_id: str | None = Depends(_optional_user_id),
) -> dict:
    await _load_owned_conversation(conversation_id, tenant_id)

    won = await conversation_store.guarded_transition(
        conversation_id, expected_status="needs_human", new_status="human_assigned"
    )
    if not won:
        raise _conflict("Already claimed (or no longer needs a human).")

    user = await load_user(user_id) if user_id else None
    await conversation_store.set_assigned_agent(
        conversation_id, user.email if user else "Agent"
    )
    # Best-effort: the escalation's own status is secondary bookkeeping — the
    # conversation guard above is the authoritative gate for the claim itself.
    await conversation_store.guarded_escalation_transition(
        conversation_id, expected_status="notified", new_status="assigned"
    )
    await conversation_store.insert_event(conversation_id, "agent_joined")
    await conversation_store.touch_last_activity(conversation_id)
    return {"status": "human_assigned"}


@router.post("/conversations/{conversation_id}/resolve")
async def resolve(
    conversation_id: str, tenant_id: str = Depends(require_admin_tenant)
) -> dict:
    await _load_owned_conversation(conversation_id, tenant_id)

    won = await conversation_store.guarded_transition(
        conversation_id, expected_status="human_assigned", new_status="resolved"
    )
    if not won:
        raise _conflict("Not currently assigned to a human (already resolved?).")

    await conversation_store.guarded_escalation_transition(
        conversation_id, expected_status="assigned", new_status="resolved"
    )
    await conversation_store.insert_event(conversation_id, "resolved")
    await conversation_store.touch_last_activity(conversation_id)
    return {"status": "resolved"}


@router.post("/conversations/{conversation_id}/handback")
async def handback(
    conversation_id: str, tenant_id: str = Depends(require_admin_tenant)
) -> dict:
    await _load_owned_conversation(conversation_id, tenant_id)

    won = await conversation_store.guarded_transition(
        conversation_id, expected_status="human_assigned", new_status="ai_handling"
    )
    if not won:
        raise _conflict("Not currently assigned to a human.")

    await conversation_store.set_assigned_agent(conversation_id, None)
    await conversation_store.insert_event(conversation_id, "handed_back")
    await conversation_store.touch_last_activity(conversation_id)
    return {"status": "ai_handling"}
