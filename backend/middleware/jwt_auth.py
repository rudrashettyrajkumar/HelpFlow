"""JWT auth dependency — Bearer header → authenticated user_id (spec E5 Req 2,
ARCHITECTURE §7.1). Minting/decoding lives in `utils/security.py`; this module
is just the FastAPI wiring, ported from DocChat v2 `middleware/jwt_auth.py`.

Two dependencies, by need:

* `get_current_user_id` — decode-only, no I/O. The identity key for every
  JWT-scoped route (`/api/workspaces*`, the ownership check on
  `/admin/sources*`): a valid signature already proves *which* account, so
  this stays a hot-path-cheap dependency with no store round-trip.
* `get_current_user` — additionally loads the account from Supabase, for
  `GET /api/auth/me` where the caller wants the live profile.
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError

from backend.services.users import AuthUnavailable, AuthUser, load_user
from backend.utils.security import decode_jwt

_log = logging.getLogger("helpflow.jwt_auth")

# auto_error=False: raise our own uniform JSON 401 for a missing/blank header
# rather than FastAPI's terser default, so every failure mode looks identical.
_bearer = HTTPBearer(auto_error=False)


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or missing authentication.",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_current_user_id(
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> str:
    """The authenticated account id — decode-only (a valid signature is proof)."""
    if creds is None or not creds.credentials:
        raise _unauthorized()
    try:
        claims = decode_jwt(creds.credentials)
    except JWTError as exc:
        # Bad signature, malformed token, and expiry are all auth failures
        # (ExpiredSignatureError is a JWTError subclass), never server errors.
        _log.info("jwt rejected", extra={"reason": repr(exc)})
        raise _unauthorized() from exc
    sub = claims.get("sub")
    if not sub:
        raise _unauthorized()
    return sub


async def get_current_user(
    user_id: Annotated[str, Depends(get_current_user_id)],
) -> AuthUser:
    """The live account behind the token — for `/api/auth/me`.

    A valid token for a since-deleted account is a 401 (the account is gone);
    a store outage is a 503 (we can't say), never a 500.
    """
    try:
        user = await load_user(user_id)
    except AuthUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Sign-in temporarily unavailable. Please try again.",
        ) from exc
    if user is None:
        raise _unauthorized()
    return user
