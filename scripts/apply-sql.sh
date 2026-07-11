#!/usr/bin/env bash
# Idempotent SQL runner against Supabase (spec E1 Req 4 / acceptance:
# "runs clean twice"). Applies the migrations in order, then optionally the
# assertion script.
#
# Usage:
#   SUPABASE_DB_URL="postgres://...session-pooler..." scripts/apply-sql.sh
#   SUPABASE_DB_URL=... scripts/apply-sql.sh --assert   # also run assertions
#
# Requires: psql on PATH. SUPABASE_DB_URL must be the SESSION POOLER connection
# string (the direct db host is IPv6-only on Supabase free tier).
set -euo pipefail

: "${SUPABASE_DB_URL:?set SUPABASE_DB_URL to the Supabase session-pooler connection string}"

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SQL_DIR="$ROOT/sql"

run() {
  echo "== applying $1 =="
  psql "$SUPABASE_DB_URL" -v ON_ERROR_STOP=1 -f "$SQL_DIR/$1"
}

run 001_schema.sql
run 002_views_rls.sql
run 003_users_trials.sql
run 004_events_idempotency.sql
run 005_gap_clusters.sql
run 006_ops_markers.sql

if [[ "${1:-}" == "--assert" ]]; then
  echo "== running assertions =="
  psql "$SUPABASE_DB_URL" -v ON_ERROR_STOP=1 -f "$SQL_DIR/assert_schema.sql"
  psql "$SUPABASE_DB_URL" -v ON_ERROR_STOP=1 -f "$SQL_DIR/assert_users_trials.sql"
  psql "$SUPABASE_DB_URL" -v ON_ERROR_STOP=1 -f "$SQL_DIR/assert_events_idempotency.sql"
fi

echo "== done =="
