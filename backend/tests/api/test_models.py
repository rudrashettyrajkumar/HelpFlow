"""`GET /api/models` · `POST /api/models/validate` · `GET /api/demo-budget`
(spec E4 Req 4, spec E8 Req 4)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch


def test_get_models_returns_the_catalog_verbatim(client):
    resp = client.get("/api/models")
    assert resp.status_code == 200
    body = resp.json()
    provider_ids = {p["id"] for p in body["providers"]}
    assert provider_ids == {"groq", "openrouter", "openai", "anthropic", "gemini"}
    assert set(body["embed_providers"]) == {"openrouter", "openai", "gemini"}

    openrouter = next(p for p in body["providers"] if p["id"] == "openrouter")
    assert openrouter["allows_custom_model"] is True
    model_ids = {m["id"] for m in openrouter["models"]}
    assert "nvidia/nemotron-3-ultra-550b-a55b:free" in model_ids
    embed_ids = {m["id"] for m in openrouter["embedding_models"]}
    assert "nvidia/llama-nemotron-embed-vl-1b-v2:free" in embed_ids


def test_validate_unknown_provider_returns_ok_false(client):
    resp = client.post(
        "/api/models/validate",
        json={"provider": "not-a-provider", "model": "x", "key": "k"},
    )
    assert resp.status_code == 200
    assert resp.json() == {"ok": False, "error_code": "unknown_provider"}


def test_validate_never_echoes_the_key_on_failure(client):
    secret = "gsk_do_not_leak_this_token"
    with patch(
        "backend.api.models.factory.build_chat_model",
        side_effect=RuntimeError("401 unauthorized"),
    ):
        resp = client.post(
            "/api/models/validate",
            json={"provider": "groq", "model": "llama-3.3-70b-versatile", "key": secret},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is False
    assert body["error_code"] == "key_invalid"
    assert secret not in resp.text


def test_demo_budget_degrades_to_full_cap_when_redis_unavailable(client):
    # The autouse `_no_real_redis` fixture makes every Redis call raise —
    # `remaining_today`'s own degrade-never-break contract reports the full cap.
    resp = client.get("/api/demo-budget")
    assert resp.status_code == 200
    body = resp.json()
    assert body["chat"] == {"remaining": 150, "cap": 150}
    assert body["embed"] == {"remaining": 100, "cap": 100}
    assert "resets_at" in body


def test_demo_budget_reports_remaining_from_the_helper(client):
    with patch(
        "backend.api.models.demo_budget.remaining_today", AsyncMock(side_effect=[12, 40])
    ):
        resp = client.get("/api/demo-budget")
    body = resp.json()
    assert body["chat"]["remaining"] == 12
    assert body["embed"]["remaining"] == 40
