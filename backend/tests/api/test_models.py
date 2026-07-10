"""`GET /api/models` · `POST /api/models/validate` (spec E4 Req 4)."""

from __future__ import annotations

from unittest.mock import patch


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
