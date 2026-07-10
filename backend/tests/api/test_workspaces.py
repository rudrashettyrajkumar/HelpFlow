"""`POST/GET/DELETE /api/workspaces` (spec E5 Required tests): the trial gate
end to end at the HTTP layer, ownership on delete, and the JWT requirement.
`services.trials`/`supabase_client`/Qdrant are mocked."""

from unittest.mock import AsyncMock, patch

import pytest

from backend.utils.security import issue_jwt


@pytest.fixture
def _auth():
    # JWT_SECRET only exists inside the autouse `_env` fixture's env, so the
    # token must be minted per-test, not at import time.
    token = issue_jwt(user_id="user-1")
    return {"Authorization": f"Bearer {token}"}


def test_create_requires_auth(client):
    resp = client.post(
        "/api/workspaces", json={"name": "Acme", "website_url": "https://acme.example"}
    )
    assert resp.status_code == 401


def test_create_happy_path_returns_201_with_tenant_and_widget_key(client, _auth):
    fake_execute = AsyncMock(return_value=None)

    with (
        patch("backend.api.workspaces.trials.increment_trial", AsyncMock(return_value=True)),
        patch("backend.api.workspaces.supabase_client.execute", fake_execute),
    ):
        resp = client.post(
            "/api/workspaces",
            json={"name": "Acme", "website_url": "https://acme.example"},
            headers=_auth,
        )

    assert resp.status_code == 201
    body = resp.json()
    assert body["tenant"]["name"] == "Acme"
    assert body["tenant"]["plan"] == "trial"
    assert body["widget_key"] == body["tenant"]["id"]
    fake_execute.assert_awaited_once()


def test_create_blocked_by_gate_is_403_with_gate_payload(client, _auth):
    async def fake_gate_payload():
        return {"code": "trial_limit", "message": "nope", "contact": {}, "form": True}

    with (
        patch("backend.api.workspaces.trials.increment_trial", AsyncMock(return_value=False)),
        patch("backend.api.workspaces.trials.gate_payload", fake_gate_payload),
    ):
        resp = client.post(
            "/api/workspaces",
            json={"name": "Acme", "website_url": "https://acme.example"},
            headers=_auth,
        )

    assert resp.status_code == 403
    assert resp.json()["code"] == "trial_limit"


def test_list_is_owner_scoped(client, _auth):
    async def fake_fetch(query, user_id):
        assert user_id == "user-1"
        return [
            {
                "id": "tenant-1",
                "name": "Acme",
                "website_url": "https://acme.example",
                "plan": "trial",
                "created_at": None,
                "sources_ready": 2,
                "sources_total": 3,
            }
        ]

    with patch("backend.api.workspaces.supabase_client.fetch", fake_fetch):
        resp = client.get("/api/workspaces", headers=_auth)

    assert resp.status_code == 200
    body = resp.json()
    assert body[0]["status"] == "ready"
    assert body[0]["sources_total"] == 3


def test_delete_returns_404_for_a_workspace_you_do_not_own(client, _auth):
    with patch("backend.api.workspaces.trials.is_owner", AsyncMock(return_value=False)):
        resp = client.delete("/api/workspaces/someone-elses-tenant", headers=_auth)
    assert resp.status_code == 404


def test_delete_happy_path_purges_qdrant_and_the_row(client, _auth):
    fake_qdrant = AsyncMock()
    fake_execute = AsyncMock(return_value="DELETE 1")

    with (
        patch("backend.api.workspaces.trials.is_owner", AsyncMock(return_value=True)),
        patch("backend.api.workspaces.get_qdrant", return_value=fake_qdrant),
        patch("backend.api.workspaces.supabase_client.execute", fake_execute),
    ):
        resp = client.delete("/api/workspaces/tenant-1", headers=_auth)

    assert resp.status_code == 200
    assert resp.json() == {"deleted": True}
    fake_qdrant.delete.assert_awaited_once()
    fake_execute.assert_awaited_once_with("DELETE FROM tenants WHERE id = $1", "tenant-1")
