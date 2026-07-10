"""Schema shape: static assertions that the FROZEN contracts are present in the
SQL exactly as ARCHITECTURE §5.2/§5.3 specifies. The live behaviour (CHECK,
UNIQUE, RLS) is proven by sql/assert_schema.sql against real Supabase; this test
is the fast guard that stops an accidental edit to a frozen contract from ever
being committed."""

import re
from pathlib import Path

_SQL_DIR = Path(__file__).resolve().parents[2] / "sql"
_SCHEMA = (_SQL_DIR / "001_schema.sql").read_text(encoding="utf-8")
_VIEWS = (_SQL_DIR / "002_views_rls.sql").read_text(encoding="utf-8")
_USERS_TRIALS = (_SQL_DIR / "003_users_trials.sql").read_text(encoding="utf-8")


def _norm(sql: str) -> str:
    """Collapse whitespace so multi-line SQL can be matched as one string."""
    return re.sub(r"\s+", " ", sql.lower())


def test_status_enum_is_exactly_frozen():
    norm = _norm(_SCHEMA)
    # The FROZEN enum, in order (ARCHITECTURE §5.2). Any drift is a contract break.
    expected = (
        "check (status in "
        "('ai_handling','needs_human','human_assigned','resolved','abandoned'))"
    )
    assert expected in norm


def test_conversations_unique_find_or_create_key():
    assert "unique (tenant_id, channel, external_ref)" in _norm(_SCHEMA)


def test_all_base_tables_present():
    norm = _norm(_SCHEMA)
    for table in ("tenants", "sources", "conversations", "messages", "escalations", "events"):
        assert f"create table if not exists {table}" in norm


def test_required_indexes_present():
    norm = _norm(_SCHEMA)
    assert "on conversations(tenant_id, status)" in norm
    assert "on messages(conversation_id)" in norm
    assert "on events(conversation_id)" in norm


def test_updated_at_trigger_present():
    norm = _norm(_SCHEMA)
    assert "set_updated_at()" in norm
    assert "before update on conversations" in norm


def test_rls_enabled_on_every_base_table():
    norm = _norm(_VIEWS)
    for table in ("tenants", "sources", "conversations", "messages", "escalations", "events"):
        assert re.search(
            rf"alter table {table} enable row level security", norm
        ), f"RLS not enabled on {table}"


def test_masked_views_granted_to_anon():
    norm = _norm(_VIEWS)
    for view in ("v_conversations", "v_funnel", "v_gaps", "v_events"):
        assert f"create or replace view {view}" in norm
    assert "grant select on v_conversations, v_funnel, v_gaps, v_events to anon" in norm


def test_email_mask_function_present():
    norm = _norm(_VIEWS)
    assert "function mask_email" in norm
    assert "mask_email(c.customer_email)" in norm


# --------------------------------------------------------- 003_users_trials (E5)


def test_003_is_additive_only_and_never_touches_001_or_002():
    # The FROZEN files themselves are untouched (git diff proves this on
    # review); this test guards the intent — 003 must not DROP/ALTER-away
    # anything the frozen files define.
    norm = _norm(_USERS_TRIALS)
    assert "drop table" not in norm
    assert "drop column" not in norm


def test_users_and_premium_leads_tables_present():
    norm = _norm(_USERS_TRIALS)
    assert "create table if not exists users" in norm
    assert "create table if not exists premium_leads" in norm


def test_users_email_is_citext_unique():
    norm = _norm(_USERS_TRIALS)
    assert "email         citext unique not null" in norm or "email citext unique not null" in norm


def test_premium_leads_source_check():
    norm = _norm(_USERS_TRIALS)
    assert "check (source in ('gate', 'landing'))" in norm


def test_tenants_gains_owner_and_plan_columns():
    norm = _norm(_USERS_TRIALS)
    assert "add column if not exists owner_user_id uuid references users(id)" in norm
    assert "check (plan in ('demo', 'trial', 'premium'))" in norm


def test_rls_enabled_on_users_and_premium_leads_with_no_anon_grant():
    norm = _norm(_USERS_TRIALS)
    assert "alter table users enable row level security" in norm
    assert "alter table premium_leads enable row level security" in norm
    assert "revoke all on users, premium_leads from anon" in norm
