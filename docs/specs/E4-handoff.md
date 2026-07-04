# SPEC E4 — Handoff orchestration (n8n WF-H)

**Epic:** E4 · **Depends on:** E3 · **Architecture refs:** §2, §3.2 (5b), §5.2, §7.2, §9

## Objective
When FastAPI escalates a conversation, a human gets pinged fast with the context and a link
to take over — respecting business hours. This is the n8n "nervous system" epic: it owns
notifications, business-hours routing, SLA, and the daily digest hooks — but NOT the
escalation decision (FastAPI's) and NOT the claim/reply (the console's). After it, an
escalated conversation reliably reaches a human via Slack + email, and off-hours escalations
capture the customer's email instead of pinging a sleeping agent.

## Port, don't reinvent
The n8n discipline (repo-as-source-of-truth, webhook header auth, guarded Postgres UPDATEs,
continueOnFail + events row on failure, deterministic export) is LeadFlow's — read
`/mnt/d/PortfolioProjects/LeadFlow/.claude/skills/n8n-builder/SKILL.md` and its
`workflows/`/`snippets/`. This epic has **no LLM calls** (the brain owns those).

## Deliverables
```
workflows/wf-handoff.json             # WF-H — Handoff
snippets/business-hours.js            # is-now-within BUSINESS_HOURS for the tenant tz
snippets/verify-token.js              # X-Handoff-Token check (shared with E8)
docs/runbook-handoff.md               # the human's flow: alert → open inbox → claim → reply
```

## Requirements
1. **Trigger**: `POST /webhook/handoff` with header `X-Handoff-Token == $env.HANDOFF_TOKEN`
   (else Respond 401). Body: `{conversation_id, tenant, reason, transcript_url, channel,
   customer_email?}`. Respond 200 early (the caller — FastAPI — must not block on n8n).
2. **Escalation row update** (guarded): `UPDATE escalations SET status='notified',
   notified_at=now() WHERE conversation_id=$1 AND status='open'`. 0 rows = already handled =
   stop silently (idempotent — FastAPI may retry the webhook).
3. **Business-hours branch** (`business-hours.js`, config via `$env.BUSINESS_HOURS` +
   `$env.BUSINESS_TZ`):
   - **In hours** → Slack message to `$env.SLACK_CHANNEL` + Gmail to `$env.ONCALL_EMAIL`,
     both containing: tenant, reason, channel, a 3-line transcript preview, and the deep link
     to the console conversation. Write `events type='notified'`.
   - **Off hours** → if `customer_email` present, Slack a low-priority note + write
     `events type='notified' detail:{offhours:true}`; if absent, the WIDGET already asked for
     it (E5) — WF-H just records `offhours` and leaves the conversation `needs_human` for the
     morning digest. **Never auto-resolve or auto-abandon here** (that's WF-O's SLA sweep).
4. **No stage transition to human_assigned here** — WF-H only notifies. The claim happens in
   the console (E6). WF-H must not write `human_assigned` (invariant: one owner per transition).
5. **Agent-reply relay is NOT in this workflow for web** (the console pushes web replies via
   FastAPI `/chat/subscribe`); WF-H is web + whatsapp alerting only. (WhatsApp *outbound*
   relay is E8's WF-W.)
6. **Failure handling**: Slack or Gmail node failure → `continueOnFail`, write
   `events type='workflow_error' detail:{node}`, still try the other channel. One dead
   notifier never loses the escalation (it stays `needs_human`; the digest catches it).
7. **Config via `$env` only**: `HANDOFF_TOKEN, SLACK_CHANNEL, ONCALL_EMAIL, BUSINESS_HOURS,
   BUSINESS_TZ, CONSOLE_BASE_URL`. No literal channel ids / emails / hours inside nodes.

## Acceptance criteria (trace live, paste transcripts)
- FastAPI escalation (from an E3 off-topic question) → within seconds a Slack message AND an
  email land with the correct tenant/reason/preview and a working console deep link.
- Re-firing the same `/webhook/handoff` (idempotency) → escalation stays `notified`, no
  duplicate stage change (guarded UPDATE affects 0 rows the second time).
- Simulate off-hours (`BUSINESS_HOURS` set to exclude now): no on-call ping storm; the
  off-hours path recorded; conversation still `needs_human`.
- Kill the Slack webhook URL → the email still sends and a `workflow_error` event is written.
- `X-Handoff-Token` missing/wrong → 401, nothing sent.

## Required verification
- Paste: the Slack message text, the alert email text, and
  `SELECT type, count(*) FROM events WHERE type IN ('notified','workflow_error') GROUP BY type`.
- `wf-handoff.json` exported + committed; every Code node opens `// source: snippets/<file>.js`
  and matches the snippet byte-for-byte; give the exact n8n import curl command.
