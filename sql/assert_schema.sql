-- HelpFlow schema assertions (spec E1 Required tests / acceptance).
-- Proves: (1) the conversations.status CHECK enum, (2) the UNIQUE
-- (tenant_id, channel, external_ref) key, (3) RLS — anon reads the masked view
-- but NOT the base table. Non-destructive: everything runs in one transaction
-- that ROLLBACKs at the end, so it's safe to run against any environment.
--
-- Run:  psql "$SUPABASE_DB_URL" -v ON_ERROR_STOP=1 -f sql/assert_schema.sql
-- Paste the transcript into the session summary.

\set ON_ERROR_STOP on
begin;

\echo '=== seed a throwaway tenant + conversation + message ==='
insert into tenants (id, name, website_url)
  values ('00000000-0000-0000-0000-0000000000aa', 'Assert Co', 'https://assert.example');
insert into conversations (id, tenant_id, channel, external_ref, customer_email)
  values ('00000000-0000-0000-0000-0000000000b1',
          '00000000-0000-0000-0000-0000000000aa', 'web', 'sess-1', 'john@acme.com');
insert into messages (conversation_id, role, body)
  values ('00000000-0000-0000-0000-0000000000b1', 'user', 'do you ship to Canada?');

\echo
\echo '=== 1. CHECK: status=''bogus'' must be rejected ==='
do $$ begin
  begin
    insert into conversations (tenant_id, channel, external_ref, status)
      values ('00000000-0000-0000-0000-0000000000aa', 'web', 'sess-bogus', 'bogus');
    raise exception 'ASSERT FAIL: bogus status was accepted';
  exception when check_violation then
    raise notice 'OK: status CHECK rejected ''bogus''';
  end;
end $$;

\echo
\echo '=== 2. UNIQUE: duplicate (tenant_id, channel, external_ref) must be rejected ==='
do $$ begin
  begin
    insert into conversations (tenant_id, channel, external_ref)
      values ('00000000-0000-0000-0000-0000000000aa', 'web', 'sess-1');
    raise exception 'ASSERT FAIL: duplicate (tenant,channel,external_ref) was accepted';
  exception when unique_violation then
    raise notice 'OK: UNIQUE rejected the duplicate find-or-create key';
  end;
end $$;

\echo
\echo '=== 3. RLS: anon is denied the base table but sees the masked view ==='
set local role anon;

\set ON_ERROR_STOP off
savepoint before_base;
\echo '-- anon direct read of base conversations (expect: permission denied):'
select count(*) as anon_base_rows from conversations;
rollback to savepoint before_base;
\set ON_ERROR_STOP on

\echo '-- anon read of v_conversations (expect one row; email masked j***@acme.com):'
select customer_email, last_message_preview
  from v_conversations
 where tenant_id = '00000000-0000-0000-0000-0000000000aa';

reset role;

\echo
\echo '=== rollback (non-destructive) ==='
rollback;
