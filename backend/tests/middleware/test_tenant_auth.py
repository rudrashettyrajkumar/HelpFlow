"""`require_admin_tenant`: ADMIN_TOKEN keeps working for scripts; a JWT is
accepted for its OWN workspace and 404s (never 403) for someone else's (spec
E5 Req 5)."""

from unittest.mock import patch

import pytest
from fastapi import HTTPException

from backend.middleware.tenant_auth import require_admin_tenant
from backend.utils.security import issue_jwt


async def test_admin_token_bypasses_ownership_for_any_tenant():
    tenant_id = await require_admin_tenant(
        authorization="Bearer test-admin-token", x_tenant_id="some-tenant"
    )
    assert tenant_id == "some-tenant"


async def test_missing_tenant_header_is_400():
    with pytest.raises(HTTPException) as exc_info:
        await require_admin_tenant(authorization="Bearer test-admin-token", x_tenant_id=None)
    assert exc_info.value.status_code == 400


async def test_missing_authorization_is_401():
    with pytest.raises(HTTPException) as exc_info:
        await require_admin_tenant(authorization=None, x_tenant_id="tenant-1")
    assert exc_info.value.status_code == 401


async def test_owning_jwt_is_accepted():
    token = issue_jwt(user_id="user-1")

    async def fake_is_owner(tenant_id, user_id):
        assert (tenant_id, user_id) == ("tenant-1", "user-1")
        return True

    with patch("backend.middleware.tenant_auth.trials.is_owner", fake_is_owner):
        tenant_id = await require_admin_tenant(
            authorization=f"Bearer {token}", x_tenant_id="tenant-1"
        )
    assert tenant_id == "tenant-1"


async def test_non_owning_jwt_is_404_not_403():
    token = issue_jwt(user_id="user-1")

    async def fake_is_owner(tenant_id, user_id):
        return False

    with patch("backend.middleware.tenant_auth.trials.is_owner", fake_is_owner):
        with pytest.raises(HTTPException) as exc_info:
            await require_admin_tenant(authorization=f"Bearer {token}", x_tenant_id="someone-elses")
    assert exc_info.value.status_code == 404


async def test_garbage_bearer_token_is_401():
    with pytest.raises(HTTPException) as exc_info:
        await require_admin_tenant(authorization="Bearer not-a-jwt", x_tenant_id="tenant-1")
    assert exc_info.value.status_code == 401
