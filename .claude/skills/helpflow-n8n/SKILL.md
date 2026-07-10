---
name: helpflow-n8n
description: n8n workflow engineering for HelpFlow — the handoff, ops, and WhatsApp workflows. Repo-as-source-of-truth discipline, webhook header/signature auth, idempotency, guarded Postgres transitions, notify plumbing, and the FastAPI↔n8n boundary. Use when creating or editing anything in workflows/ or snippets/, or guiding the developer through the n8n editor.
---

# n8n builder (HelpFlow)

Ported from LeadFlow's n8n-builder. Key difference: **the brain (FastAPI) owns all LLM calls
and the RAG**; n8n here is pure orchestration — notify, route, wait, deliver. There are NO
OpenRouter/AI nodes in these workflows. See the boundary in ARCHITECTURE §2 and [[helpflow-schema]].

## The FastAPI ↔ n8n boundary (do not blur it)
- FastAPI decides escalations and owns `conversations`/`messages`. n8n never decides an
  escalation and never writes `human_assigned` (the console owns that).
- WF-H (handoff, E6): notify humans + business hours. WF-P (premium lead, E6): gate-form
  submission → Slack/Gmail to Raj with mailto/wa.me quick-replies, idempotent by lead_id.
  WF-O (ops, E10): SLA sweep + digest, owns `needs_human → abandoned`. WF-W (whatsapp,
  E11): channel adapter, calls FastAPI `/chat`.
- One owner per stage transition — respect the table in [[helpflow-schema]].

## The working loop (Claude can't click the n8n editor)
1. Claude edits `workflows/*.json` + `snippets/*.js` in the repo.
2. Developer imports: `curl -X POST $N8N_URL/api/v1/workflows -H "X-N8N-API-KEY: $KEY"
   -H "Content-Type: application/json" -d @workflows/<file>.json` (or PUT to update by id).
   Always print the exact command.
3. Developer runs it, pastes execution results/errors back.
4. After any editor tweak: `node scripts/export-workflows.mjs` → commit. The repo must win;
   unexported editor changes are considered lost. `scripts/check-sync.mjs` (E10) proves no drift.

## Source-of-truth markers (never omit)
- Every Code node text starts `// source: snippets/<file>.js` then the file contents verbatim.
- check-sync.mjs diffs these — a mismatch is a build failure, not a nitpick.

## Node patterns
- **Webhooks**: auth in-workflow — first node checks `$json.headers['x-handoff-token'] ===
  $env.HANDOFF_TOKEN` (WF-H) or verifies the provider signature (WF-W) → else Respond 401.
  Use **Respond Early** so the caller (FastAPI / Meta) gets 200 before slow work runs — FastAPI
  must never block on n8n.
- **Idempotency** (WF-W, invariant #6): `hf:wa:{message_id}` set-once guard in Redis; a
  replayed delivery is dropped. Also: guarded Postgres UPDATEs make retried webhooks no-ops.
- **Postgres**: one node per statement; stage transitions ALWAYS `UPDATE ... WHERE id=$1 AND
  status='<expected>'` with parameters, never string interpolation. Every meaningful step
  writes an `events` row.
- **Notify (Slack/Gmail)**: each node `continueOnFail: true`; on failure write
  `events type='workflow_error' detail:{node}` and still try the other channel. One dead
  notifier never loses an escalation — it stays `needs_human` for the digest to catch.
- **External HTTP** (FastAPI /chat, WhatsApp send): timeout 12–15s, `retryOnFail`, and a
  fallback branch that records the error and sends the customer a polite fallback — never a
  silent drop.

## Config & credentials
- All tunables via `$env`: `HANDOFF_TOKEN, LEAD_TOKEN, RAJ_WHATSAPP_URL, SLACK_CHANNEL,
  ONCALL_EMAIL, BUSINESS_HOURS, BUSINESS_TZ, CONSOLE_BASE_URL, SLA_MINUTES, ABANDON_HOURS,
  FASTAPI_URL` and (E11)
  `WA_VERIFY_TOKEN, WA_PHONE_NUMBER_ID, WA_ACCESS_TOKEN, WA_TENANT_MAP, AGENT_OUTBOUND_TOKEN`.
  A literal channel id / email / hour / url / token inside a node is a review reject.
- Credential names are contracts: `supabase-pg`, `slack`, `gmail-alerts`, `whatsapp`.
  Referenced by name in workflow JSON; ids stripped on export.

## snippets/*.js constraints
- n8n Code node runtime: no npm imports, no fs; pure functions over `$input.all()`, return
  `[{json: {...}}]`. Keep each runnable standalone with `node` for testing (guard the n8n
  globals: `if (typeof $input !== 'undefined')`). Business-hours, dedup, normalize, and
  signature-verify logic all live here as tested pure functions.

## Railway + Supabase deployment gotchas (learned the hard way, E6 — check this list
FIRST before re-diagnosing from scratch; same instance as [[leadflow-project]], so
these apply there too)
- **Postgres connection needs SSL, but the error lies to you.** n8n's `pg` driver
  defaults to no SSL; Supabase's Supavisor pooler requires it. A missing-SSL connection
  fails as `password authentication failed for user "postgres"` — NOT an SSL error.
  Fix: `DB_POSTGRESDB_SSL_ENABLED=true` + `DB_POSTGRESDB_SSL_REJECT_UNAUTHORIZED=false`
  on the n8n service env. Same story for a `Postgres` CREDENTIAL created in the editor
  (used by workflow nodes, separate from n8n's own `DB_POSTGRESDB_*` config) — toggle
  **"Ignore SSL Issues (Insecure)"** ON when the credential test says "Connection
  refused" or "Couldn't connect".
- **`password authentication failed for user "postgres"` is normal even with the RIGHT
  credentials.** Supabase's pooler always reports the underlying role (`postgres`), not
  the `postgres.<project-ref>` username you actually authenticated with. Don't chase a
  username bug here — verify the password with a direct `psql` test first
  (`PGPASSWORD=... psql -h host -U postgres.<ref> -p 5432 -d postgres -c "select 1"`)
  before assuming n8n's config is wrong.
- **`$env` access is blocked by default in newer n8n.** Every node reading `$env.X`
  (Set, Code, Slack, Gmail params, Postgres query params) fails with `access to env
  vars denied` unless the service has `N8N_BLOCK_ENV_ACCESS_IN_NODE=false` set. This is
  a hard requirement for the "everything from `$env`, zero literals" rule above — set
  it on the Railway service before importing anything.
- **Webhook node `path` must NOT include `webhook/`.** n8n auto-prepends `/webhook/` to
  whatever you put in the `path` parameter. `path: "webhook/handoff"` registers at
  `/webhook/webhook/handoff`, not `/webhook/handoff` — symptom is a 404 "requested
  webhook is not registered" that looks like an activation problem, not a path bug.
  Just use `path: "handoff"`.
- **Set node (`n8n-nodes-base.set`, typeVersion 3.x): `includeOtherFields` is a
  TOP-LEVEL parameter, not nested under `options`.** Putting it in `options:
  {includeOtherFields: true}` silently no-ops — the node drops every field from the
  input item except what you explicitly assigned, quietly killing anything downstream
  reading `$json.headers`/`$json.body` (e.g. a token-verification Code node right after
  it). No error is thrown; it just always evaluates false. Correct shape:
  `parameters: {assignments: {...}, includeOtherFields: true, options: {}}`.
- **"Active" toggle is gone in newer n8n — it's "Publish" now** (top-right of the
  editor, green "Published" badge once live). Same effect (registers the production
  webhook); don't go hunting for a toggle that no longer exists.
- **Auto-credential-attach**: if only one credential exists for a given type (e.g. one
  `Postgres` credential), n8n auto-attaches it to every new node of that type — confirm
  on 1-2 nodes, no need to wire each by hand.
- **`Postgres` node "Execute Query" parameter binding**: the positional-parameter field
  is `options.queryReplacement`, an expression evaluating to an array in `$1, $2, ...`
  order, e.g. `={{ [$json.body.conversation_id, $json.error] }}`.
- **Password with `@` (or other URI-special chars) breaks `postgresql://user:pass@host`
  parsing** — both in shell one-liners and when pasted into a Railway env var box that
  later feeds a URI. Prefer an alphanumeric-only DB password, or use `PGPASSWORD=...
  psql -h host -p port -U user -d db` (flags, no URI) for testing.
- **Fast diagnosis when a webhook returns 200 but nothing downstream happened**: query
  n8n's own API — `GET /api/v1/executions?limit=5` for the execution id + status, then
  `GET /api/v1/executions/{id}?includeData=true` for the exact failed node + stack
  (`resultData.runData.<node>[0].error`). Much faster than guessing from the webhook
  response or Slack/Gmail silence alone.
- **⚠️ Webhook path collision risk**: this n8n instance is shared with LeadFlow. E6
  registered `/webhook/handoff` and `/webhook/premium-lead`. Before adding a new
  webhook path here, grep LeadFlow's `docs/` and `workflows/` for the same path first.
