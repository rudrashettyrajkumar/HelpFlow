"""Password hashing + our own HS256 JWT — the account security boundary.

PBKDF2-HMAC-SHA256 ported verbatim from DocChat v2 `backend/utils/security.py`:
deliberately dependency-free (no bcrypt/argon2 C-extension), keeping the
container featherweight per CLAUDE.md exactly like the "no local ML models"
rule. Stored format is self-describing so the iteration count can be raised
later without invalidating existing hashes:

    pbkdf2_sha256$<iterations>$<salt_hex>$<hash_hex>

JWT minting/decoding lives here too (spec E5 deliverables), unlike DocChat
where it sits in `middleware/jwt_auth.py` — that module here is purely the
FastAPI Bearer-header → user_id wiring; the account security boundary
(hashing + signing) is kept in one module.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

from jose import jwt

from backend.utils.config import get_settings

_ALGO = "pbkdf2_sha256"
_ITERATIONS = 600_000  # OWASP 2023 guidance for PBKDF2-HMAC-SHA256
_SALT_BYTES = 16
_DKLEN = 32

JWT_ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    """Return a self-describing PBKDF2 hash for `password`."""
    salt = secrets.token_bytes(_SALT_BYTES)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _ITERATIONS, _DKLEN)
    return f"{_ALGO}${_ITERATIONS}${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """Constant-time check of `password` against a stored hash.

    Returns False (never raises) on any malformed stored value — a corrupt
    hash is an auth failure, not a server error.
    """
    try:
        algo, iterations_s, salt_hex, hash_hex = stored.split("$")
        if algo != _ALGO:
            return False
        iterations = int(iterations_s)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(hash_hex)
    except (ValueError, AttributeError):
        return False
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations, len(expected))
    return hmac.compare_digest(dk, expected)


def _secret() -> str:
    secret = get_settings().JWT_SECRET
    if not secret:
        # An auth boundary must never sign/verify with an empty key; refuse
        # loudly. JWT_SECRET is REQUIRED_IN_PROD, so this only bites a misconfig.
        raise RuntimeError("JWT_SECRET is not configured")
    return secret


def issue_jwt(*, user_id: str, now: datetime | None = None) -> str:
    """Sign a token with claims {sub, exp} ONLY (spec E5 Req 2, TTL from
    `JWT_TTL_DAYS`) — no email or other PII in the token itself; every
    protected route re-reads the live account from `sub` when it needs more."""
    now = now or datetime.now(UTC)
    ttl = timedelta(days=get_settings().JWT_TTL_DAYS)
    claims = {"sub": user_id, "exp": now + ttl}
    return jwt.encode(claims, _secret(), algorithm=JWT_ALGORITHM)


def decode_jwt(token: str) -> dict[str, Any]:
    """Decode + verify a token minted by `issue_jwt`.

    Raises `jose.JWTError` (bad signature, malformed, or expired — a subclass)
    on any problem; callers turn that into a clean 401, never a 500.
    """
    return jwt.decode(token, _secret(), algorithms=[JWT_ALGORITHM])
