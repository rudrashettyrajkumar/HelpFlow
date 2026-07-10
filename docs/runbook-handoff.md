# Runbook — handling a WF-H handoff alert

The human side of the escalation loop (spec E6 deliverable). WF-H only **notifies** —
nothing in n8n ever claims, replies, or resolves a conversation; that's the console's job
(E9). This is what you (the on-call human) actually do when a ping lands.

## 1. Alert lands (Slack + Gmail, in business hours)

You get a Slack message in `$env.SLACK_CHANNEL` and an email at `$env.ONCALL_EMAIL`,
within seconds of the customer being escalated. Both contain:

- Tenant name, escalation reason (`user_requested` / `low_relevance` / `sensitive_intent`
  / `repeated_low_conf`), and channel (`web` / `whatsapp`)
- A 3-line preview of the most recent messages
- A **console deep link**: `$env.CONSOLE_BASE_URL/app/inbox/{conversation_id}`

Outside business hours (`$env.BUSINESS_HOURS` / `$env.BUSINESS_TZ`) you get a
low-priority Slack note only — no email, no on-call paged. The conversation stays
`needs_human`; nothing auto-resolves or auto-abandons it here (that's WF-O's SLA sweep,
E10). If it's off-hours and looks urgent, open it anyway — the link still works.

**Known gap right now:** the console (E9) hasn't been built yet, so the deep link
currently 404s. Until E9 ships, use the fallback below.

## 2. Open the conversation

**Once E9 ships:** click the deep link → the inbox opens straight to that conversation,
`needs_human` pinned at the top.

**Fallback until then** — query Supabase directly with the `conversation_id` from the
alert:
```sql
select role, body, confidence, created_at
  from messages
 where conversation_id = '<id-from-the-alert>'
 order by created_at;

select reason, status, created_at from escalations where conversation_id = '<id>';
```

## 3. Claim

E9's **Claim** button does a guarded transition `needs_human → human_assigned`
(`escalations.status` stays `notified` — WF-H already moved it there; the console owns
`assigned`/`resolved`). Until E9 exists, claiming is a manual heads-up in the team
channel ("I've got this one") — there's no enforced single-claim guarantee without the
console's guarded UPDATE, so don't have two people work the same conversation.

While a conversation is `human_assigned`, the AI stops answering (invariant #5) — the
customer is talking to you now, not the model.

## 4. Reply

E9's **Reply** box lands your message live in the customer's widget (or WhatsApp, E11)
via the same real-time channel the AI streams through. Until E9 exists, there's no
supported way to reply as the AI mid-conversation — this is the sharpest edge of
building E6 before E9; say so if you're demoing this gap live.

## 5. Resolve, or hand back

- **Resolve**: `human_assigned → resolved`. Done.
- **Hand back to AI**: `human_assigned → ai_handling` — the AI answers again on the next
  customer message. Use this if you just needed to unblock one question, not staff the
  whole thread.

Both are guarded UPDATEs owned by the console (E9), never by n8n.

## Troubleshooting

- **No Slack, got email**: Slack webhook/app token is probably dead — check
  `events` for a `workflow_error` row with `detail->>'node' = 'Slack Notify'`
  (or `'Slack Low-Priority Note'`). WF-H still delivered via Gmail; nothing was lost.
- **No email, got Slack**: same idea, `detail->>'node' = 'Gmail Notify'`.
- **Nothing arrived at all**: check `escalations.status` for that conversation. If it's
  still `open`, the webhook never reached n8n (FastAPI logs a warning and moves on —
  it never blocks the customer's chat). If it's `notified`, n8n ran but both channels
  failed — check the n8n execution log for the run.
- **Got pinged twice for the same escalation**: shouldn't happen — the guarded UPDATE
  (`WHERE status='open'`) makes a retried `/webhook/handoff` a no-op after the first
  successful run. If you see it, check whether two *different* escalation rows exist for
  the same conversation (e.g. `repeated_low_conf` firing again before the first was
  resolved) — that's two genuine escalations, not a duplicate.
