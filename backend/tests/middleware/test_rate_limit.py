"""Plan-aware tenant daily message cap (spec E5 Req 4: `TRIAL_MESSAGES_DAILY`
clamps plan='trial' workspaces; everything else keeps the v1 limit)."""

from unittest.mock import patch

import pytest

from backend.middleware.rate_limit import RateLimitExceeded, check_tenant_message_limit


async def test_trial_plan_is_capped_at_trial_messages_daily():
    async def fake_get(key):
        return "40"  # == TRIAL_MESSAGES_DAILY

    with patch("backend.middleware.rate_limit.get_redis") as fake_get_redis:
        fake_get_redis.return_value.get = fake_get
        with pytest.raises(RateLimitExceeded, match="40/day"):
            await check_tenant_message_limit("tenant-1", "trial")


async def test_trial_plan_under_the_cap_passes():
    async def fake_get(key):
        return "39"

    with patch("backend.middleware.rate_limit.get_redis") as fake_get_redis:
        fake_get_redis.return_value.get = fake_get
        await check_tenant_message_limit("tenant-1", "trial")  # no raise


async def test_premium_plan_keeps_the_v1_limit():
    async def fake_get(key):
        return "40"  # over the trial cap, but under the v1 200/day limit

    with patch("backend.middleware.rate_limit.get_redis") as fake_get_redis:
        fake_get_redis.return_value.get = fake_get
        await check_tenant_message_limit("tenant-1", "premium")  # no raise


async def test_unknown_plan_defaults_to_the_v1_limit():
    async def fake_get(key):
        return "40"

    with patch("backend.middleware.rate_limit.get_redis") as fake_get_redis:
        fake_get_redis.return_value.get = fake_get
        await check_tenant_message_limit("tenant-1", None)  # no raise
