# SPEC E8 — WhatsApp channel (OPTIONAL bonus)

**Epic:** E8 · **Depends on:** E3, E4 · **Architecture refs:** §3.4, §5.2, §7.2 · **Status:** optional

## Objective
A second channel: customers text the business's WhatsApp number and get the SAME grounded
agent, with the SAME handoff to a human — proving HelpFlow is channel-agnostic. This is a
bonus epic; the core product (E1–E7) ships without it. Do it when the web demo is solid and a
WhatsApp story would win a specific client. Uses **Meta WhatsApp Cloud API** (free test
number) — Twilio WhatsApp sandbox is the drop-in alternative if Meta onboarding is slow.

## Why n8n owns this (not FastAPI)
WhatsApp is inbound webhooks + outbound sends + provider quirks + retries — exactly n8n's
job. The brain stays untouched: n8n normalizes WhatsApp into a `/chat` (non-streaming) call
and sends the reply back. The conversation model already has `channel` and the find-or-create
key `(tenant_id, channel, external_ref)` from E1 — no schema change needed.

## Port, don't reinvent
n8n discipline from LeadFlow (webhook auth, dedup, continueOnFail, guarded transitions,
export/check-sync). The `/chat` non-streaming endpoint and conversation store are E3's.

## Deliverables
```
workflows/wf-whatsapp.json            # WF-W — WhatsApp adapter (inbound + outbound)
snippets/normalize-wa.js              # WhatsApp payload → {tenant_id, phone, text, message_id}
snippets/dedup.js                     # hf:wa:{message_id} once-only guard (Redis via HTTP)
snippets/verify-signature.js          # Meta/Twilio webhook signature verification
docs/runbook-whatsapp.md              # Meta app setup, number, verify token, phone mapping
```

## Requirements
1. **Inbound webhook** `POST /webhook/whatsapp`: verify the provider signature
   (`verify-signature.js`) and the Meta hub challenge on GET; reject unverified.
2. **Idempotency** (invariant #6): `dedup.js` sets `hf:wa:{message_id}` in Redis (TTL 24h); a
   duplicate delivery (providers retry) is dropped — processed exactly once. Test by replaying
   the same payload.
3. **Normalize + map**: `normalize-wa.js` extracts `{phone, text, message_id}` and maps the
   business phone-number-id → `tenant_id` (via `$env.WA_TENANT_MAP` or a Supabase lookup).
   Find-or-create the conversation by `(tenant_id, 'whatsapp', phone)`.
4. **Brain call**: HTTP `POST {FASTAPI_URL}/chat` `{tenant_id, conversation_id, message}` →
   `{reply, sources, escalated, reason, status}`. Same timeout+fallback discipline; a brain
   error → a polite "we'll get back to you" WhatsApp message + `events type='workflow_error'`.
5. **Send reply**: post `reply` back to the WhatsApp number; append cited source URLs as plain
   text (`Sources: url1, url2`). Write `events type='whatsapp_out'`.
6. **Handoff on WhatsApp**: if `escalated`, the E4 WF-H already ran (fired by FastAPI). When a
   human replies in the console, FastAPI fires `POST /webhook/agent-outbound` → WF-W delivers
   that reply to the WhatsApp thread (write `events type='agent_reply'`). No AI message goes
   out while `human_assigned` (invariant #5, enforced in the brain).
7. **Config via `$env`**: `WA_VERIFY_TOKEN, WA_PHONE_NUMBER_ID, WA_ACCESS_TOKEN, WA_TENANT_MAP,
   FASTAPI_URL, AGENT_OUTBOUND_TOKEN`. No literals in nodes.

## Acceptance criteria (trace live on the test number)
- Text a question → the grounded answer comes back on WhatsApp with source links; a second
  identical delivery (replayed webhook) does NOT double-reply (dedup proves out).
- Text "I want a human" / a refund question → escalation fires (Slack/email alert from WF-H);
  a console reply is delivered back to the WhatsApp thread.
- A brain timeout → the customer still gets a polite fallback, and a `workflow_error` event
  is recorded (no silent drop).
- Unverified signature / wrong verify token → rejected.

## Required verification
- Paste: an inbound+outbound WhatsApp transcript, the replay-dedup proof, and
  `SELECT type, count(*) FROM events WHERE type LIKE 'whatsapp%' OR type='agent_reply' GROUP BY type`.
- `wf-whatsapp.json` exported + committed; nodes match snippets (check-sync clean); import curl given.
