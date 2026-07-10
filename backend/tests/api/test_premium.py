"""`POST /api/premium-contact` (spec E5 Required tests): the row is the source
of truth even when the WF-P webhook fails, rate limiting, and optional auth.
`supabase_client`/Redis/httpx are mocked."""

from unittest.mock import AsyncMock, patch

from backend.utils.security import issue_jwt

_LEAD_ROW = {"id": "lead-1"}


def test_anonymous_submission_is_202_and_inserts_a_row(client):
    async def fake_fetchrow(query, *args):
        assert args[0] is None  # no JWT -> user_id is NULL
        return _LEAD_ROW

    with (
        patch("backend.api.premium.supabase_client.fetchrow", fake_fetchrow),
        patch("backend.api.premium.get_redis") as fake_get_redis,
    ):
        fake_get_redis.return_value.incr = AsyncMock(return_value=1)
        fake_get_redis.return_value.expire = AsyncMock(return_value=1)
        resp = client.post(
            "/api/premium-contact",
            json={"name": "Jo", "email": "jo@example.com", "message": "tell me more"},
        )

    assert resp.status_code == 202
    assert resp.json()["id"] == "lead-1"


def test_logged_in_submission_attaches_user_id(client):
    token = issue_jwt(user_id="user-1")

    async def fake_fetchrow(query, *args):
        assert args[0] == "user-1"
        return _LEAD_ROW

    with (
        patch("backend.api.premium.supabase_client.fetchrow", fake_fetchrow),
        patch("backend.api.premium.get_redis") as fake_get_redis,
    ):
        fake_get_redis.return_value.incr = AsyncMock(return_value=1)
        fake_get_redis.return_value.expire = AsyncMock(return_value=1)
        resp = client.post(
            "/api/premium-contact",
            json={
                "name": "Jo",
                "email": "jo@example.com",
                "message": "tell me more",
                "source": "gate",
            },
            headers={"Authorization": f"Bearer {token}"},
        )

    assert resp.status_code == 202


def test_over_the_daily_ip_cap_is_429(client):
    async def fake_fetchrow(query, *args):  # pragma: no cover — must not be reached
        raise AssertionError("insert must not run once the IP cap is hit")

    with (
        patch("backend.api.premium.supabase_client.fetchrow", fake_fetchrow),
        patch("backend.api.premium.get_redis") as fake_get_redis,
    ):
        # 4 is over PREMIUM_CONTACT_DAILY_PER_IP=3
        fake_get_redis.return_value.incr = AsyncMock(return_value=4)
        resp = client.post(
            "/api/premium-contact",
            json={"name": "Jo", "email": "jo@example.com", "message": "tell me more"},
        )

    assert resp.status_code == 429


def test_webhook_failure_still_returns_202_and_logs_a_workflow_error_event(client, monkeypatch):
    monkeypatch.setenv("N8N_PREMIUM_LEAD_URL", "https://n8n.example/webhook/premium-lead")
    from backend.utils.config import get_settings

    get_settings.cache_clear()

    async def fake_fetchrow(query, *args):
        return _LEAD_ROW

    fake_insert_event = AsyncMock()

    class _RaisingClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def post(self, *args, **kwargs):
            raise ConnectionError("n8n unreachable")

    with (
        patch("backend.api.premium.supabase_client.fetchrow", fake_fetchrow),
        patch("backend.api.premium.get_redis") as fake_get_redis,
        patch("backend.api.premium.httpx.AsyncClient", return_value=_RaisingClient()),
        patch("backend.api.premium.insert_event", fake_insert_event),
    ):
        fake_get_redis.return_value.incr = AsyncMock(return_value=1)
        fake_get_redis.return_value.expire = AsyncMock(return_value=1)
        resp = client.post(
            "/api/premium-contact",
            json={"name": "Jo", "email": "jo@example.com", "message": "tell me more"},
        )

    assert resp.status_code == 202
    fake_insert_event.assert_awaited_once()
    args, _ = fake_insert_event.call_args
    assert args[1] == "workflow_error"

    get_settings.cache_clear()
