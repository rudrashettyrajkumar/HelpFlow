# SPEC E6 — n8n orchestration: WF-H handoff notify + WF-P premium-lead

**Epic:** E6 · **Depends on:** E3 (handoff webhook fires), E5 (premium-lead webhook fires) ·
**Architecture refs:** §2, §3.2 (escalate), §5.2, §7.2, §9

## Objective
The n8n "nervous system" epic, two workflows. **WF-H**: when FastAPI escalates a
conversation, a human gets pinged fast (Slack + Gmail) with context and a console deep
link, respecting business hours. **WF-P** (new in v2): when someone submits the premium
gate form, Raj gets pinged with the lead — the demo generating its maker's freelance
leads is itself the n8n showcase. n8n owns notifications/hours/SLA only: NOT the
escalation decision (FastAPI's), NOT claim/reply (the console's), NO LLM calls.

## Port, don't reinvent
LeadFlow's n8n discipline — read
`/mnt/d/PortfolioProjects/LeadFlow/.claude/skills/n8n-builder/SKILL.md` + its
`workflows/`/`snippets/`: repo-as-source-of-truth, webhook header auth, respond-early,
guarded Postgres UPDATEs, `continueOnFail` + events row on failure, deterministic export
(`scripts/export-workflows.mjs` from E1).

## Deliverables
```
workflows/wf-handoff.json             # WF-H — Handoff
workflows/wf-premium-lead.json        # WF-P — Premium lead → Raj
snippets/business-hours.js            # is-now-within BUSINESS_HOURS for the tenant tz
snippets/verify-token.js              # header-token check (shared: handoff + lead + wa)
snippets/format-lead.js               # lead row → Slack blocks + email body + quick-reply links
docs/runbook-handoff.md               # the human's flow: alert → open inbox → claim → reply
```

## Requirements — WF-H (unchanged from the v1 E4 spec)
1. **Trigger**: `POST /webhook/handoff`, header `X-Handoff-Token == $env.HANDOFF_TOKEN`
   (else 401). Body `{conversation_id, tenant, reason, transcript_url, channel,
   customer_email?}`. **Respond 200 early** — FastAPI must not block on n8n.
2. **Guarded escalation update**: `UPDATE escalations SET status='notified',
   notified_at=now() WHERE conversation_id=$1 AND status='open'`; 0 rows = already
   handled = stop silently (FastAPI may retry the webhook — idempotent).
3. **Business-hours branch** (`business-hours.js`, `$env.BUSINESS_HOURS` +
   `$env.BUSINESS_TZ`): in hours → Slack to `$env.SLACK_CHANNEL` + Gmail to
   `$env.ONCALL_EMAIL` with tenant, reason, channel, 3-line transcript preview, console
   deep link; write `events type='notified'`. Off hours → low-priority Slack note +
   `events detail:{offhours:true}`; never auto-resolve/abandon here (WF-O's job, E10).
4. **No stage transition to `human_assigned`** — WF-H only notifies (one owner per
   transition; the console claims).
5. **Failure handling**: Slack or Gmail node failure → `continueOnFail`, write
   `events type='workflow_error' detail:{node}`, still try the other channel.
6. **Config via `$env` only**: `HANDOFF_TOKEN, SLACK_CHANNEL, ONCALL_EMAIL,
   BUSINESS_HOURS, BUSINESS_TZ, CONSOLE_BASE_URL`.

## Requirements — WF-P (new)
7. **Trigger**: `POST /webhook/premium-lead`, header `X-Lead-Token == $env.LEAD_TOKEN`
   (else 401), respond 200 early. Body `{lead_id, name, email, company?, message,
   source}`.
8. **Notify Raj both channels** (`format-lead.js`): Slack DM/channel + Gmail — name,
   company, message, the user's email as a `mailto:` quick-reply AND a `wa.me` link
   (`$env.RAJ_WHATSAPP_URL`) so Raj can respond in one tap. Include how many workspaces
   the account used (passed by FastAPI) — that's buying-intent context.
9. **Idempotent by lead_id**: an events row `type='lead_notified' detail:{lead_id}` is
   written first via guarded insert-if-absent (Postgres `ON CONFLICT DO NOTHING` on a
   unique marker) — a retried webhook must not double-ping Raj.
10. **Failure**: same continueOnFail + `workflow_error` events discipline; the
    `premium_leads` row (E5) is the source of truth regardless.

## Acceptance criteria (trace live, paste transcripts)
- E3 off-topic question → escalation → Slack + email land in seconds with correct
  content and a working deep link; re-fired webhook = no duplicate (guarded UPDATE 0 rows).
- Off-hours simulation → no on-call ping; event recorded; conversation stays `needs_human`.
- Dead Slack webhook → email still sends + `workflow_error` event.
- Premium form submit (E5) → Raj's Slack + Gmail lead with working mailto/wa.me links;
  replayed webhook → exactly one notification.
- Wrong/missing header token on either webhook → 401, nothing sent.

## Required verification
Paste: both Slack messages, both emails, `SELECT type, count(*) FROM events WHERE type IN
('notified','lead_notified','workflow_error') GROUP BY type`. Both workflow JSONs
exported + committed; every Code node opens `// source: snippets/<file>.js` and matches
byte-for-byte; give the exact n8n import curl for each. `/spec-check` before done.
