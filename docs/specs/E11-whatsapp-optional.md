# SPEC E11 — WhatsApp channel (OPTIONAL bonus)

**Epic:** E11 · **Depends on:** E4, E6 · **Architecture refs:** §3.4, §5.4, §7.2 · **Status:** optional

## Objective
A second channel: customers text the business's WhatsApp number and get the SAME grounded
agent with the SAME human handoff — proving HelpFlow is channel-agnostic. Bonus epic; the
core product (E1–E10) ships without it. Uses **Meta WhatsApp Cloud API** (free test
number); Twilio sandbox is the drop-in fallback. **WhatsApp conversations always run demo
mode** (an end customer has no BYOK headers — §4.4), so the demo-budget notice copy must
read sensibly as an outbound WhatsApp text too.

## Why n8n owns this (not FastAPI)
Inbound webhooks + outbound sends + provider quirks + retries = n8n's job. The brain is
untouched: WF-W normalizes WhatsApp into a `POST /chat` (non-streaming) call and sends the
reply back. The conversation model already supports it via `channel` +
`(tenant_id, channel, external_ref)` from E1 — no schema change.

## Port, don't reinvent
n8n discipline from LeadFlow (webhook auth, dedup, continueOnFail, guarded transitions,
export/check-sync). `/chat` + the conversation store are E3's; `verify-token.js` is E6's.

## Deliverables
```
workflows/wf-whatsapp.json            # WF-W — WhatsApp adapter (inbound + outbound)
snippets/normalize-wa.js              # payload → {tenant_id, phone, text, message_id}
snippets/dedup.js                     # hf:wa:{message_id} once-only guard (Redis via HTTP)
snippets/verify-signature.js          # Meta/Twilio webhook signature verification
docs/runbook-whatsapp.md              # Meta app setup, number, verify token, phone mapping
```

## Requirements
1. **Inbound webhook** `POST /webhook/whatsapp`: verify provider signature
   (`verify-signature.js`) + the Meta hub challenge on GET; reject unverified.
2. **Idempotency** (invariant #6): `dedup.js` sets `hf:wa:{message_id}` (TTL 24h);
   duplicate deliveries dropped — processed exactly once. Test by replaying.
3. **Normalize + map**: `normalize-wa.js` extracts `{phone, text, message_id}`; business
   phone-number-id → `tenant_id` via `$env.WA_TENANT_MAP` or Supabase lookup;
   find-or-create conversation by `(tenant_id, 'whatsapp', phone)`.
4. **Brain call**: `POST {FASTAPI_URL}/chat` → `{reply, sources, escalated, reason,
   status}`. Timeout + fallback discipline; brain error → polite "we'll get back to you"
   + `events type='workflow_error'`. A `demo_exhausted` notice becomes a polite text
   (with the get-a-key line dropped — end customers aren't the key owners; say "the team
   will follow up" instead and write an event so the owner sees it in the console).
5. **Send reply**: post back to the number; append cited source URLs as plain text
   (`Sources: url1, url2`); `events type='whatsapp_out'`.
6. **Handoff**: if `escalated`, WF-H already ran (FastAPI fires it). Console reply →
   FastAPI fires `POST /webhook/agent-outbound` → WF-W delivers to the WhatsApp thread
   (`events type='agent_reply'`). No AI message while `human_assigned` (invariant #5,
   enforced in the brain).
7. **Config via `$env`**: `WA_VERIFY_TOKEN, WA_PHONE_NUMBER_ID, WA_ACCESS_TOKEN,
   WA_TENANT_MAP, FASTAPI_URL, AGENT_OUTBOUND_TOKEN`. No literals in nodes.

## Acceptance criteria (trace live on the test number)
- Text a question → grounded answer with source links; a replayed webhook does NOT
  double-reply.
- Text "I want a human" / a refund question → WF-H alert fires; a console reply reaches
  the WhatsApp thread.
- Brain timeout → polite fallback + `workflow_error` event (no silent drop).
- Unverified signature / wrong verify token → rejected.

## Required verification
Paste: inbound+outbound transcript, the replay-dedup proof, and `SELECT type, count(*)
FROM events WHERE type LIKE 'whatsapp%' OR type='agent_reply' GROUP BY type`.
`wf-whatsapp.json` exported + committed matching snippets (check-sync clean); import curl
given. `/spec-check docs/specs/E11-whatsapp-optional.md`.
