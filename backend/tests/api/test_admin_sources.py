"""`/admin/sources` API tests (spec E2 Required tests): all pre-stream
rejection cases (bad url, over-cap max_pages, rate-limited, missing auth), the
happy-path SSE progress stream, and the ownership check on refresh/delete.
`ingest_service`/`rate_limit`/`supabase_client` are mocked — no real network,
Qdrant, Postgres, or Redis in this test.
"""

from __future__ import annotations

import json
import uuid
from unittest.mock import AsyncMock, patch

from backend.ingestion.errors import IngestValidationError

_TENANT_ID = str(uuid.uuid4())
_ADMIN_HEADERS = {"Authorization": "Bearer test-admin-token", "X-Tenant-Id": _TENANT_ID}


def _parse_sse(text: str) -> list[dict]:
    lines = (line for line in text.splitlines() if line.startswith("data: "))
    return [json.loads(line[len("data: ") :]) for line in lines]


async def _no_op_crawl_limit(tenant_id: str) -> None:
    return None


# ---------------------------------------------------------------- auth / validation


def test_missing_admin_token_is_401(client):
    resp = client.post("/admin/sources", json={"url": "https://example.com"})
    assert resp.status_code == 401


def test_wrong_admin_token_is_401(client):
    resp = client.post(
        "/admin/sources",
        json={"url": "https://example.com"},
        headers={"Authorization": "Bearer nope", "X-Tenant-Id": _TENANT_ID},
    )
    assert resp.status_code == 401


def test_missing_tenant_header_is_400(client):
    resp = client.post(
        "/admin/sources",
        json={"url": "https://example.com"},
        headers={"Authorization": "Bearer test-admin-token"},
    )
    assert resp.status_code == 400


def test_missing_url_and_sitemap_is_400(client):
    with patch(
        "backend.api.admin_sources.check_and_increment_tenant_crawl", _no_op_crawl_limit
    ):
        resp = client.post("/admin/sources", json={}, headers=_ADMIN_HEADERS)
    assert resp.status_code == 400
    assert resp.json()["error"] == "missing_url"


def test_invalid_url_is_400(client):
    with patch(
        "backend.api.admin_sources.check_and_increment_tenant_crawl", _no_op_crawl_limit
    ):
        resp = client.post(
            "/admin/sources", json={"url": "not-a-url"}, headers=_ADMIN_HEADERS
        )
    assert resp.status_code == 400
    assert resp.json()["error"] == "invalid_url"


def test_max_pages_over_cap_is_400(client):
    with patch(
        "backend.api.admin_sources.check_and_increment_tenant_crawl", _no_op_crawl_limit
    ):
        resp = client.post(
            "/admin/sources",
            json={"url": "https://example.com", "max_pages": 9999},
            headers=_ADMIN_HEADERS,
        )
    assert resp.status_code == 400
    assert resp.json()["error"] == "max_pages_exceeded"


def test_rate_limited_tenant_is_429(client):
    async def _reject(tenant_id: str) -> None:
        raise IngestValidationError(
            "crawl_limit_exceeded", "limit reached", status_code=429
        )

    with patch("backend.api.admin_sources.check_and_increment_tenant_crawl", _reject):
        resp = client.post(
            "/admin/sources", json={"url": "https://example.com"}, headers=_ADMIN_HEADERS
        )
    assert resp.status_code == 429
    assert resp.json()["error"] == "crawl_limit_exceeded"


# ---------------------------------------------------------------- happy path SSE


def test_create_source_streams_sse_progress(client):
    async def fake_run_ingestion(*, tenant_id, url, sitemap_url, max_pages):
        assert tenant_id == _TENANT_ID
        yield {"stage": "discovering"}
        yield {"stage": "fetching", "done": 1, "total": 1}
        yield {"stage": "embedding", "pct": 100}
        yield {"stage": "ready", "pages": 1, "chunks": 3}

    with (
        patch("backend.api.admin_sources.check_and_increment_tenant_crawl", _no_op_crawl_limit),
        patch("backend.api.admin_sources.run_ingestion", fake_run_ingestion),
    ):
        resp = client.post(
            "/admin/sources", json={"url": "https://example.com"}, headers=_ADMIN_HEADERS
        )

    assert resp.status_code == 200
    events = _parse_sse(resp.text)
    assert events[-1] == {"stage": "ready", "pages": 1, "chunks": 3}
    assert events[0] == {"stage": "discovering"}


# ---------------------------------------------------------------- list / refresh / delete


def test_list_sources_is_tenant_scoped(client):
    rows = [
        {
            "id": uuid.uuid4(),
            "url": "https://example.com/a",
            "title": "A",
            "status": "ready",
            "chunk_count": 5,
            "crawled_at": None,
            "error": None,
        }
    ]

    async def fake_fetch(query, tenant_id):
        assert tenant_id == _TENANT_ID
        return rows

    with patch("backend.api.admin_sources.supabase_client.fetch", fake_fetch):
        resp = client.get("/admin/sources", headers=_ADMIN_HEADERS)

    assert resp.status_code == 200
    body = resp.json()
    assert body[0]["url"] == "https://example.com/a"
    assert body[0]["chunk_count"] == 5


def test_refresh_returns_404_for_another_tenants_source(client):
    other_tenant = str(uuid.uuid4())
    source_id = str(uuid.uuid4())

    async def fake_fetchrow(query, sid):
        return {"id": uuid.UUID(source_id), "tenant_id": uuid.UUID(other_tenant), "url": "https://x.com"}

    with patch("backend.api.admin_sources.supabase_client.fetchrow", fake_fetchrow):
        resp = client.post(f"/admin/sources/{source_id}/refresh", headers=_ADMIN_HEADERS)

    assert resp.status_code == 404


def test_refresh_returns_404_for_unknown_source(client):
    source_id = str(uuid.uuid4())

    async def fake_fetchrow(query, sid):
        return None

    with patch("backend.api.admin_sources.supabase_client.fetchrow", fake_fetchrow):
        resp = client.post(f"/admin/sources/{source_id}/refresh", headers=_ADMIN_HEADERS)

    assert resp.status_code == 404


def test_refresh_happy_path_reingests_owned_source(client):
    source_id = str(uuid.uuid4())

    async def fake_fetchrow(query, sid):
        return {"id": uuid.UUID(source_id), "tenant_id": uuid.UUID(_TENANT_ID), "url": "https://example.com/a"}

    fake_run_refresh = AsyncMock(return_value={"status": "ready", "chunks": 4})

    with (
        patch("backend.api.admin_sources.supabase_client.fetchrow", fake_fetchrow),
        patch("backend.api.admin_sources.run_refresh", fake_run_refresh),
    ):
        resp = client.post(f"/admin/sources/{source_id}/refresh", headers=_ADMIN_HEADERS)

    assert resp.status_code == 200
    assert resp.json() == {"status": "ready", "chunks": 4}
    fake_run_refresh.assert_awaited_once_with(
        tenant_id=_TENANT_ID, source_id=source_id, url="https://example.com/a"
    )


def test_delete_returns_404_for_another_tenants_source(client):
    other_tenant = str(uuid.uuid4())
    source_id = str(uuid.uuid4())

    async def fake_fetchrow(query, sid):
        return {"id": uuid.UUID(source_id), "tenant_id": uuid.UUID(other_tenant), "url": "https://x.com"}

    with patch("backend.api.admin_sources.supabase_client.fetchrow", fake_fetchrow):
        resp = client.delete(f"/admin/sources/{source_id}", headers=_ADMIN_HEADERS)

    assert resp.status_code == 404


def test_delete_happy_path_removes_points_and_row(client):
    source_id = str(uuid.uuid4())

    async def fake_fetchrow(query, sid):
        return {"id": uuid.UUID(source_id), "tenant_id": uuid.UUID(_TENANT_ID), "url": "https://example.com/a"}

    fake_delete_points = AsyncMock()
    fake_execute = AsyncMock(return_value="DELETE 1")

    with (
        patch("backend.api.admin_sources.supabase_client.fetchrow", fake_fetchrow),
        patch("backend.api.admin_sources.supabase_client.execute", fake_execute),
        patch("backend.api.admin_sources.delete_source_points", fake_delete_points),
    ):
        resp = client.delete(f"/admin/sources/{source_id}", headers=_ADMIN_HEADERS)

    assert resp.status_code == 200
    assert resp.json() == {"deleted": True}
    fake_delete_points.assert_awaited_once()
    fake_execute.assert_awaited_once()
