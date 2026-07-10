-- WF-P idempotency assertion (spec E6 Required verification). Proves the
-- partial unique index on events(detail->>'lead_id') WHERE type='lead_notified'
-- makes the guarded insert-if-absent pattern a safe no-op on retry — the same
-- proof shape as assert_users_trials.sql. Non-destructive: rolls back at the end.
--
-- Run:  psql "$SUPABASE_DB_URL" -v ON_ERROR_STOP=1 -f sql/assert_events_idempotency.sql
-- Paste the transcript into the session summary.

\set ON_ERROR_STOP on
begin;

\echo '=== 1. first insert-if-absent for a lead_id succeeds ==='
do $$
declare
  n int;
begin
  insert into events (conversation_id, type, detail)
    values (null, 'lead_notified', jsonb_build_object('lead_id', 'assert-lead-1'))
    on conflict ((detail ->> 'lead_id')) where type = 'lead_notified'
    do nothing;
  select count(*) into n from events
    where type = 'lead_notified' and detail ->> 'lead_id' = 'assert-lead-1';
  if n <> 1 then
    raise exception 'ASSERT FAIL: expected 1 lead_notified row, got %', n;
  end if;
  raise notice 'OK: 1st insert-if-absent landed 1 row';
end $$;

\echo
\echo '=== 2. a retried webhook (same lead_id) is a safe no-op ==='
do $$
declare
  n int;
begin
  insert into events (conversation_id, type, detail)
    values (null, 'lead_notified', jsonb_build_object('lead_id', 'assert-lead-1'))
    on conflict ((detail ->> 'lead_id')) where type = 'lead_notified'
    do nothing;
  select count(*) into n from events
    where type = 'lead_notified' and detail ->> 'lead_id' = 'assert-lead-1';
  if n <> 1 then
    raise exception 'ASSERT FAIL: expected the retry to still land exactly 1 row, got %', n;
  end if;
  raise notice 'OK: retried insert was a safe no-op — still 1 row, Raj is not double-pinged';
end $$;

\echo
\echo '=== 3. a different lead_id is unaffected (index is scoped per lead_id, not global) ==='
do $$
declare
  n int;
begin
  insert into events (conversation_id, type, detail)
    values (null, 'lead_notified', jsonb_build_object('lead_id', 'assert-lead-2'))
    on conflict ((detail ->> 'lead_id')) where type = 'lead_notified'
    do nothing;
  select count(*) into n from events where type = 'lead_notified';
  if n <> 2 then
    raise exception 'ASSERT FAIL: expected 2 distinct lead_notified rows, got %', n;
  end if;
  raise notice 'OK: a different lead_id inserted independently — 2 rows total';
end $$;

\echo
\echo '=== rollback (non-destructive) ==='
rollback;
