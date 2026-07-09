-- HelpFlow RLS + masked views (ARCHITECTURE §5.3).
-- Idempotent. Ported from LeadFlow's dashboard contract: the console uses the
-- ANON key and reads ONLY these tenant-scoped, masked views; base tables have
-- RLS on with NO anon policy, so a direct base-table read returns nothing.
--
-- Why the views can read base tables that anon can't: a plain Postgres view runs
-- as its OWNER (postgres, which owns the tables), so base-table RLS does not
-- constrain it (security_invoker stays off — deliberate). anon reaches the data
-- ONLY through these masked, tenant-filterable views. FROZEN across E2–E7.

begin;

-- ---------------------------------------------------------------- email mask
-- Keep the first char of the local part + ***@ + domain: john@acme.com → j***@acme.com
-- (ARCHITECTURE §5.3 / §5.4 — never expose a full customer email on the console).
create or replace function mask_email(addr text) returns text
language sql immutable as $$
  select case
    when addr is null or position('@' in addr) = 0 then null
    else left(split_part(addr, '@', 1), 1) || '***@' || split_part(addr, '@', 2)
  end
$$;

-- ---------------------------------------------------------------- RLS on base tables
-- Enable RLS everywhere; grant NO policy to anon (reads return zero rows). The
-- service-role DB connection (the brain) bypasses RLS as the table owner.
alter table tenants       enable row level security;
alter table sources       enable row level security;
alter table conversations enable row level security;
alter table messages      enable row level security;
alter table escalations   enable row level security;
alter table events        enable row level security;

-- Belt-and-braces: strip any direct base-table privileges from the anon role so
-- a direct select is a permission error, not just an empty RLS result.
revoke all on tenants, sources, conversations, messages, escalations, events from anon;

-- ---------------------------------------------------------------- v_conversations
-- Inbox list: masked email, a last-message PREVIEW only (no full transcript),
-- and the open escalation reason. Tenant-filterable via tenant_id.
create or replace view v_conversations as
select
  c.id,
  c.tenant_id,
  c.channel,
  c.status,
  c.assigned_agent,
  mask_email(c.customer_email)                       as customer_email,
  left(lm.body, 140)                                 as last_message_preview,
  e.reason                                           as escalation_reason,
  c.last_activity_at,
  c.created_at
from conversations c
left join lateral (
  select body from messages m
  where m.conversation_id = c.id
  order by m.created_at desc
  limit 1
) lm on true
left join lateral (
  select reason from escalations es
  where es.conversation_id = c.id and es.status <> 'resolved'
  order by es.created_at desc
  limit 1
) e on true;

-- ---------------------------------------------------------------- v_funnel
-- Per-tenant counts + deflection rate = ai_resolved / total.
-- ai_resolved  = resolved AND never escalated (the AI handled it end-to-end).
-- human_resolved = resolved AND escalated at some point.
create or replace view v_funnel as
select
  c.tenant_id,
  count(*)                                                              as total,
  count(*) filter (
    where c.status = 'resolved' and esc.conversation_id is null
  )                                                                     as ai_resolved,
  count(*) filter (where esc.conversation_id is not null)               as escalated,
  count(*) filter (
    where c.status = 'resolved' and esc.conversation_id is not null
  )                                                                     as human_resolved,
  round(
    count(*) filter (where c.status = 'resolved' and esc.conversation_id is null)::numeric
      / nullif(count(*), 0), 4
  )                                                                     as deflection_rate
from conversations c
left join (
  select distinct conversation_id from escalations
) esc on esc.conversation_id = c.id
group by c.tenant_id;

-- ---------------------------------------------------------------- v_gaps
-- Questions the docs didn't cover (low_relevance escalations). E1 ships the base
-- view; E6 adds clustering + frequency on top of it.
create or replace view v_gaps as
select
  c.tenant_id,
  es.conversation_id,
  es.created_at,
  (
    select m.body from messages m
    where m.conversation_id = c.id and m.role = 'user'
    order by m.created_at desc
    limit 1
  )                                                  as question
from escalations es
join conversations c on c.id = es.conversation_id
where es.reason = 'low_relevance';

-- ---------------------------------------------------------------- v_events
-- Recent activity feed per conversation for the inbox timeline.
create or replace view v_events as
select
  c.tenant_id,
  ev.conversation_id,
  ev.type,
  ev.detail,
  ev.created_at
from events ev
join conversations c on c.id = ev.conversation_id;

-- ---------------------------------------------------------------- grants
grant select on v_conversations, v_funnel, v_gaps, v_events to anon;

commit;
