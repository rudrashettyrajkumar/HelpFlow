"""User accounts — Supabase Postgres, self-contained email/password auth.

Adapted from DocChat v2 `backend/services/users.py` (Upstash-backed) to the
Supabase asyncpg store every other HelpFlow write goes through (ARCHITECTURE
§5.2). Email uniqueness is enforced by the `citext` column itself (case-
insensitive, `sql/003_users_trials.sql`) rather than an application-level
lookup-then-insert, so registration is a single INSERT and the uniqueness
guarantee is exactly as atomic as everywhere else in this codebase (guarded
transitions, CLAUDE.md invariant #4).

Auth is a security boundary, so — unlike the data paths that "degrade, never
break" — a store outage here raises `AuthUnavailable`: we must never silently
treat an unreachable database as "no such user" or "password OK".
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import asyncpg

from backend.utils import supabase_client
from backend.utils.security import hash_password, verify_password


@dataclass(frozen=True)
class AuthUser:
    """The public identity attached to a request — never carries the hash."""

    id: str
    email: str
    trials_used: int
    created_at: datetime | None


class EmailAlreadyRegistered(Exception):
    """Signup attempted with an email that already has an account (→ 409)."""


class InvalidCredentials(Exception):
    """Login email unknown or password wrong (→ 401, identical message either way)."""


class AuthUnavailable(Exception):
    """The user store could not be reached — auth can't be decided (→ 503)."""


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def _to_user(record: Any) -> AuthUser:
    return AuthUser(
        id=str(record["id"]),
        email=record["email"],
        trials_used=record["trials_used"],
        created_at=record["created_at"],
    )


async def register_user(email: str, password: str) -> AuthUser:
    """Create a new account. Raises `EmailAlreadyRegistered` / `AuthUnavailable`."""
    email_norm = _normalize_email(email)
    user_id = str(uuid.uuid4())
    password_hash = hash_password(password)
    try:
        row = await supabase_client.fetchrow(
            "INSERT INTO users (id, email, password_hash) VALUES ($1, $2, $3) "
            "RETURNING id, email, trials_used, created_at",
            user_id,
            email_norm,
            password_hash,
        )
    except asyncpg.UniqueViolationError as exc:
        raise EmailAlreadyRegistered(email_norm) from exc
    except Exception as exc:  # noqa: BLE001 — a store outage must not read as "created"
        raise AuthUnavailable(str(exc)) from exc
    if row is None:  # pragma: no cover — INSERT ... RETURNING always returns a row on success
        raise AuthUnavailable("insert returned no row")
    return _to_user(row)


async def authenticate(email: str, password: str) -> AuthUser:
    """Return the user iff the password verifies. Raises `InvalidCredentials`.

    Same exception for unknown-email and wrong-password so the response can't
    be used to enumerate which emails have accounts.
    """
    try:
        row = await supabase_client.fetchrow(
            "SELECT id, email, password_hash, trials_used, created_at FROM users WHERE email = $1",
            _normalize_email(email),
        )
    except Exception as exc:  # noqa: BLE001 — can't verify ⇒ 503, never a false accept
        raise AuthUnavailable(str(exc)) from exc
    if row is None or not verify_password(password, row["password_hash"]):
        raise InvalidCredentials
    return _to_user(row)


async def load_user(user_id: str) -> AuthUser | None:
    """Resolve a JWT `sub` to the current account, or None if it's gone.

    Raises `AuthUnavailable` on a store outage so a protected route returns
    503 rather than pretending the (validly-tokened) user no longer exists.
    """
    try:
        row = await supabase_client.fetchrow(
            "SELECT id, email, trials_used, created_at FROM users WHERE id = $1", user_id
        )
    except Exception as exc:  # noqa: BLE001
        raise AuthUnavailable(str(exc)) from exc
    return _to_user(row) if row else None
