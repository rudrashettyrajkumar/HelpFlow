# SPEC E7 — Ship: ops workflow, drift-proofing, deploy, monitoring, sales artifacts

**Epic:** E7 · **Depends on:** E6 · **Architecture refs:** §5.4, §9, §11, §12

## Objective
Everything is built; this session makes it live, observable, drift-proof, and sellable. After
it, the whole system runs on production URLs, an SLA sweep + daily digest keep escalations
from rotting, the repo provably matches what's live, and there's a README + case study + Loom
script aimed at a client who fears hallucinating bots.

## Deliverables
```
workflows/wf-ops.json                 # WF-O — Ops: SLA sweep + daily digest
snippets/sla-sweep.js                 # find stale/idle escalations
scripts/check-sync.mjs                # diff workflow node text vs snippets/prompts (port LeadFlow)
backend/scripts/cleanup_orphans.py    # Qdrant orphan-chunk cleanup + keepalive
.github/workflows/keepalive.yml       # daily Qdrant keepalive + cleanup + Supabase ping
README.md                             # the sales-grade readme (replaces the E1 stub)
CASE-STUDY.md                         # the writeup
LOOM-SCRIPT.md                        # the 2-minute video script + exact recording steps
docs/runbook.md                       # ops: how to add a tenant, rotate keys, read the digest
```

## Requirements
1. **WF-O — Ops** (n8n, schedule daily + hourly sweep):
   - **SLA sweep** (hourly): escalations `status='notified'` older than `$env.SLA_MINUTES`
     with no assignment → re-alert Slack (once, guarded by an `events` marker). Conversations
     `needs_human` off-hours + idle > `$env.ABANDON_HOURS` with no customer_email → guarded
     UPDATE `needs_human → abandoned` (WF-O owns this transition, §5.2).
   - **Daily digest** (09:00 tenant tz): per tenant — deflection rate, conversations handled,
     open escalations, top 3 gap-report themes → one Slack/Gmail summary. Real counts from
     `v_funnel` + `v_gaps`.
2. **Drift-proofing**: `check-sync.mjs` (ported) diffs every n8n Code node against its
   `snippets/*.js` and every prompt marker against its file; exit non-zero on any mismatch.
   Run it, fix any drift it finds, and make it a required pre-commit check.
3. **Deploy** (numbered checklists for the operator where dashboard-only):
   - FastAPI Railway service (verify SSE streams through the proxy — a real streamed chat and
     a live `/chat/subscribe`).
   - n8n Railway service with all three workflows imported + `$env` set; webhooks reachable.
   - Widget → Cloudflare Pages; Console → Vercel; CORS locked to the widget/console origins;
     the widget key resolution works cross-origin.
   - Confirm the demo tenant is seeded and answering on the live widget (demo.html hosted).
4. **Monitoring**: UptimeRobot on `/health` and `/webhook/health` every 5 min; alert to the
   on-call email. Paste the green-check screenshot description.
5. **Secret sweep**: grep the whole repo for `sk-`, `eyJ`, `client_secret`, Slack/Meta tokens
   → empty. `.env.example` complete with a comment per var.
6. **README + CASE-STUDY + LOOM-SCRIPT** — audience: a non-technical client skimming an Upwork
   profile who is scared of a bot that lies to their customers or spams them. Lead with the
   **live widget demo link** and a GIF of an **escalation → human takeover**. The
   grounded-or-handoff behavior and the ethics/safety section (§5.4) are SELLING points —
   write them that way. Include real measured numbers only: time-to-first-token, crawl seconds
   for the demo site, deflection rate on the seeded data, LLM cost from the OpenRouter
   dashboard. The case study tells the reuse story explicitly: "the RAG engine is Project #1,
   the orchestration is Project #2, composed into a shippable product."

## Acceptance criteria
- The full loop runs on production URLs end-to-end (customer question → escalate → agent reply
  live → resolve), traced once and pasted.
- WF-O: force a stale escalation → SLA re-alert fires once (not repeatedly); the daily digest
  produces correct numbers; an off-hours idle escalation moves to `abandoned` via the guarded
  UPDATE (and only via WF-O).
- `check-sync.mjs` exits 0; a deliberately edited node then makes it exit non-zero (prove it works).
- UptimeRobot green on both endpoints; secret sweep empty.
- README has: live demo link, architecture diagram, escalation-→-takeover GIF, deflection +
  gap-report screenshots, ethics section, honest limitations, and the reuse story.

## Required verification
- Paste the production end-to-end trace, the digest output, the SLA-sweep event rows, the
  `check-sync.mjs` exit codes (both), and the empty secret-sweep grep.
- All three workflow JSONs exported + committed matching snippets byte-for-byte.
