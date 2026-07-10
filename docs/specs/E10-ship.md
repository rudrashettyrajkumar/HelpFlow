# SPEC E10 — Ship: ops workflow, drift-proofing, deploy, monitoring, sales artifacts

**Epic:** E10 · **Depends on:** E9 · **Architecture refs:** §5.6, §9, §11, §12

## Objective
Everything is built; this session makes it live, observable, drift-proof, and sellable.
After it, the whole system runs on production URLs, an SLA sweep + daily digest keep
escalations from rotting, the repo provably matches what's live in n8n, and the README /
case study / Loom script sell BOTH stories: "a grounded agent that gets a human" AND
"try it yourself right now — free, with your own key or none."

## Deliverables
```
workflows/wf-ops.json                 # WF-O — Ops: SLA sweep + daily digest
snippets/sla-sweep.js                 # find stale/idle escalations
scripts/check-sync.mjs                # workflow-node text vs snippets/prompts (port LeadFlow)
backend/scripts/cleanup_orphans.py    # Qdrant orphan-chunk cleanup + keepalive
.github/workflows/keepalive.yml       # daily keepalive + cleanup + Supabase ping
README.md                             # sales-grade (replaces stub)
CASE-STUDY.md · LOOM-SCRIPT.md · docs/runbook.md
```

## Requirements
1. **WF-O — Ops** (n8n, hourly sweep + daily digest):
   - SLA sweep: escalations `status='notified'` older than `$env.SLA_MINUTES`, unassigned
     → ONE Slack re-alert (guarded by an events marker). `needs_human` off-hours + idle >
     `$env.ABANDON_HOURS`, no customer_email → guarded `needs_human→abandoned` (WF-O is
     the ONLY writer of that transition).
   - Daily digest (09:00 tenant tz): per tenant — deflection rate, volume, open
     escalations, top gap themes; **plus the v2 ops lines: today's demo-budget usage
     (`hf:demo:*`), trial signups, premium leads**. One Slack/Gmail summary, real counts.
2. **Drift-proofing**: `check-sync.mjs` diffs every n8n Code node against `snippets/*.js`
   and prompt markers against files; non-zero exit on mismatch. Run it; deliberately edit
   a node to prove it fails; fix.
3. **Deploy** (numbered operator checklists where dashboard-only):
   - FastAPI on Railway — **deploy via the `git archive HEAD | tar -x -C /tmp/...`
     recipe, NEVER `railway up` from `/mnt/d`** (drvfs null-byte corruption — DocChat
     incident). Verify SSE streams through the proxy (real streamed chat + live
     subscribe). Set the v2 env: DEMO_* models/budgets, JWT_SECRET, RAJ_* links, trial
     caps.
   - n8n on Railway with all workflows imported + `$env` set; webhooks reachable.
   - Widget → Cloudflare Pages; Portal → Vercel; CORS locked to those origins; widget
     key resolution cross-origin OK.
   - Seed/verify the demo tenant; demo.html + the landing's live widget answering.
4. **Monitoring**: UptimeRobot on `/health` + `/webhook/health` (5 min) → on-call email.
5. **Secret sweep**: grep repo for `sk-`, `gsk_`, `eyJ`, `client_secret`, Slack/Meta
   tokens → empty; `.env.example` complete with a comment per var.
6. **Sales artifacts** — audience: a non-technical Upwork client who fears a bot that
   lies to their customers. Lead with the live portal link + a GIF of escalation → human
   takeover. Sell grounded-or-handoff and the ethics section (§5.6). **v2 additions:**
   the "try it free in 2 minutes" funnel, Model Studio screenshot, the BYOK trust story
   ("your key never leaves your browser"), the honest demo-mode/free-tier explainer, and
   the reuse story ("RAG engine = Project #1, orchestration = Project #2, BYOK layer =
   Project #1 v3 — composed into a product"). Real measured numbers only: TTFT, crawl
   seconds, deflection %, cold-visitor-to-chat time (E8's timing), demo-mode daily cost
   (should be ₹0). LOOM-SCRIPT beats: landing widget → wizard crawl → cited answer →
   refund escalation → Slack ping → console takeover → live reply in widget → gap
   report → demo-exhausted card → Model Studio with a real key → premium gate.

## Acceptance criteria
- Full loop on production URLs traced once and pasted (question → escalate → Slack →
  claim → live reply → resolve) PLUS the v2 loop (register → wizard → BYOK chat → gate →
  premium lead ping).
- WF-O: forced stale escalation re-alerts ONCE; digest numbers correct (incl. demo
  budget + leads); idle off-hours escalation → `abandoned` via WF-O only.
- `check-sync.mjs` 0 → forced-drift non-zero → fixed 0.
- UptimeRobot green on both; secret sweep empty.
- README: live links, diagram, takeover GIF, Model Studio + gap-report screenshots,
  tiers table, ethics + BYOK-trust sections, honest limitations (incl. §4.4 external-
  embed truth), real numbers.

## Required verification
Paste: both production traces, digest output, SLA event rows, check-sync exit codes
(all three runs), empty secret grep. All workflow JSONs exported + matching snippets.
`/spec-check docs/specs/E10-ship.md`.
