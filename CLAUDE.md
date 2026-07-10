# HelpFlow — Project Memory

Portfolio Project #3 (capstone): a **self-serve, bring-your-own-key** AI customer-support
agent trained on a business's own website. Visitor signs up → pastes a site → crawl →
Qdrant → grounded, cited answers on a chat widget (+ optional WhatsApp). Knows when it
doesn't know and **hands off to a human** instead of guessing; the human takes over live
from an agent inbox. Owner dashboard shows deflection rate + a "gap report". Three tiers:
**demo mode** (Raj's free-tier keys, daily budget, honest when exhausted), **free BYOK**
(user's Groq/OpenRouter key, curated open-source models), **paid BYOK** (user's
OpenRouter/OpenAI/Gemini/Anthropic key). **2 trial workspaces per account**, then a
premium gate → contact Raj (LinkedIn/WhatsApp/email) captured as a lead via n8n.

**This project fuses #1 and #2 (+ #1's v3).** DocChat's RAG brain + BYOK/LangChain layer,
LeadFlow's n8n orchestration + Supabase stage machine. When a piece exists there, PORT it.

## Source of truth (read before implementing anything)
- `docs/ARCHITECTURE.md` — **v2.0** final design. NEVER contradict it; if a task seems to
  require deviating, STOP and ask the developer first. §13 = the v1→v2 migration map.
- `docs/specs/` — one spec per epic, one epic per session. **E1–E3 are merged as built to
  v1** (banners on their specs); building resumes at E4.
- `docs/BUILD-PROMPTS.md` — the session prompt for each epic.
- Reference code to PORT (patterns, not imports):
  - DocChat: `/mnt/d/PortfolioProjects/DocChat/backend/` — **`llm/` + `graph/` +
    `services/embed_signature.py` (the v3 BYOK layer — E4's source)**, auth
    (`utils/security.py`, `middleware/jwt_auth.py` — E5's source), frontend
    (ModelStudio, design system — E7/E8's source)
  - LeadFlow: `/mnt/d/PortfolioProjects/LeadFlow/` (sql/, workflows/, snippets/, scripts/)
  - MyShiva: `/mnt/d/PortfolioProjects/MyShiva/backend/` (the original of both)

## Two backends, one clean boundary (ARCHITECTURE §2)
- **FastAPI = brain + system of record**: RAG, streaming, the escalation DECISION, auth/
  trials/demo-budget, conversations/messages tables.
- **n8n = nervous system**: handoff alerts (WF-H), **premium-lead notify (WF-P)**,
  business hours, SLA sweep + digest (WF-O), WhatsApp adapter (WF-W). Anything
  "when X, notify/route".
- Thin versioned webhook contract (§7.2). Don't move brain logic into n8n or vice versa.

## How building works here (hybrid repo)
- FastAPI/widget/portal are normal codebases: Claude edits and runs them directly.
- n8n is NOT: Claude edits `workflows/*.json` + `snippets/*.js`; the developer imports in
  the n8n editor and pastes results back. Code nodes open `// source: snippets/<file>.js`;
  `scripts/check-sync.mjs` (E10) proves no drift.
- Railway/Supabase/Slack/Meta dashboard steps → numbered checklists for the developer.

## Hard constraints
- ₹0 incremental cost: existing Railway Hobby, Qdrant free, Supabase free, Upstash free,
  Vercel/Cloudflare free, Slack/Gmail free. BYOK bills the USER's key, never Raj's.
- **LangChain + LangGraph ARE the LLM layer (v2.0, 2026-07-10, Raj-requested — REVERSES
  v1's "no frameworks" lock, same reversal DocChat v3 made).** LiteLLM is gone. Provider
  construction ONLY in `backend/llm/factory.py`; agents call `backend/llm/gateway.py`,
  never a provider SDK; the graph lives in `backend/graph/support_graph.py`. n8n still
  never makes LLM calls (no AI Agent nodes).
- **Demo mode serves ONLY free-tier open-source models** (Raj hard rule, carried from
  DocChat): chat `groq/llama-3.3-70b-versatile` ↔ failover OpenRouter Nemotron `:free`;
  embeddings `openrouter/nvidia/llama-nemotron-embed-vl-1b-v2:free`. Budget-capped per
  day (`hf:demo:*`); exhaustion → the honest designed explainer + get-a-free-key links,
  never a raw error.
- **BYOK keys are never stored server-side.** Browser localStorage → per-request
  `X-LLM-*`/`X-Embed-*` headers, parsed ONLY in `backend/llm/runconfig.py`. Never
  logged, never in Redis/Postgres, never echoed. BYOK gets NO silent fallback (demo mode
  is the only failover chain).
- **OpenRouter chat models bind `reasoning: {"enabled": false}`; no other provider does**
  (Groq 400s on it; without it free reasoning models hang 70s+). Tested.
- Stateless, featherweight containers: no torch, no files on disk, no volumes. One
  deliberate exception: FlashRank's ~4MB ONNX reranker (degrades to no-op).
- pip install into the native-Linux venv `/home/raj/.venvs/helpflow`, NEVER into
  `/mnt/d`. NEVER `railway up` from `/mnt/d` (drvfs corruption) — use the
  `git archive HEAD | tar -x -C /tmp/...` deploy recipe.

## Stack (locked, v2)
FastAPI on Railway · n8n on Railway · Qdrant Cloud (`helpflow_chunks`, 768-dim cosine —
ALL embed providers pinned to 768, per-tenant pin `hf:embedsig:{tenant}`) · Supabase
Postgres (`public` + `n8n` schemas; users/premium_leads in 003) · Upstash Redis (`hf:`
prefix) · **LangChain (ChatOpenAI for OpenRouter/Groq/OpenAI via base_url +
ChatAnthropic + ChatGoogleGenerativeAI) + LangGraph** · FlashRank · trafilatura + Jina ·
self-contained email/password auth (stdlib PBKDF2 + HS256 JWT) · widget: React 18 + Vite
+ Tailwind on Cloudflare Pages · portal (landing/wizard/Model Studio/console): Next.js 14
on Vercel · Slack + Gmail alerts · (optional) WhatsApp Cloud API. Design language:
light-first colorful glassmorphism, Plus Jakarta Sans (DocChat family).

## Non-negotiable invariants (ARCHITECTURE §12)
1. **Grounded-or-handoff.** Low relevance / sensitive intent / explicit request →
   escalate, never guess. The escalation decision is deterministic (NO LLM) and tested.
2. **Tenant isolation everywhere.** Qdrant `tenant_id` filter at one choke point; RLS
   masked views; v2 adds ownership scoping (users touch only owned workspaces, wrong
   owner → 404). Tested both sides.
3. **Input guardrail before any LLM call;** blocked messages never reach a model or
   storage. Zero-gateway-call test.
4. **Every stage transition is a guarded UPDATE** — including the trial counter
   (`trials_used<2` atomic). One owner per transition. Double-anything = safe no-op.
5. **The AI never talks over a human** (human_assigned → no AI output until hand-back).
6. **WhatsApp idempotency** (`hf:wa:{id}`, E11).
7. Every external call has timeout + fallback; degrade, never break — but in BYOK, never
   silently substitute a different model.
8. All ids/keys/limits/thresholds from env — never hardcoded — EXCEPT the deliberate
   BYOK catalog (`backend/llm/catalog.py`) and per-request BYOK headers. Raj's contact
   links are env (`RAJ_LINKEDIN_URL`/`RAJ_WHATSAPP_URL`/`RAJ_EMAIL`). Prompt text +
   product copy (demo_exhausted, trial_limit) live in `backend/prompts/*.md`.
9. **Trial gate server-enforced**: 2 workspaces/account; gate blocks NEW workspaces only;
   premium path (form → premium_leads → WF-P → Raj pinged) traced before ship.
10. **The SSE contract from E3 is FROZEN** (token/seq, sources, handoff, human_turn,
    done); v2 added only the additive `notice` event (demo_exhausted / embed_mismatch /
    key_invalid).

## Code conventions
- Backend: Python 3.12, full type hints, async-first, `ruff` clean. Tests mirror module
  paths; external services mocked in `conftest.py` (eval/smoke scripts are the live
  exceptions).
- n8n: workflows `WF-H — Handoff`, `WF-P — Premium lead`, etc.; kebab-case exports;
  credential names are contracts (`supabase-pg`, `slack`, `gmail-alerts`, `whatsapp`).
  Snippets = pure JS, runnable with `node`.
- SQL: additive migrations only; guarded transitions; the stage CHECK + RLS views are
  frozen contracts from E1.
- Widget/portal: TypeScript strict, ESLint clean, `npm run build` clean; invoke
  ui-ux-pro-max/dataviz skills before building screens/charts.
- Secrets: `.env` gitignored; `.env.example` committed blank; zero secrets in repo.
- Commit format: `feat(E4): LangChain factory + LangGraph graph + BYOK catalog`.

## Workflow
- One epic per session. After implementing: run the spec's Required verification, then
  `/spec-check <spec path>` before declaring done.
- If a spec is ambiguous: smallest reasonable choice, note it in the commit body, flag it.
