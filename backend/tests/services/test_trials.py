"""The trial gate: the guarded UPDATE, its concurrency guarantee, the 403 gate
payload, and workspace ownership (spec E5 Required tests — "write the
concurrency test first"). Real end-to-end atomicity is proven live by
`sql/assert_users_trials.sql` against Supabase; the concurrency test below
proves `increment_trial` makes exactly ONE atomic call (never a Python-level
read-then-write) by racing it against a fake store whose lock models
Postgres's real row-level locking during an UPDATE."""

import asyncio
from unittest.mock import patch

from backend.services import trials


async def test_increment_trial_true_when_it_claims_a_slot():
    async def fake_execute(query, *args):
        assert "trials_used = trials_used + 1" in query
        assert "trials_used < 2" in query
        return "UPDATE 1"

    with patch("backend.services.trials.supabase_client.execute", fake_execute):
        assert await trials.increment_trial("user-1") is True


async def test_increment_trial_false_when_the_gate_is_shut():
    async def fake_execute(query, *args):
        return "UPDATE 0"

    with patch("backend.services.trials.supabase_client.execute", fake_execute):
        assert await trials.increment_trial("user-1") is False


class _FakeUsersRow:
    """Models the ONE thing that actually guarantees the trial-gate invariant:
    Postgres serializes concurrent `UPDATE`s against the same row via its row
    lock. The `asyncio.Lock` here stands in for that lock — real Postgres
    would provide it for free; this fake makes the guarantee visible to a
    hermetic unit test."""

    def __init__(self, trials_used: int) -> None:
        self.trials_used = trials_used
        self._lock = asyncio.Lock()

    async def execute(self, query: str, *args: object) -> str:
        async with self._lock:
            await asyncio.sleep(0)  # force a real scheduling point under the lock
            if self.trials_used < 2:
                self.trials_used += 1
                return "UPDATE 1"
            return "UPDATE 0"


async def test_two_simultaneous_creates_at_trials_used_1_claim_exactly_one_slot():
    row = _FakeUsersRow(trials_used=1)

    with patch("backend.services.trials.supabase_client.execute", row.execute):
        first, second = await asyncio.gather(
            trials.increment_trial("user-1"), trials.increment_trial("user-1")
        )

    assert sorted([first, second]) == [False, True]
    assert row.trials_used == 2


async def test_gate_payload_carries_env_contact_links(monkeypatch):
    monkeypatch.setenv("RAJ_LINKEDIN_URL", "https://linkedin.example/raj")
    monkeypatch.setenv("RAJ_WHATSAPP_URL", "https://wa.me/example")
    monkeypatch.setenv("RAJ_EMAIL", "raj@example.com")
    from backend.utils.config import get_settings

    get_settings.cache_clear()
    trials._trial_limit_message.cache_clear()

    payload = await trials.gate_payload()

    assert payload["code"] == "trial_limit"
    assert payload["contact"] == {
        "linkedin": "https://linkedin.example/raj",
        "whatsapp": "https://wa.me/example",
        "email": "raj@example.com",
    }
    assert payload["form"] is True
    assert payload["message"]
    get_settings.cache_clear()


async def test_is_owner_true_when_the_tenant_row_matches():
    async def fake_fetchrow(query, *args):
        assert args == ("tenant-1", "user-1")
        return {"?column?": 1}

    with patch("backend.services.trials.supabase_client.fetchrow", fake_fetchrow):
        assert await trials.is_owner("tenant-1", "user-1") is True


async def test_is_owner_false_when_no_row_matches():
    async def fake_fetchrow(query, *args):
        return None

    with patch("backend.services.trials.supabase_client.fetchrow", fake_fetchrow):
        assert await trials.is_owner("tenant-1", "someone-else") is False
