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
