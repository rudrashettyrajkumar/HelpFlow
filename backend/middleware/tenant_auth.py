"""Auth dependencies — public widget key → tenant, and the admin bearer.

ARCHITECTURE §7.1: `tenant_id` is resolved from a public **widget key** sent by
the embed (`X-Widget-Key`), NOT trusted as a raw id from the client; the owner
`/admin/*` routes sit behind a simple per-deploy bearer (`ADMIN_TOKEN`).

E1 SCOPE (flagged): the widget-key → tenant lookup is stubbed. The demo treats
the `X-Widget-Key` value as the tenant id directly so downstream epics can wire
routes now; E2/E6 replace `resolve_tenant` with a real lookup (a `widget_key`
column / mapping on `tenants`) without changing this dependency's signature. The
admin bearer check is real from E1.
"""

from __future__ import annotations

from fastapi import Header, HTTPException, status

from backend.utils.config import get_settings


async def resolve_tenant(x_widget_key: str | None = Header(default=None)) -> str:
    """Resolve the public widget key to a tenant id (E1 stub: identity mapping).

    Raises 401 when the header is absent. The returned value is what every
    Qdrant search and Supabase read scopes on (tenant isolation, invariant #2).
    """
    if not x_widget_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="missing X-Widget-Key"
        )
    # TODO(E2/E6): look up tenants by widget key instead of trusting it as the id.
    return x_widget_key


async def require_admin(authorization: str | None = Header(default=None)) -> None:
    """Gate the owner `/admin/*` routes behind the `ADMIN_TOKEN` bearer.

    Constant-time-ish compare via `secrets.compare_digest`; a missing/blank
    configured token means admin routes are locked (never open by default).
    """
    import secrets

    token = get_settings().ADMIN_TOKEN
    supplied = ""
    if authorization and authorization.lower().startswith("bearer "):
        supplied = authorization[7:].strip()
    if not token or not supplied or not secrets.compare_digest(supplied, token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid admin token"
        )
