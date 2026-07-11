"""`GET /widget/config` — public, cosmetic-only tenant config for the embedded
widget (ARCHITECTURE §8.2/§3.2, spec E7 Req 8: "business name, brand color,
greeting from tenant config").

DESIGN CHOICE (flagged, spec E7): no endpoint existed for this before E7 — the
widget key only resolved a `tenant_id` (`resolve_tenant`, E1/E2 stub) for the
chat/subscribe routes. Reusing that same dependency here is the smallest
addition that satisfies Req 8 without touching the frozen `/chat/*` contract:
same auth shape (`X-Widget-Key`), same `conversation_store.get_tenant` read
E3 already has. Only the public-safe subset of `widget_config` is returned —
never `sensitive_intents` or `plan`.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from backend.channels import conversation_store
from backend.middleware.tenant_auth import resolve_tenant

router = APIRouter()


@router.get("/widget/config")
async def widget_config(tenant_id: str = Depends(resolve_tenant)) -> dict:
    tenant = await conversation_store.get_tenant(tenant_id)
    if tenant is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Unknown tenant.")

    config = tenant.get("widget_config") or {}
    if not isinstance(config, dict):
        config = {}

    return {
        "name": tenant.get("name") or "This business",
        "greeting": config.get("greeting"),
        "brand_color": config.get("brand_color"),
        "theme": config.get("theme"),
    }
