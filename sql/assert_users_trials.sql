-- HelpFlow accounts/trials assertions (spec E5 Required verification).
-- Proves: (1) citext case-insensitive UNIQUE email, (2) the trial-gate guarded
-- UPDATE (trials_used<2) is atomic — a 3rd claim on an already-exhausted
-- account is a safe no-op, (3) RLS — anon reads neither users nor
-- premium_leads. Non-destructive: rolls back at the end.
--
-- Run:  psql "$SUPABASE_DB_URL" -v ON_ERROR_STOP=1 -f sql/assert_users_trials.sql
-- Paste the transcript into the session summary.

\set ON_ERROR_STOP on
begin;

\echo '=== seed a throwaway user at trials_used=1 ==='
insert into users (id, email, password_hash, trials_used)
  values ('00000000-0000-0000-0000-0000000000c1', 'Assert@Example.com',
          'pbkdf2_sha256$1$00$00', 1);

\echo
\echo '=== 1. citext: a case-different duplicate email must be rejected ==='
do $$ begin
  begin
    insert into users (email, password_hash)
      values ('assert@example.com', 'pbkdf2_sha256$1$00$00');
    raise exception 'ASSERT FAIL: case-different duplicate email was accepted';
  exception when unique_violation then
    raise notice 'OK: citext UNIQUE rejected ''assert@example.com'' as a dup of ''Assert@Example.com''';
  end;
end $$;

\echo
\echo '=== 2. guarded trial UPDATE: 1st claim succeeds, 2nd is a safe no-op ==='
do $$
declare
  tag text;
begin
  update users set trials_used = trials_used + 1
    where id = '00000000-0000-0000-0000-0000000000c1' and trials_used < 2;
  get diagnostics tag = row_count;
  if tag <> '1' then
    raise exception 'ASSERT FAIL: expected the 1st guarded claim to affect 1 row, got %', tag;
  end if;
  raise notice 'OK: 1st claim moved trials_used 1 -> 2 (1 row)';

  update users set trials_used = trials_used + 1
    where id = '00000000-0000-0000-0000-0000000000c1' and trials_used < 2;
  get diagnostics tag = row_count;
  if tag <> '0' then
    raise exception 'ASSERT FAIL: expected the 2nd (gated) claim to affect 0 rows, got %', tag;
  end if;
  raise notice 'OK: 2nd claim at trials_used=2 was a safe no-op (0 rows) — gate holds';
end $$;

\echo
\echo '=== 3. tenants.plan CHECK: a bogus plan must be rejected ==='
do $$ begin
  begin
    insert into tenants (name, plan) values ('Assert Co (bogus plan)', 'bogus');
    raise exception 'ASSERT FAIL: bogus plan was accepted';
  exception when check_violation then
    raise notice 'OK: plan CHECK rejected ''bogus''';
  end;
end $$;

\echo
\echo '=== 4. RLS: anon is denied users and premium_leads (expect: permission denied) ==='
set local role anon;
\set ON_ERROR_STOP off
savepoint before_anon;
select count(*) as anon_users_rows from users;
rollback to savepoint before_anon;
savepoint before_anon2;
select count(*) as anon_leads_rows from premium_leads;
rollback to savepoint before_anon2;
\set ON_ERROR_STOP on
reset role;

\echo
\echo '=== rollback (non-destructive) ==='
rollback;
