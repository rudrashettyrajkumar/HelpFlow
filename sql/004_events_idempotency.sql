-- WF-P idempotency (spec E6 Req 9): a retried /webhook/premium-lead must not
-- double-ping Raj. events.type has no CHECK enum (free-text, see 001), so this
-- migration adds ONLY a partial unique index — the "unique marker" the spec's
-- guarded insert-if-absent (`ON CONFLICT ... DO NOTHING`) targets. Additive,
-- idempotent: safe to run repeatedly (apply-sql.sh runs it twice in CI).

begin;

create unique index if not exists events_lead_notified_lead_id_uniq
  on events (((detail ->> 'lead_id')))
  where type = 'lead_notified';

commit;
