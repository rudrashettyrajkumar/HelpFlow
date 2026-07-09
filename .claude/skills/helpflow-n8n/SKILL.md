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
- WF-H (handoff): notify humans + business hours. WF-O (ops): SLA sweep + digest, owns
  `needs_human → abandoned`. WF-W (whatsapp, E8): channel adapter, calls FastAPI `/chat`.
- One owner per stage transition — respect the table in [[helpflow-schema]].

## The working loop (Claude can't click the n8n editor)
1. Claude edits `workflows/*.json` + `snippets/*.js` in the repo.
2. Developer imports: `curl -X POST $N8N_URL/api/v1/workflows -H "X-N8N-API-KEY: $KEY"
   -H "Content-Type: application/json" -d @workflows/<file>.json` (or PUT to update by id).
   Always print the exact command.
3. Developer runs it, pastes execution results/errors back.
4. After any editor tweak: `node scripts/export-workflows.mjs` → commit. The repo must win;
   unexported editor changes are considered lost. `scripts/check-sync.mjs` (E7) proves no drift.

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
- All tunables via `$env`: `HANDOFF_TOKEN, SLACK_CHANNEL, ONCALL_EMAIL, BUSINESS_HOURS,
  BUSINESS_TZ, CONSOLE_BASE_URL, SLA_MINUTES, ABANDON_HOURS, FASTAPI_URL` and (E8)
  `WA_VERIFY_TOKEN, WA_PHONE_NUMBER_ID, WA_ACCESS_TOKEN, WA_TENANT_MAP, AGENT_OUTBOUND_TOKEN`.
  A literal channel id / email / hour / url / token inside a node is a review reject.
- Credential names are contracts: `supabase-pg`, `slack`, `gmail-alerts`, `whatsapp`.
  Referenced by name in workflow JSON; ids stripped on export.

## snippets/*.js constraints
- n8n Code node runtime: no npm imports, no fs; pure functions over `$input.all()`, return
  `[{json: {...}}]`. Keep each runnable standalone with `node` for testing (guard the n8n
  globals: `if (typeof $input !== 'undefined')`). Business-hours, dedup, normalize, and
  signature-verify logic all live here as tested pure functions.
