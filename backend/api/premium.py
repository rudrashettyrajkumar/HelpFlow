"""`POST /api/premium-contact` (ARCHITECTURE §3.0/§7.1/§7.2, spec E5 Req 6).

The `premium_leads` row is the source of truth — inserted FIRST, then a
best-effort notify to n8n WF-P (E6, `POST /webhook/premium-lead`). A webhook
failure, timeout, or missing `N8N_PREMIUM_LEAD_URL` never fails the request:
the row already exists, so a lead is never lost even if n8n is down — only a
`workflow_error` event records the miss (same "row is truth, webhook is
notify" split as the handoff path, ARCHITECTURE §7.2).

Reachable both logged-out (the marketing landing page) and logged-in (the
trial-gate form, `source='gate'`) — `Authorization` is OPTIONAL here, unlike
every JWT-scoped route in `workspaces.py`/`auth.py`.
"""

from __future__ import annotations

import logging
from typing import Literal

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, Header, Request
from fastapi.responses import JSONResponse
from jose import JWTError
from pydantic import BaseModel, Field

from backend.channels.conversation_store import insert_event
from backend.utils import supabase_client
from backend.utils.config import get_settings
from backend.utils.redis_client import get_redis, hf_key
from backend.utils.security import decode_jwt

router = APIRouter()
_log = logging.getLogger("helpflow.api.premium")

_DAY_TTL_S = 24 * 3600


class PremiumContactRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: str = Field(min_length=3, max_length=254)
    company: str | None = Field(default=None, max_length=160)
    message: str = Field(min_length=1, max_length=4000)
    source: Literal["gate", "landing"] = "landing"


async def _optional_user_id(authorization: str | None = Header(default=None)) -> str | None:
    """Best-effort identity: a bad/missing/expired token is just "anonymous"
    here, never a 401 — the form itself has no login requirement."""
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    try:
        return decode_jwt(authorization[7:].strip()).get("sub")
    except JWTError:
        return None


async def _under_ip_rate_limit(ip: str) -> bool:
    """3/day/IP (spec Req 6, `PREMIUM_CONTACT_DAILY_PER_IP`). A Redis outage
    lets the request through — errors degrade, never break (invariant #7)."""
    key = hf_key("premium", "ip", ip)
    try:
        count = await get_redis().incr(key)
        if count == 1:
            await get_redis().expire(key, _DAY_TTL_S)
    except Exception as exc:  # noqa: BLE001
        _log.warning("premium-contact rate check failed; allowing", extra={"error": str(exc)})
        return True
    return count <= get_settings().PREMIUM_CONTACT_DAILY_PER_IP


async def _notify_wf_p(lead_id: str, body: PremiumContactRequest) -> None:
    settings = get_settings()
    if not settings.N8N_PREMIUM_LEAD_URL:
        return
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.post(
                settings.N8N_PREMIUM_LEAD_URL,
                headers={"X-Lead-Token": settings.LEAD_TOKEN or ""},
                json={
                    "lead_id": lead_id,
                    "name": body.name,
                    "email": body.email,
                    "company": body.company,
                    "message": body.message,
                    "source": body.source,
                },
            )
            resp.raise_for_status()
    except Exception as exc:  # noqa: BLE001 — best-effort notify; the row is the source of truth
        _log.warning("WF-P notify failed", extra={"lead_id": lead_id, "error": str(exc)})
        try:
            await insert_event(
                None,  # not tied to a conversation — a lead, not a chat
                "workflow_error",
                {"webhook": "premium-lead", "lead_id": lead_id, "error": str(exc)},
            )
        except Exception as inner_exc:  # noqa: BLE001 — already on a failure path
            _log.warning(
                "workflow_error event write also failed",
                extra={"lead_id": lead_id, "error": str(inner_exc)},
            )


@router.post("/api/premium-contact")
async def premium_contact(
    body: PremiumContactRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    user_id: str | None = Depends(_optional_user_id),
) -> JSONResponse:
    ip = request.client.host if request.client else "unknown"
    if not await _under_ip_rate_limit(ip):
        return JSONResponse(
            status_code=429,
            content={
                "error": "rate_limited",
                "detail": "Too many contact requests from this address today.",
            },
        )

    row = await supabase_client.fetchrow(
        "INSERT INTO premium_leads (user_id, name, email, company, message, source) "
        "VALUES ($1, $2, $3, $4, $5, $6) RETURNING id",
        user_id,
        body.name.strip(),
        body.email.strip().lower(),
        (body.company or "").strip() or None,
        body.message.strip(),
        body.source,
    )
    lead_id = str(row["id"])

    # respond-early (spec Req 6): the row already exists, so the WF-P notify
    # runs AFTER the response is sent — never adds webhook/n8n latency to the
    # visitor's request, same pattern as the handoff notify (chat_pipeline.py).
    background_tasks.add_task(_notify_wf_p, lead_id, body)

    return JSONResponse(status_code=202, content={"id": lead_id, "status": "received"})
