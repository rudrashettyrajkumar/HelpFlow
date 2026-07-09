-- HelpFlow schema — public app tables (ARCHITECTURE §5.2).
-- Idempotent: safe to run repeatedly (apply-sql.sh runs it twice in CI).
--
-- FROZEN CONTRACTS (do not change across E2–E7):
--   * conversations.status CHECK enum
--   * UNIQUE (tenant_id, channel, external_ref)
-- The guarded stage machine (§5.2) and the RLS masked views (002) build on both.

begin;

create extension if not exists pgcrypto;  -- gen_random_uuid()

-- updated_at trigger function (shared by tables that track it).
create or replace function set_updated_at() returns trigger
language plpgsql as $$
begin
  new.updated_at := now();
  return new;
end;
$$;

-- ---------------------------------------------------------------- tenants
-- A "tenant" = one business using HelpFlow. The demo seeds 1–2 (E2).
create table if not exists tenants (
  id                uuid primary key default gen_random_uuid(),
  name              text not null,
  website_url       text,
  widget_config     jsonb not null default '{}'::jsonb,   -- theme, greeting, brand color
  sensitive_intents text[] not null default '{}',         -- per-tenant override of the env default
  created_at        timestamptz not null default now()
);

-- ---------------------------------------------------------------- sources
-- One row per crawled page (ARCHITECTURE §3.1 STEP 5).
create table if not exists sources (
  id          uuid primary key default gen_random_uuid(),
  tenant_id   uuid not null references tenants(id) on delete cascade,
  url         text not null,
  type        text not null default 'page' check (type in ('page','sitemap')),
  title       text,
  status      text not null default 'crawling' check (status in ('crawling','ready','error')),
  chunk_count int not null default 0,
  error       text,
  crawled_at  timestamptz
);

create index if not exists idx_sources_tenant on sources(tenant_id);

-- ---------------------------------------------------------------- conversations
-- The spine — the guarded stage machine (§5.2). status enum is FROZEN.
create table if not exists conversations (
  id              uuid primary key default gen_random_uuid(),
  tenant_id       uuid not null references tenants(id) on delete cascade,
  channel         text not null default 'web' check (channel in ('web','whatsapp')),
  external_ref    text not null,                    -- wa phone / widget session
  status          text not null default 'ai_handling'
                    check (status in ('ai_handling','needs_human','human_assigned','resolved','abandoned')),
  assigned_agent  text,
  customer_email  text,
  low_conf_streak int not null default 0,
  last_activity_at timestamptz not null default now(),
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now(),
  unique (tenant_id, channel, external_ref)         -- find-or-create key
);

create index if not exists idx_conversations_tenant_status on conversations(tenant_id, status);

drop trigger if exists trg_conversations_updated_at on conversations;
create trigger trg_conversations_updated_at
  before update on conversations
  for each row execute function set_updated_at();

-- ---------------------------------------------------------------- messages
create table if not exists messages (
  id              uuid primary key default gen_random_uuid(),
  conversation_id uuid not null references conversations(id) on delete cascade,
  role            text not null check (role in ('user','assistant','agent','system')),
  body            text not null default '',
  citations       jsonb not null default '[]'::jsonb,   -- [{n, source_url, page_title, snippet}]
  confidence      text check (confidence in ('answered','low','escalated')),
  created_at      timestamptz not null default now()
);

create index if not exists idx_messages_conversation on messages(conversation_id);

-- ---------------------------------------------------------------- escalations
create table if not exists escalations (
  id              uuid primary key default gen_random_uuid(),
  conversation_id uuid not null references conversations(id) on delete cascade,
  reason          text not null
                    check (reason in ('user_requested','low_relevance','sensitive_intent','repeated_low_conf')),
  status          text not null default 'open'
                    check (status in ('open','notified','assigned','resolved')),
  assigned_agent  text,
  notified_at     timestamptz,
  resolved_at     timestamptz,
  created_at      timestamptz not null default now()
);

create index if not exists idx_escalations_conversation on escalations(conversation_id);
create index if not exists idx_escalations_status on escalations(status);

-- ---------------------------------------------------------------- events
-- Append-only audit; the inbox timeline and the digest both read from here.
create table if not exists events (
  id              uuid primary key default gen_random_uuid(),
  conversation_id uuid references conversations(id) on delete cascade,
  type            text not null,   -- answered|escalated|notified|agent_joined|agent_reply|
                                   -- resolved|handed_back|whatsapp_in|whatsapp_out|gap_logged|workflow_error
  detail          jsonb not null default '{}'::jsonb,
  created_at      timestamptz not null default now()
);

create index if not exists idx_events_conversation on events(conversation_id);
create index if not exists idx_events_created on events(created_at);

commit;
