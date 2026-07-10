---
name: helpflow-schema
description: HelpFlow data model — the conversation stage machine, table shapes, find-or-create keys, guarded transitions with one-owner-per-transition, RLS masked views, and the events taxonomy. Use when writing SQL, conversation-state logic, the escalation flow, or the console's view reads. The status enum and view shapes are frozen contracts across E1–E11.
---

# HelpFlow schema (the spine of the system)

Ported from LeadFlow's stage-machine discipline; the domain is support conversations, not
leads. Qdrant holds knowledge; Postgres holds state — see [[helpflow-rag]] for the vector side.

## Conversation stage machine — frozen enum, one owner per transition
```
ai_handling ──escalate──► needs_human ──claim──► human_assigned ──resolve──► resolved
     │                        │                        │
     │                        │                        └──hand back──► ai_handling
     └──AI resolved / idle────┴──────────────────────────────────────► resolved
                                (off-hours + no email + idle → abandoned)
```
- `conversations.status` CHECK with EXACTLY: `ai_handling, needs_human, human_assigned,
  resolved, abandoned`.
- **One owner per transition** (this is what makes it race-free without locks):

| Transition | Owner |
|---|---|
| `ai_handling → needs_human` / `ai_handling → resolved` | FastAPI answer engine (E3) |
| `needs_human → human_assigned` / `human_assigned → resolved` / `human_assigned → ai_handling` | Agent console (E9) |
| `needs_human → abandoned` | n8n WF-O SLA sweep (E10) |

No two actors write the same target status. WF-H (E6) NOTIFIES only — it writes NO status.

**v2 additions (E5, `sql/003_users_trials.sql` — ADDITIVE, 001/002 frozen):** `users`
(citext email, stdlib-PBKDF2 `password_hash`, `trials_used int`), `premium_leads`,
`tenants.owner_user_id` + `plan` ('demo'|'trial'|'premium'). The trial counter reuses THE
guarded-UPDATE pattern: `UPDATE users SET trials_used=trials_used+1 WHERE id=$1 AND
trials_used<2` — 0 rows = gate response, no tenant INSERT. `users`/`premium_leads`: RLS
on, service-role only (no anon views, ever).

## Guarded transition (THE pattern — use everywhere)
```sql
UPDATE conversations
   SET status = $2, updated_at = now(), <cols> = ...
 WHERE id = $1 AND status = $3    -- $3 = the expected current status
```
0 rows affected = someone already moved it (double-click, retried webhook, concurrent run) =
correct and safe, NOT an error. NEVER update status without the guard. Idempotency is a design
invariant, not an optimization. Same rule on `escalations.status`.

## Tables (public schema) — see sql/001_schema.sql
- `tenants`: one business. `widget_config jsonb` (theme, greeting, brand color, tone) drives
  the widget AND is injected into the answer prompt. `sensitive_intents text[]` retargets escalation.
- `sources`: one row per crawled page; `status` crawling→ready|error, `chunk_count`,
  `source_id` links to Qdrant payloads.
- `conversations`: **find-or-create key `UNIQUE (tenant_id, channel, external_ref)`** — the
  same web session or WhatsApp phone always maps to one conversation. `channel` ∈ web|whatsapp
  makes the model channel-agnostic (WhatsApp in E11 needs no schema change). `low_conf_streak`
  drives the 2-in-a-row escalation. `updated_at` via trigger.
- `messages`: `role` ∈ user|assistant|agent|system; `citations jsonb`; `confidence` ∈
  answered|low|escalated. The transcript source of truth for the inbox and `/chat/subscribe`.
- `escalations`: `reason` ∈ user_requested|low_relevance|sensitive_intent|repeated_low_conf;
  `status` ∈ open|notified|assigned|resolved (guarded).
- `events`: append-only audit; `type` ∈ answered, escalated, notified, agent_joined,
  agent_reply, resolved, handed_back, whatsapp_in, whatsapp_out, gap_logged,
  workflow_error, lead_notified (v2).
  Every meaningful transition writes one — the inbox timeline, the digest, and the gap report
  all read from here.

## RLS + masked views (console contract — frozen in E1)
- RLS ON for all base tables; anon has NO base-table policy (reads denied). The **service-role
  key lives only inside FastAPI + n8n** and bypasses RLS.
- Console reads ONLY these, tenant-scoped (a tenant can never read another's data):
  - `v_conversations` — status, channel, last-message preview, escalation reason,
    `last_activity_at`; **customer_email masked** `j***@x.com`; no raw doc text.
  - `v_funnel` — per-status counts + **deflection rate** = ai_resolved / total.
  - `v_gaps` — `low_relevance` escalation questions; clustered themes added in E9.
  - `v_events` — recent per-conversation activity for the inbox timeline.

## Real-time delivery
- `/chat/subscribe` fan-out uses Postgres `LISTEN/NOTIFY` (or a 3s poll fallback) — NOT Redis
  pub/sub. Keep the container featherweight; Redis is only rate limits + WhatsApp dedup (`hf:`).
