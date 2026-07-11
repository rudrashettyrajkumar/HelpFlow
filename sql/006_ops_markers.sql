-- WF-O guard markers (spec E10 Req 1): the SLA re-alert must fire exactly ONCE
-- per escalation and the daily digest exactly once per day, across hourly
-- sweeps and n8n retries alike. Same pattern as 004: events.type is free-text
-- (001), so these are ONLY partial unique indexes — the targets WF-O's
-- `INSERT ... ON CONFLICT DO NOTHING RETURNING` guards hit. A conflicting
-- insert returns zero rows, so the Slack/Gmail nodes downstream never run
-- twice. Additive, idempotent: safe to run repeatedly (apply-sql.sh runs it
-- twice in CI).

begin;

create unique index if not exists events_sla_realert_escalation_uniq
  on events (((detail ->> 'escalation_id')))
  where type = 'sla_realert';

create unique index if not exists events_digest_sent_date_uniq
  on events (((detail ->> 'date')))
  where type = 'digest_sent';

commit;
