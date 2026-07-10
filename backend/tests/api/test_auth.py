"""`POST /api/auth/register` · `POST /api/auth/login` · `GET /api/auth/me`
(spec E5 Required tests). `services.users`/`supabase_client` are mocked."""

from datetime import UTC, datetime
from unittest.mock import patch

from backend.services.users import (
    AuthUnavailable,
    AuthUser,
    EmailAlreadyRegistered,
    InvalidCredentials,
)
from backend.utils.security import issue_jwt

_NOW = datetime.now(UTC)
_USER = AuthUser(id="user-1", email="a@b.com", trials_used=0, created_at=_NOW)


def test_register_happy_path_returns_token_and_user(client):
    async def fake_register(email, password):
        assert email == "a@b.com"
        return _USER

    with patch("backend.api.auth.register_user", fake_register):
        resp = client.post(
            "/api/auth/register", json={"email": "a@b.com", "password": "password123"}
        )

    assert resp.status_code == 201
    body = resp.json()
    assert body["user"]["id"] == "user-1"
    assert body["token"]


def test_register_rejects_short_password(client):
    resp = client.post("/api/auth/register", json={"email": "a@b.com", "password": "short"})
    assert resp.status_code == 422


def test_register_rejects_invalid_email(client):
    resp = client.post(
        "/api/auth/register", json={"email": "not-an-email", "password": "password123"}
    )
    assert resp.status_code == 422


def test_register_duplicate_email_is_409(client):
    async def fake_register(email, password):
        raise EmailAlreadyRegistered(email)

    with patch("backend.api.auth.register_user", fake_register):
        resp = client.post(
            "/api/auth/register", json={"email": "a@b.com", "password": "password123"}
        )
    assert resp.status_code == 409


def test_register_store_outage_is_503(client):
    async def fake_register(email, password):
        raise AuthUnavailable("db down")

    with patch("backend.api.auth.register_user", fake_register):
        resp = client.post(
            "/api/auth/register", json={"email": "a@b.com", "password": "password123"}
        )
    assert resp.status_code == 503


def test_login_happy_path_returns_token(client):
    async def fake_authenticate(email, password):
        return _USER

    with patch("backend.api.auth.authenticate", fake_authenticate):
        resp = client.post("/api/auth/login", json={"email": "a@b.com", "password": "password123"})

    assert resp.status_code == 200
    assert resp.json()["token"]


def test_login_wrong_credentials_is_401(client):
    async def fake_authenticate(email, password):
        raise InvalidCredentials

    with patch("backend.api.auth.authenticate", fake_authenticate):
        resp = client.post(
            "/api/auth/login", json={"email": "a@b.com", "password": "wrong-password"}
        )
    assert resp.status_code == 401


def test_me_requires_auth(client):
    resp = client.get("/api/auth/me")
    assert resp.status_code == 401


def test_me_returns_profile_trials_and_workspaces(client):
    token = issue_jwt(user_id="user-1")

    async def fake_load_user(user_id):
        return _USER

    async def fake_fetch(query, user_id):
        assert user_id == "user-1"
        return [
            {
                "id": "tenant-1",
                "name": "Acme",
                "website_url": "https://acme.example",
                "plan": "trial",
                "created_at": _NOW,
            }
        ]

    with (
        patch("backend.middleware.jwt_auth.load_user", fake_load_user),
        patch("backend.api.auth.supabase_client.fetch", fake_fetch),
    ):
        resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["user"]["id"] == "user-1"
    assert body["trials_used"] == 0
    assert body["workspaces"][0]["name"] == "Acme"
