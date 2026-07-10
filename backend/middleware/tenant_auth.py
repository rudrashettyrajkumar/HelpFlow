"""Auth dependencies — public widget key → tenant, and the admin/owner bearer.

ARCHITECTURE §7.1: `tenant_id` is resolved from a public **widget key** sent by
the embed (`X-Widget-Key`), NOT trusted as a raw id from the client; the owner
`/admin/*` routes sit behind either the shared `ADMIN_TOKEN` (scripts/seeding)
or, since E5, a JWT whose account owns the workspace.

E1 SCOPE (flagged): the widget-key → tenant lookup is stubbed. The demo treats
the `X-Widget-Key` value as the tenant id directly so downstream epics can wire
routes now; E2/E6 replace `resolve_tenant` with a real lookup (a `widget_key`
column / mapping on `tenants`) without changing this dependency's signature.
`POST /api/workspaces` (E5, `api/workspaces.py`) mirrors this same stub: the
`widget_key` it returns IS the tenant id, for the same reason.
"""

from __future__ import annotations

import secrets

from fastapi import Header, HTTPException, status
from jose import JWTError

from backend.services import trials
from backend.utils.config import get_settings
from backend.utils.security import decode_jwt


def _bearer_token(authorization: str | None) -> str:
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return ""


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
    token = get_settings().ADMIN_TOKEN
    supplied = _bearer_token(authorization)
    if not token or not supplied or not secrets.compare_digest(supplied, token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid admin token"
        )


async def require_admin_tenant(
    authorization: str | None = Header(default=None),
    x_tenant_id: str | None = Header(default=None),
) -> str:
    """Gate `/admin/sources*` (E2; JWT-scoped in E5, spec Req 5): EITHER the
    legacy `ADMIN_TOKEN` bearer (any tenant — scripts/seeding, unchanged) OR a
    JWT whose account owns the `X-Tenant-Id` workspace.

    A wrong-owner JWT is a 404, not a 403 (don't leak whether the tenant id
    exists at all); a missing/unparseable/expired bearer is a 401 either way —
    we genuinely don't know who's asking. `require_admin`'s DESIGN CHOICE note
    (a shared `X-Tenant-Id` header rather than a real per-tenant admin
    credential store) still applies to the ADMIN_TOKEN branch.

    ALSO REUSABLE (flagged): E9's `/conversations*` console routes need this
    exact same admin-OR-owner check per ARCHITECTURE §7.1/spec Req 5, but
    those routes don't exist in this codebase yet (console is E9) — nothing to
    wire it into this epic. E9 should depend on this function unchanged.

    Auth is checked BEFORE the tenant header (E1/E2 precedent, `require_admin`
    unchanged): no credential at all is a 401 whether or not `X-Tenant-Id` was
    sent; only once SOME credential is recognized (ADMIN_TOKEN or a valid JWT)
    does a missing tenant header become the 400.
    """
    settings = get_settings()
    supplied = _bearer_token(authorization)
    admin_match = bool(
        settings.ADMIN_TOKEN and supplied and secrets.compare_digest(supplied, settings.ADMIN_TOKEN)
    )

    user_id: str | None = None
    if not admin_match:
        if not supplied:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid admin token"
            )
        try:
            user_id = decode_jwt(supplied).get("sub")
        except JWTError:
            user_id = None
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid admin token"
            )

    if not x_tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="missing X-Tenant-Id"
        )

    if admin_match:
        return x_tenant_id

    if not await trials.is_owner(x_tenant_id, user_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found.")
    return x_tenant_id
