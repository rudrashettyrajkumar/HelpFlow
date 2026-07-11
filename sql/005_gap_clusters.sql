-- Gap Report cache (ARCHITECTURE §5.5, spec E9 Req 4). Additive; 001-004 frozen.
--
-- `v_gaps` (002) already exposes raw `low_relevance` escalation questions —
-- useful, but not what the Gap Report renders: it needs THEMES (frequency +
-- example questions), which only an LLM clustering pass can produce, not a
-- SQL view. `backend/scripts/cluster_gaps.py` computes that pass OFFLINE and
-- writes the result here; a re-run replaces (not appends to) a tenant's rows
-- — this table is a cache of the latest clustering, not a history log.

begin;

create table if not exists gap_clusters (
  id                uuid primary key default gen_random_uuid(),
  tenant_id         uuid not null references tenants(id) on delete cascade,
  theme             text not null,
  frequency         int not null check (frequency > 0),
  example_questions text[] not null default '{}',
  computed_at       timestamptz not null default now()
);

create index if not exists idx_gap_clusters_tenant on gap_clusters(tenant_id);

alter table gap_clusters enable row level security;
revoke all on gap_clusters from anon;

create or replace view v_gap_clusters as
select tenant_id, theme, frequency, example_questions, computed_at
from gap_clusters;

grant select on v_gap_clusters to anon;

commit;
