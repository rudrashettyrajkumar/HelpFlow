"""The trial gate — atomic guarded-UPDATE trial counter, the 403 gate payload,
and the JWT-ownership check the whole workspace surface hangs off (spec E5
Req 3/5, ARCHITECTURE §5.3/§6, CLAUDE.md invariant #4/#9/#11).
"""

from __future__ import annotations

from functools import cache
from pathlib import Path

from backend.utils import supabase_client
from backend.utils.config import get_settings

_PROMPTS_DIR = Path(__file__).resolve().parents[1] / "prompts"

#: The 2-trial-workspaces-per-account cap (ARCHITECTURE §5.3) — the number
#: itself is baked into the guarded UPDATE's WHERE clause below, same as the
#: FROZEN status enum is baked into the schema: it's the invariant, not a tunable.
MAX_TRIAL_WORKSPACES = 2


async def increment_trial(user_id: str) -> bool:
    """Atomically claim one of the account's `MAX_TRIAL_WORKSPACES` slots.

    ONE guarded UPDATE — `trials_used < 2` is the guard, row-locked by
    Postgres for the duration of the statement, so two simultaneous calls for
    the same account can never both succeed (the guarded-transition pattern,
    ARCHITECTURE §5.3, CLAUDE.md invariant #4). Returns True iff THIS call
    claimed the slot (status tag `'UPDATE 1'`); False means the account
    already had 2 (or a concurrent call won the race) — a safe no-op, not an
    error, and the caller must not create a tenant row.
    """
    tag = await supabase_client.execute(
        "UPDATE users SET trials_used = trials_used + 1 WHERE id = $1 AND trials_used < 2",
        user_id,
    )
    return tag == "UPDATE 1"


@cache
def _trial_limit_message() -> str:
    return (_PROMPTS_DIR / "trial_limit.md").read_text(encoding="utf-8").strip()


async def gate_payload() -> dict:
    """The 403 body when the trial gate blocks a new workspace (§6/§5.3).

    Contact links come from env, never hardcoded (invariant #8) — a blank env
    value degrades to an omitted link rather than a broken one.
    """
    settings = get_settings()
    return {
        "code": "trial_limit",
        "message": _trial_limit_message(),
        "contact": {
            "linkedin": settings.RAJ_LINKEDIN_URL,
            "whatsapp": settings.RAJ_WHATSAPP_URL,
            "email": settings.RAJ_EMAIL,
        },
        "form": True,
    }


async def is_owner(tenant_id: str, user_id: str) -> bool:
    """Whether `user_id` owns `tenant_id` (spec Req 5, ARCHITECTURE §5.5).

    Used both by `/api/workspaces/{id}` and by the JWT branch of
    `middleware.tenant_auth.require_admin_tenant` — a wrong owner is a 404,
    not a 403, so a request can never be used to probe whether a tenant id
    exists at all.
    """
    row = await supabase_client.fetchrow(
        "SELECT 1 FROM tenants WHERE id = $1 AND owner_user_id = $2", tenant_id, user_id
    )
    return row is not None
