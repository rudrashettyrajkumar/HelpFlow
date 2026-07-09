# HelpFlow — Project Memory

Portfolio Project #3 (capstone): an AI customer-support agent trained on a business's own
website. Crawl site → Qdrant → grounded, cited answers on a chat widget + WhatsApp. Knows
when it doesn't know and **hands off to a human** instead of guessing; the human takes over
the live conversation from an agent inbox. Owner dashboard shows deflection rate + a
"gap report" of unanswered questions. Goal: live demo + Loom that wins "AI chatbot for my
website / WhatsApp support agent" gigs. Built in ~1.5 weeks.

**This project fuses #1 and #2.** It reuses DocChat's FastAPI RAG brain and LeadFlow's n8n
orchestration + Supabase stage machine. When a piece already exists there, PORT it — don't
reinvent it. That reuse is a portfolio talking point, not a shortcut.

## Source of truth (read before implementing anything)
- `docs/ARCHITECTURE.md` — final design. NEVER contradict it; if a task seems to require
  deviating, STOP and ask the developer first.
- `docs/specs/` — one spec per epic. Implement exactly one epic per session.
- `docs/BUILD-PROMPTS.md` — the session prompt for each epic.
- Reference code to PORT (patterns, not imports):
  - DocChat: `/mnt/d/PortfolioProjects/DocChat/backend/` (utils, ingestion, pipeline, agents)
  - LeadFlow: `/mnt/d/PortfolioProjects/LeadFlow/` (sql/, workflows/, snippets/, scripts/)
  - MyShiva: `/mnt/d/PortfolioProjects/MyShiva/backend/` (the original of both)

## Two backends, one clean boundary (read §2 of ARCHITECTURE)
- **FastAPI = the brain + system of record.** RAG, streaming answers, the escalation
  DECISION, and the conversations/messages tables. Anything real-time or transactional.
- **n8n = the nervous system.** Human-agent notifications, business-hours routing, SLA
  timers, the WhatsApp channel adapter, the daily digest. Anything "when X, notify/route".
- They talk over a thin, versioned webhook contract (ARCHITECTURE §7). Do not move brain
  logic into n8n or ops logic into FastAPI.

## How building works here (hybrid repo)
- FastAPI/widget/console are normal codebases: Claude edits and runs them (pytest, uvicorn,
  npm) directly.
- n8n is NOT a codebase: Claude edits `workflows/*.json`, `snippets/*.js` in the repo; the
  developer imports/runs in the n8n editor and pastes results back. Every Code node opens
  `// source: snippets/<file>.js`; `scripts/check-sync.mjs` (E7) proves no drift.
- Railway/Supabase/Slack/Meta/OAuth dashboard steps → numbered checklists for the developer.

## Hard constraints
- ₹0 incremental cost: Railway Hobby (existing), Qdrant free, Supabase free, Upstash free,
  Vercel/Cloudflare free, Slack/Gmail free, OpenRouter existing credit. Never add a paid
  service without flagging it.
- **No LangChain/LangGraph/agent frameworks; no n8n AI Agent nodes.** Plain Python asyncio +
  FastAPI + LiteLLM in the brain; single-purpose workflows in n8n. Deliberate, documented,
  a portfolio talking point ("I know when NOT to use an agent framework").
- Stateless, featherweight containers: no local ML models, no files on disk, no Railway
  volumes. Pages parsed in memory; vectors in Qdrant, state in Supabase, cache in Redis.

## Stack (locked)
FastAPI on Railway · n8n Docker on Railway · Qdrant Cloud (collection `helpflow_chunks`,
768-dim cosine) · Supabase Postgres (schemas `public` + `n8n`) · Upstash Redis (`hf:`
prefix) · LiteLLM Router (OpenRouter → Groq) · gemini-embedding-001 @ 768 · trafilatura +
Jina Reader · React 18 + Vite + Tailwind widget on Cloudflare Pages · Next.js 14 console on
Vercel · Slack + Gmail alerts · (optional) WhatsApp Cloud API.

## Non-negotiable invariants (the spine — see ARCHITECTURE §12)
1. **Grounded-or-handoff.** The AI never invents an answer. Low retrieval relevance,
   sensitive intent (refund/complaint/cancel/legal), or an explicit human request →
   escalate, do NOT guess. The escalation decision is deterministic and tested.
2. **Tenant isolation everywhere.** Every Qdrant search carries the `tenant_id` filter (one
   choke point in `retrieval_agent.py`); every console read goes through tenant-scoped RLS
   views. Tenant A can never see tenant B's chunks or conversations. Tested both sides.
3. **Input guardrail runs before any LLM call;** blocked messages never reach a model and
   aren't stored. A test asserts zero router calls on that path.
4. **Every conversation transition is a guarded UPDATE** (`WHERE id=$1 AND status='<expected>'`).
   One owner per transition (ARCHITECTURE §5.2). Double-claim/double-resolve = safe no-op.
5. **The AI never talks over a human.** Once a conversation is `human_assigned`, the
   pipeline produces no AI messages for it until an explicit hand-back. Tested end-to-end.
6. **WhatsApp idempotency (E8):** each inbound message id is processed exactly once
   (`hf:wa:{id}` dedup in Redis).
7. Every external call (LLM, embed, Qdrant, Supabase, Redis, HTTP) has timeout + fallback;
   the user always gets a valid response/SSE event, never a hang or raw traceback.
8. All model IDs, keys, limits, thresholds from env (`config.py` / `$env`) — never
   hardcoded. Prompt text lives in `backend/prompts/*.md`, never in Python strings.

## Code conventions
- Backend: Python 3.12, full type hints, async-first, `ruff` clean before commit. Tests in
  `backend/tests/` mirroring module paths; external services mocked via `conftest.py` —
  tests never hit real APIs (eval + smoke scripts are the deliberate live exceptions).
- n8n: workflows named `WF-H — Handoff` etc.; kebab-case exports; credential names are
  contracts (`supabase-pg`, `openrouter`(unused here—brain owns LLM), `slack`, `gmail-alerts`,
  `whatsapp`). snippets = pure JS, no npm deps, runnable standalone with `node`.
- SQL: guarded transitions only; stage CHECK + RLS views are frozen contracts from E1.
- Widget/console: TypeScript strict, ESLint clean, `npm run build` clean before done.
- Secrets: `.env` (gitignored) + `.env.example` (committed, blank). Zero secrets in repo.
- Commit format: `feat(E3): escalation decision + streaming answer pipeline`.

## Workflow
- One epic per session. After implementing: run the spec's Required tests/verification,
  then `/spec-check <spec path>` before declaring done.
- If a spec is ambiguous: smallest reasonable choice, note it in the commit body, flag it.
