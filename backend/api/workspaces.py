"""`POST/GET/DELETE /api/workspaces` (ARCHITECTURE §3.0/§5.3/§7.1, spec E5 Req 3).

JWT-scoped throughout (`get_current_user_id`) — a signed-in account only ever
touches its own workspaces. Creation IS the trial gate: `services/trials.
increment_trial` performs the one atomic guarded UPDATE that decides success
BEFORE any tenant row is written, so a blocked create never leaves a
half-made workspace behind (invariant #4/#11).

DESIGN CHOICE (flagged, ARCHITECTURE §5.2 does not add a `widget_key` column
in this migration): the `widget_key` returned on create is the tenant id
itself — consistent with `middleware/tenant_auth.resolve_tenant`'s E1 stub,
which already treats `X-Widget-Key` as the tenant id directly. A real,
separately-rotatable widget key is deferred to whichever of E6/E7 replaces
that stub, without changing this response shape's meaning.
"""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from backend.middleware.jwt_auth import get_current_user_id
from backend.services import trials
from backend.utils import supabase_client
from backend.utils.config import get_settings
from backend.utils.qdrant_client import get_qdrant

router = APIRouter()
_log = logging.getLogger("helpflow.api.workspaces")


class CreateWorkspaceRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    website_url: str = Field(min_length=1, max_length=2048)


@router.post("/api/workspaces", response_model=None)
async def create_workspace(
    body: CreateWorkspaceRequest, user_id: str = Depends(get_current_user_id)
) -> JSONResponse:
    claimed = await trials.increment_trial(user_id)
    if not claimed:
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN, content=await trials.gate_payload()
        )

    tenant_id = str(uuid.uuid4())
    name = body.name.strip()
    website_url = body.website_url.strip()
    await supabase_client.execute(
        "INSERT INTO tenants (id, name, website_url, owner_user_id, plan) "
        "VALUES ($1, $2, $3, $4, 'trial')",
        tenant_id,
        name,
        website_url,
        user_id,
    )
    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content={
            "tenant": {
                "id": tenant_id,
                "name": name,
                "website_url": website_url,
                "plan": "trial",
            },
            "widget_key": tenant_id,
        },
    )


@router.get("/api/workspaces")
async def list_workspaces(user_id: str = Depends(get_current_user_id)) -> list[dict]:
    rows = await supabase_client.fetch(
        "SELECT t.id, t.name, t.website_url, t.plan, t.created_at, "
        "count(s.id) FILTER (WHERE s.status = 'ready') AS sources_ready, "
        "count(s.id) AS sources_total "
        "FROM tenants t LEFT JOIN sources s ON s.tenant_id = t.id "
        "WHERE t.owner_user_id = $1 GROUP BY t.id ORDER BY t.created_at DESC",
        user_id,
    )
    return [
        {
            "id": str(row["id"]),
            "name": row["name"],
            "website_url": row["website_url"],
            "plan": row["plan"],
            "created_at": row["created_at"].isoformat() if row["created_at"] else None,
            "status": "ready"
            if row["sources_ready"]
            else ("crawling" if row["sources_total"] else "empty"),
            "sources_ready": row["sources_ready"],
            "sources_total": row["sources_total"],
        }
        for row in rows
    ]


@router.delete("/api/workspaces/{tenant_id}")
async def delete_workspace(tenant_id: str, user_id: str = Depends(get_current_user_id)) -> dict:
    if not await trials.is_owner(tenant_id, user_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Workspace not found.")

    from qdrant_client import models

    try:
        await get_qdrant().delete(
            collection_name=get_settings().QDRANT_COLLECTION,
            points_selector=models.Filter(
                must=[
                    models.FieldCondition(
                        key="tenant_id", match=models.MatchValue(value=tenant_id)
                    )
                ]
            ),
        )
    except Exception as exc:  # noqa: BLE001 — best-effort purge; the row delete must still proceed
        _log.warning(
            "qdrant purge failed during workspace delete",
            extra={"tenant_id": tenant_id, "error": str(exc)},
        )

    # 001_schema.sql's ON DELETE CASCADE on tenant_id takes sources/
    # conversations/messages/escalations/events with it — one delete, no
    # manual fan-out. Does NOT touch users.trials_used (spec Req 3: no refund).
    await supabase_client.execute("DELETE FROM tenants WHERE id = $1", tenant_id)
    return {"deleted": True}
