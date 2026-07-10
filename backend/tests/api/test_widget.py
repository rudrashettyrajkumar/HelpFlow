"""`GET /widget/config` tests (spec E7 Req 8) — `conversation_store` is mocked,
no real Postgres in this test."""

import uuid
from unittest.mock import AsyncMock, patch

_TENANT_ID = str(uuid.uuid4())
_HEADERS = {"X-Widget-Key": _TENANT_ID}


def test_missing_widget_key_is_401(client):
    resp = client.get("/widget/config")
    assert resp.status_code == 401


def test_unknown_tenant_is_404(client):
    with patch("backend.api.widget.conversation_store.get_tenant", AsyncMock(return_value=None)):
        resp = client.get("/widget/config", headers=_HEADERS)
    assert resp.status_code == 404


def test_returns_public_safe_subset_only(client):
    tenant = {
        "id": _TENANT_ID,
        "name": "Acme",
        "widget_config": {
            "greeting": "Hi there!",
            "brand_color": "#6366F1",
            "theme": "dark",
            "tone": "playful",
        },
        "sensitive_intents": ["billing"],
        "plan": "trial",
    }
    with patch("backend.api.widget.conversation_store.get_tenant", AsyncMock(return_value=tenant)):
        resp = client.get("/widget/config", headers=_HEADERS)
    assert resp.status_code == 200
    body = resp.json()
    assert body == {
        "name": "Acme",
        "greeting": "Hi there!",
        "brand_color": "#6366F1",
        "theme": "dark",
    }
    assert "sensitive_intents" not in body
    assert "plan" not in body
    assert "tone" not in body


def test_defaults_when_widget_config_empty(client):
    tenant = {"id": _TENANT_ID, "name": "Acme", "widget_config": {}, "sensitive_intents": []}
    with patch("backend.api.widget.conversation_store.get_tenant", AsyncMock(return_value=tenant)):
        resp = client.get("/widget/config", headers=_HEADERS)
    assert resp.status_code == 200
    assert resp.json() == {"name": "Acme", "greeting": None, "brand_color": None, "theme": None}
