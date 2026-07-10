# BUILD PROMPTS — one Claude Code session per epic (v2.0)

How to use: open a fresh Claude Code session in the HelpFlow repo, paste the prompt for
the current epic, review the result, run the verification, then `/spec-check` before
committing. Don't start the next epic in the same session — fresh context per epic keeps
quality high.

> Prompts point at the spec + architecture instead of repeating details. The docs are the
> source of truth; the prompt's job is scope + reuse pointers + guardrails + definition
> of done.
>
> Reality check: FastAPI/widget/portal are normal codebases Claude runs directly (pytest,
> uvicorn, npm). n8n is NOT — Claude writes `workflows/*.json` + `snippets/*.js`, you
> import in the n8n editor and paste results back; Claude gives the exact import curl.
> Railway/Supabase/Slack/Meta dashboard steps come to you as numbered checklists.
>
> **E1–E3 are done (merged, built to v1).** Their prompts are removed; building resumes
> at E4. If a session needs their history, it's in git + the banners on their specs.

---

## E4 — Model layer v2 (LiteLLM → LangChain/LangGraph + BYOK)

```
Read docs/ARCHITECTURE.md fully — especially §4 (all), §3.2, and §13 (the v1→v2 migration
map) — then implement docs/specs/E4-model-layer.md exactly.

This epic RETROFITS merged code. The prime directive: E1–E3's behavior is FROZEN — the
pipeline order, the SSE event shapes (one additive `notice` event allowed), the
deterministic escalation truth table, and the tenant-isolation choke point must survive
byte-identical. Existing tests may change import paths ONLY; a behavioral test edit means
you broke the contract.

Port, don't reinvent — DocChat v3 already did this exact conversion. Read
/mnt/d/PortfolioProjects/DocChat/backend/llm/ (catalog, runconfig, factory, gateway,
reranker), backend/graph/chat_graph.py, services/embed_signature.py, and
tests/llm/test_factory.py FIRST, then adapt (session→tenant, dc:→hf:, + the escalation
branch in the graph).

Three things I'll personally check:
1. The OpenRouter-only `reasoning: {"enabled": false}` binding with its test (DocChat's
   highest-impact live finding — without it free Nemotron models hang 70s+; Groq 400s if
   you bind it there).
2. BYOK keys: parsed ONLY in llm/runconfig.py, never logged/stored/echoed — show me the
   leak test. BYOK gets NO silent fallback; only demo mode has the Groq↔OpenRouter chain.
3. Demo budget: counters checked BEFORE provider calls; exhaustion → the designed
   `notice` event rendering prompts/demo_exhausted.md — never a raw 429/provider error.

requirements.txt: -litellm, +langchain-openai/-anthropic/-google-genai, +langgraph,
+flashrank, httpx>=0.28.1,<1. Install into the native-Linux venv
(/home/raj/.venvs/helpflow), NEVER pip install into /mnt/d. Done = spec acceptance
criteria + full suite green + the four live curl transcripts + empty `grep -r litellm`.
```

---

## E5 — Accounts, self-serve workspaces, trial gate & premium leads

```
Read docs/ARCHITECTURE.md §3.0/§5.2/§5.3/§5.5/§7.1 and implement
docs/specs/E5-accounts-trials.md exactly. E4 is merged.

Port DocChat v2's self-contained auth (backend/utils/security.py stdlib PBKDF2, HS256 JWT
via python-jose, middleware/jwt_auth.py, api/auth.py) — adapt user storage from Upstash
to Supabase Postgres via the existing asyncpg client. sql/003_users_trials.sql is
ADDITIVE-ONLY; 001/002 are frozen contracts.

The heart of this epic is the trial gate: workspace create = ONE atomic guarded UPDATE
(trials_used<2) — write the concurrency test first (two simultaneous creates at
trials_used=1 → exactly one tenant). The 403 gate payload carries RAJ_* contact links
from env (never hardcoded) + renders prompts/trial_limit.md. The gate blocks NEW
workspaces only — existing ones must keep chatting (someone may be mid-demo to their
boss).

Also: JWT ownership scoping on /admin/sources* and /conversations* (wrong owner → 404,
ADMIN_TOKEN keeps working for scripts), trial caps (MAX_TRIAL_PAGES=25 clamp,
TRIAL_MESSAGES_DAILY=40 in rate_limit), and POST /api/premium-contact → premium_leads row
+ best-effort WF-P webhook (row is source of truth; n8n down → still 202 + workflow_error
event).

Walk me through the real-Supabase apply-sql.sh --assert run as a checklist. Done = spec
acceptance + the full visitor-journey curl walkthrough (register → 2 workspaces → gate →
lead row) + tests green.
```

---

## E6 — n8n orchestration (WF-H handoff + WF-P premium lead)

```
Read docs/ARCHITECTURE.md §2/§3.2(escalate)/§5.4/§7.2 and implement
docs/specs/E6-orchestration.md exactly. E1–E5 merged; FastAPI already fires
POST /webhook/handoff on escalation and POST /webhook/premium-lead on gate submissions.

Port the n8n discipline from LeadFlow — read
/mnt/d/PortfolioProjects/LeadFlow/.claude/skills/n8n-builder/SKILL.md and its workflows/.
NO LLM calls in either workflow; pure orchestration.

THE boundary rules: WF-H only NOTIFIES — it must NOT write status='human_assigned' (the
console owns that) and NOT decide escalations (FastAPI owns that). WF-P must be
idempotent by lead_id (a retried webhook never double-pings me).

Get right: (1) header-token auth + respond-early on both webhooks; (2) the guarded
escalations UPDATE (WHERE status='open') making retries no-ops; (3) business-hours branch
from $env — off-hours doesn't ping a sleeping on-call; (4) Slack OR Gmail failing still
delivers via the other + writes workflow_error; (5) WF-P's lead message has one-tap
mailto: and wa.me quick-reply links — this workflow is literally how my demo hands me
freelance leads, make the message worth screenshotting for the case study.

Walk me through Slack webhook + Gmail credential setup as checklists, give me both import
curls, then we trace a live escalation AND a live premium lead together. Done = spec
acceptance + both notify transcripts + exports matching snippets byte-for-byte.
```

---

## E7 — Chat widget (the demo star)

```
Implement docs/specs/E7-widget.md exactly. Read docs/ARCHITECTURE.md §7.1/§8/§4.3 first,
and read backend/api/chat.py + backend/utils/sse.py to bind to the REAL /chat/stream,
/chat/subscribe AND the new `notice` event shapes — do NOT guess contracts. Port
streaming-client patterns and the design tokens from DocChat's frontend
(/mnt/d/PortfolioProjects/DocChat/frontend/src/) — fetch-stream SSE parser, reconnect,
citation chips, glassmorphism token system. Invoke the ui-ux-pro-max skill before
building screens.

Stack: Vite + React 18 + TS + Tailwind. embed.js injects an iframe; the widget key
resolves tenant_id SERVER-side. BYOK config is read from localStorage (shared contract
with E8's Model Studio via lib/llmConfig.ts) and attached as X-LLM-*/X-Embed-* headers.

Build in spec order (loader+shell → streaming+citations → notice states → handoff state →
live human replies → resilience → theming/polish). The v2 hero moments: the
demo-exhausted NoticeCard (honest copy, working "get a free key" buttons — a Loom beat,
make it gorgeous) and the "a human joined" live transition. Dark+light, mobile-first,
host-CSS isolated.

Done = the spec's acceptance walkthrough in incognito on demo.html, including
devtools-offline reconnect, live human takeover, AND the forced demo-exhausted card.
npm run build clean, TS strict.
```

---

## E8 — Portal (landing + wizard + Model Studio + gates) — the beautiful-display hero

```
Implement docs/specs/E8-portal.md exactly. Read docs/ARCHITECTURE.md §3.0/§4.1–4.4/§5.3/
§8 first. This is the storefront my clients will judge me by — INVOKE the ui-ux-pro-max
skill before every screen, keep the DocChat-family design language (light-first colorful
glassmorphism, Plus Jakarta Sans, gradient mesh, motion), and treat empty/error/limit
states as designed moments.

Port DocChat v3's Model Studio (frontend ModelStudio + llmConfig.ts) into Next.js 14 App
Router as a full studio page — provider cards MUST render from GET /api/models only
(zero hardcoded models in the frontend). Port DocChat v2's auth-page + AuthContext
patterns for register/login.

The four screens that matter, in build order: (1) landing with the LIVE widget over the
seeded demo tenant + honest three-tier explainer + built-by-Raj footer; (2) the
onboarding wizard — name+URL → live crawl SSE → skippable Model Studio step (Demo
preselected, remaining shared budget shown) → live widget preview + embed snippet; time
the cold-visitor-to-chatting run, it's a README number; (3) Model Studio with the live
key test (validate endpoint) and "your key never leaves this browser" copy; (4) the
premium gate — warm, personal, LinkedIn/WhatsApp/email + lead form; design it like the
conversion surface it is.

Done = spec acceptance walked in incognito (cold-visitor timing, real-key validate,
forced demo-exhausted, workspace #3 gate → my Slack ping), bundle token-grep clean,
Lighthouse ≥90 on landing, build/TS/ESLint clean, Vercel preview URL.
```

---

## E9 — Console (inbox + sources admin + analytics + gap report)

```
Implement docs/specs/E9-console.md exactly — it extends the E8 portal app. Read
docs/ARCHITECTURE.md §5.4/§5.5/§7.1/§8.1, read sql/002_views_rls.sql for the REAL view
shapes and backend/api/conversations.py for the claim/reply/resolve/handback contract —
don't guess columns. Port dashboard patterns (anon key, masked views, server-side
tokens) from LeadFlow's dashboard/. INVOKE the dataviz skill before the KPI tiles,
volume chart, and gap report.

Reads go ONLY through the anon RLS views scoped to JWT-owned workspaces; agent actions
through Next.js route handlers holding tokens server-side — grep .next after building to
prove nothing shipped.

Build in spec order (inbox list+detail+reply → claim/resolve/handback → sources admin
with crawl SSE → analytics + gap report). Two things matter most: (1) the live loop —
escalation appears in the inbox, Claim → Reply shows live in the widget, Resolve;
double-Claim is one assignment (guarded UPDATE); (2) the Gap Report — cluster REAL
low_relevance questions (backend/scripts/cluster_gaps.py through the demo gateway +
prompts/gap_cluster.md) into "docs to write next" themes; it's the analytics hero and
the Loom's money shot.

Done = acceptance walked in incognito (incl. double-claim + token-grep + Lighthouse) +
deployed Vercel URL.
```

---

## E10 — Ship

```
Implement docs/specs/E10-ship.md. Everything is built; this session makes it live,
observable, drift-proof, and sellable.

Order: WF-O ops (SLA sweep — force a stale escalation; daily digest — real numbers incl.
demo-budget usage, trial signups, premium leads) → check-sync.mjs (run; force a drift to
prove it fails; fix) → deploy (FastAPI via the git-archive-to-/tmp Railway recipe — NEVER
railway up from /mnt/d, it corrupts files; n8n workflows + $env; widget on Cloudflare
Pages; portal on Vercel; CORS locked; set ALL v2 env: DEMO_* models/budgets, JWT_SECRET,
RAJ_* links, trial caps) → UptimeRobot both health endpoints → secret sweep →
README → CASE-STUDY.md → LOOM-SCRIPT.md → runbook.md.

WF-O owns needs_human → abandoned (guarded, off-hours+idle only) — no other actor writes
it.

Sales artifacts sell BOTH stories to a non-technical Upwork client who fears a lying
bot: (1) grounded-or-handoff with the escalation→takeover GIF; (2) "try it yourself
right now" — the 2-minute wizard, Model Studio, your-key-never-leaves-your-browser, the
honest free-tier demo mode. Real measured numbers only. The case study tells the triple
reuse story: RAG engine = Project #1, orchestration = Project #2, BYOK layer = Project
#1 v3 — composed into a product that generates its own leads (WF-P). Give me exact GIF
steps and every dashboard action as a numbered checklist. Done = both production traces
+ acceptance criteria + all three sales artifacts + empty secret sweep.
```

---

## E11 — WhatsApp channel (OPTIONAL)

```
Only after E1–E10 are solid and a WhatsApp story would win a specific client. Read
docs/ARCHITECTURE.md §3.4 and implement docs/specs/E11-whatsapp-optional.md exactly.

n8n owns the channel (webhooks + provider quirks + retries); the brain is untouched —
WF-W normalizes WhatsApp into POST /chat and sends the reply back. The conversation model
already supports it (channel + external_ref from E1); no schema change. WhatsApp always
runs demo mode (§4.4) — make the demo-exhausted path read sensibly as an outbound text
("the team will follow up"), never a get-a-key pitch to someone else's customer.

Provider: Meta WhatsApp Cloud API test number (Twilio sandbox fallback — snippets
abstract the payload shape).

Get right: (1) idempotency — hf:wa:{message_id} dedup, replayed webhook doesn't
double-reply (test by replaying); (2) signature/verify-token check; (3) brain error →
polite fallback + workflow_error event, never a silent drop; (4) handoff outbound — a
console reply reaches the WhatsApp thread; no AI message while human_assigned.

Walk me through the Meta app + number + verify-token setup as a checklist; give the
import curl; we trace live inbound+outbound + a replay + an escalation together. Done =
spec acceptance + transcripts + export matching snippets (check-sync clean).
```
