"""User accounts service — register/authenticate/load against a mocked
`supabase_client` (spec E5 Required tests). Real Postgres uniqueness is
exercised live by `sql/assert_users_trials.sql` against Supabase."""

from datetime import UTC, datetime
from unittest.mock import patch

import asyncpg
import pytest

from backend.services.users import (
    AuthUnavailable,
    EmailAlreadyRegistered,
    InvalidCredentials,
    authenticate,
    load_user,
    register_user,
)
from backend.utils.security import hash_password

_NOW = datetime.now(UTC)


async def test_register_user_returns_the_new_account():
    async def fake_fetchrow(query, *args):
        assert "INSERT INTO users" in query
        return {"id": "user-1", "email": "a@b.com", "trials_used": 0, "created_at": _NOW}

    with patch("backend.services.users.supabase_client.fetchrow", fake_fetchrow):
        user = await register_user("A@B.com", "password123")

    assert user.id == "user-1"
    assert user.email == "a@b.com"  # normalized lowercase
    assert user.trials_used == 0


async def test_register_user_raises_on_duplicate_email():
    async def fake_fetchrow(query, *args):
        raise asyncpg.UniqueViolationError("duplicate key value violates unique constraint")

    with (
        patch("backend.services.users.supabase_client.fetchrow", fake_fetchrow),
        pytest.raises(EmailAlreadyRegistered),
    ):
        await register_user("dup@example.com", "password123")


async def test_register_user_raises_auth_unavailable_on_store_outage():
    async def fake_fetchrow(query, *args):
        raise ConnectionError("db unreachable")

    with (
        patch("backend.services.users.supabase_client.fetchrow", fake_fetchrow),
        pytest.raises(AuthUnavailable),
    ):
        await register_user("a@b.com", "password123")


async def test_authenticate_succeeds_with_correct_password():
    stored = hash_password("password123")

    async def fake_fetchrow(query, *args):
        return {
            "id": "user-1",
            "email": "a@b.com",
            "password_hash": stored,
            "trials_used": 1,
            "created_at": _NOW,
        }

    with patch("backend.services.users.supabase_client.fetchrow", fake_fetchrow):
        user = await authenticate("a@b.com", "password123")

    assert user.id == "user-1"
    assert user.trials_used == 1


async def test_authenticate_rejects_wrong_password():
    stored = hash_password("password123")

    async def fake_fetchrow(query, *args):
        return {
            "id": "user-1",
            "email": "a@b.com",
            "password_hash": stored,
            "trials_used": 0,
            "created_at": _NOW,
        }

    with (
        patch("backend.services.users.supabase_client.fetchrow", fake_fetchrow),
        pytest.raises(InvalidCredentials),
    ):
        await authenticate("a@b.com", "wrong-password")


async def test_authenticate_rejects_unknown_email_with_same_exception():
    async def fake_fetchrow(query, *args):
        return None

    with (
        patch("backend.services.users.supabase_client.fetchrow", fake_fetchrow),
        pytest.raises(InvalidCredentials),
    ):
        await authenticate("nobody@example.com", "whatever")


async def test_load_user_returns_none_for_unknown_id():
    async def fake_fetchrow(query, *args):
        return None

    with patch("backend.services.users.supabase_client.fetchrow", fake_fetchrow):
        assert await load_user("missing") is None


async def test_load_user_raises_auth_unavailable_on_store_outage():
    async def fake_fetchrow(query, *args):
        raise ConnectionError("db unreachable")

    with (
        patch("backend.services.users.supabase_client.fetchrow", fake_fetchrow),
        pytest.raises(AuthUnavailable),
    ):
        await load_user("user-1")
