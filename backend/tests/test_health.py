"""Health: all deps ok → 200 ok; one dep down → 200 degraded (never a 500);
every dep down → 503 degraded (spec E1 Required tests / acceptance)."""

import pytest

from backend.api import health


async def _ok() -> bool:
    return True


async def _boom() -> bool:
    raise RuntimeError("dependency unreachable")


@pytest.fixture
def _all_ok(monkeypatch):
    for name in ("_check_qdrant", "_check_supabase", "_check_redis", "_check_llm"):
        monkeypatch.setattr(health, name, _ok)


def test_all_ok(client, _all_ok):
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body == {"status": "ok", "qdrant": "ok", "supabase": "ok", "redis": "ok", "llm": "ok"}


def test_one_dep_down_is_degraded_not_500(client, monkeypatch, _all_ok):
    # Kill just Qdrant: the app still serves, reports degraded, stays 200.
    monkeypatch.setattr(health, "_check_qdrant", _boom)
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "degraded"
    assert body["qdrant"] == "down"
    assert body["supabase"] == "ok"


def test_all_deps_down_is_503(client, monkeypatch):
    for name in ("_check_qdrant", "_check_supabase", "_check_redis", "_check_llm"):
        monkeypatch.setattr(health, name, _boom)
    resp = client.get("/health")
    assert resp.status_code == 503
    body = resp.json()
    assert body["status"] == "degraded"
    assert all(body[dep] == "down" for dep in ("qdrant", "supabase", "redis", "llm"))
