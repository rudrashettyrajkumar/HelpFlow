"""`POST /api/auth/register` · `POST /api/auth/login` · `GET /api/auth/me`
(ARCHITECTURE §7.1, spec E5 Req 2).

Register/login both mint our own HS256 JWT immediately so the client can sign
in right after signing up, ported from DocChat v2 `api/auth.py`. Validation is
intentionally light (no `email-validator` dependency): a token `@`-shaped
check plus length bounds — the real uniqueness/identity guarantee is the
`citext` column, not the regex.
"""

from __future__ import annotations

import logging
import re

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator

from backend.middleware.jwt_auth import get_current_user
from backend.services.users import (
    AuthUnavailable,
    AuthUser,
    EmailAlreadyRegistered,
    InvalidCredentials,
    authenticate,
    register_user,
)
from backend.utils import supabase_client
from backend.utils.security import issue_jwt

router = APIRouter()
_log = logging.getLogger("helpflow.api.auth")

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_AUTH_UNAVAILABLE = "Sign-in temporarily unavailable. Please try again."


class Credentials(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=8, max_length=128)

    @field_validator("email")
    @classmethod
    def _valid_email(cls, v: str) -> str:
        v = v.strip().lower()
        if not _EMAIL_RE.match(v):
            raise ValueError("Enter a valid email address.")
        return v


class UserOut(BaseModel):
    id: str
    email: str
    trials_used: int
    created_at: str | None = None


class AuthResponse(BaseModel):
    token: str
    user: UserOut


class MeResponse(BaseModel):
    user: UserOut
    trials_used: int
    workspaces: list[dict]


def _user_out(user: AuthUser) -> UserOut:
    return UserOut(
        id=user.id,
        email=user.email,
        trials_used=user.trials_used,
        created_at=user.created_at.isoformat() if user.created_at else None,
    )


def _auth_response(user: AuthUser) -> AuthResponse:
    return AuthResponse(token=issue_jwt(user_id=user.id), user=_user_out(user))


@router.post("/api/auth/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def register(body: Credentials) -> AuthResponse:
    try:
        user = await register_user(body.email, body.password)
    except EmailAlreadyRegistered as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        ) from exc
    except AuthUnavailable as exc:
        _log.warning("register failed: store unavailable", extra={"reason": str(exc)})
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=_AUTH_UNAVAILABLE
        ) from exc
    return _auth_response(user)


@router.post("/api/auth/login", response_model=AuthResponse)
async def login(body: Credentials) -> AuthResponse:
    try:
        user = await authenticate(body.email, body.password)
    except InvalidCredentials as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect email or password."
        ) from exc
    except AuthUnavailable as exc:
        _log.warning("login failed: store unavailable", extra={"reason": str(exc)})
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=_AUTH_UNAVAILABLE
        ) from exc
    return _auth_response(user)


@router.get("/api/auth/me", response_model=MeResponse)
async def me(user: AuthUser = Depends(get_current_user)) -> MeResponse:
    rows = await supabase_client.fetch(
        "SELECT id, name, website_url, plan, created_at FROM tenants "
        "WHERE owner_user_id = $1 ORDER BY created_at DESC",
        user.id,
    )
    workspaces = [
        {
            "id": str(row["id"]),
            "name": row["name"],
            "website_url": row["website_url"],
            "plan": row["plan"],
            "created_at": row["created_at"].isoformat() if row["created_at"] else None,
        }
        for row in rows
    ]
    return MeResponse(user=_user_out(user), trials_used=user.trials_used, workspaces=workspaces)
