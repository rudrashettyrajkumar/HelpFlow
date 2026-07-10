"""JWT auth dependency: decode-only identity, and the live-account load for
`/api/auth/me` (spec E5 Required tests)."""

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from backend.middleware.jwt_auth import get_current_user, get_current_user_id
from backend.services.users import AuthUnavailable, AuthUser
from backend.utils.security import issue_jwt


def _creds(token: str) -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


async def test_get_current_user_id_returns_sub_from_a_valid_token():
    token = issue_jwt(user_id="user-1")
    assert await get_current_user_id(_creds(token)) == "user-1"


async def test_get_current_user_id_401s_on_missing_credentials():
    with pytest.raises(HTTPException) as exc_info:
        await get_current_user_id(None)
    assert exc_info.value.status_code == 401


async def test_get_current_user_id_401s_on_tampered_token():
    token = issue_jwt(user_id="user-1")
    with pytest.raises(HTTPException) as exc_info:
        await get_current_user_id(_creds(token + "tampered"))
    assert exc_info.value.status_code == 401


async def test_get_current_user_id_401s_on_expired_token():
    token = issue_jwt(user_id="user-1", now=datetime.now(UTC) - timedelta(days=30))
    with pytest.raises(HTTPException) as exc_info:
        await get_current_user_id(_creds(token))
    assert exc_info.value.status_code == 401


async def test_get_current_user_returns_the_live_account():
    user = AuthUser(id="user-1", email="a@b.com", trials_used=1, created_at=None)

    async def fake_load_user(user_id):
        assert user_id == "user-1"
        return user

    with patch("backend.middleware.jwt_auth.load_user", fake_load_user):
        result = await get_current_user("user-1")
    assert result is user


async def test_get_current_user_401s_when_the_account_is_gone():
    async def fake_load_user(user_id):
        return None

    with patch("backend.middleware.jwt_auth.load_user", fake_load_user):
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user("deleted-user")
    assert exc_info.value.status_code == 401


async def test_get_current_user_503s_on_store_outage():
    async def fake_load_user(user_id):
        raise AuthUnavailable("db down")

    with patch("backend.middleware.jwt_auth.load_user", fake_load_user):
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user("user-1")
    assert exc_info.value.status_code == 503
