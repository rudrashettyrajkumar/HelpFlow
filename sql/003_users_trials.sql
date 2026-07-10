-- HelpFlow accounts + trials (ARCHITECTURE §5.2/§5.3, spec E5). ADDITIVE ONLY —
-- 001_schema.sql and 002_views_rls.sql are frozen contracts, untouched here.
-- Idempotent: safe to run repeatedly (apply-sql.sh runs everything twice in CI).

begin;

create extension if not exists citext;  -- case-insensitive unique email

-- ---------------------------------------------------------------- users
create table if not exists users (
  id            uuid primary key default gen_random_uuid(),
  email         citext unique not null,
  password_hash text not null,             -- pbkdf2_sha256$<iters>$<salt>$<hash>, stdlib
  trials_used   int not null default 0,
  created_at    timestamptz not null default now()
);

-- ---------------------------------------------------------------- premium_leads
-- The contact-Raj form (§3.0/§7.1). user_id is NULL for a landing-page visitor
-- who submits before ever registering.
create table if not exists premium_leads (
  id         uuid primary key default gen_random_uuid(),
  user_id    uuid references users(id) on delete set null,
  name       text not null,
  email      text not null,
  company    text,
  message    text not null,
  source     text not null default 'landing' check (source in ('gate', 'landing')),
  created_at timestamptz not null default now()
);

create index if not exists idx_premium_leads_created on premium_leads(created_at);

-- ---------------------------------------------------------------- tenants (extend)
-- owner_user_id NULL = a pre-v2 seeded/demo tenant (no self-serve account owns
-- it); plan drives the trial-cap clamp (§5.3) and the rate-limit cap (§7.2).
alter table tenants add column if not exists owner_user_id uuid references users(id) on delete set null;
alter table tenants add column if not exists plan text not null default 'trial'
  check (plan in ('demo', 'trial', 'premium'));

create index if not exists idx_tenants_owner on tenants(owner_user_id);

-- Retro-classify tenants that existed before this migration and have no
-- owner (E1/E2's seeded demo tenant): they are NOT a customer's trial, so the
-- column default ('trial') would mislabel them. Any future NULL-owner insert
-- (seed_demo_tenant.py) now sets plan='demo' explicitly at insert time, so
-- this backfill only ever touches pre-E5 rows — harmless no-op on rerun.
update tenants set plan = 'demo' where owner_user_id is null and plan = 'trial';

-- ---------------------------------------------------------------- RLS
-- Same contract as 002: RLS on, NO anon policy — service-role (the brain)
-- bypasses RLS as table owner; the console never reads these tables directly
-- (no user-facing masked view needed — accounts/leads aren't dashboard data).
alter table users          enable row level security;
alter table premium_leads  enable row level security;

revoke all on users, premium_leads from anon;

commit;
