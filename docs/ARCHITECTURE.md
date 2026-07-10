# HELPFLOW — SOLUTION DESIGN & TECHNICAL ARCHITECTURE
**v2.0 · July 10, 2026 · Budget: ₹0 extra/month (rides on existing free tiers + Railway Hobby)**

> Portfolio Project #3 (the capstone): "An AI customer-support agent trained on your
> website that answers with citations, knows when it doesn't know, and hands off to a
> human instead of guessing — on web chat and WhatsApp." It fuses Project #1 (DocChat's
> RAG brain) and Project #2 (LeadFlow's n8n orchestration + Supabase stage machine).
>
> **v2.0 (this revision) makes HelpFlow a self-serve, bring-your-own-key product** any
> visitor can try: sign up → paste a website → chat with a grounded agent over it — on a
> **demo mode** (Raj's free-tier keys), a **free BYOK tier** (their own Groq / OpenRouter
> free keys, curated open-source models), or a **paid BYOK tier** (their own OpenRouter /
> OpenAI / Gemini / Anthropic key, full model picker). Two trial workspaces per account;
> after that a **premium gate** invites them to contact Raj (LinkedIn / WhatsApp / email)
> — and that contact request is itself captured as a lead by n8n. The LLM layer is
> **LangChain + LangGraph** (v2 reverses v1's "no frameworks" stance, same reversal
> DocChat v3 made — LiteLLM is gone).
>
> **Build status:** E1 (foundation), E2 (ingestion), E3 (answer+escalation) are merged to
> main **as built against v1.0** (LiteLLM router, seeded-tenant-only). Epic **E4 retrofits
> them** to this design; nothing in E1–E3 is thrown away — the pipeline shape, schema,
> SSE contract, and escalation logic all carry forward. See §13 for the exact v1→v2 delta.

---

## 1. PRODUCT SUMMARY

A business owner pastes their website (or sitemap) URL into HelpFlow. HelpFlow crawls it,
extracts the text, and builds a knowledge base. A chat bubble drops onto their site (one
`<script>` tag) and optionally onto WhatsApp. Customers get answers **only from the
business's real docs**, with citations back to the source page — and the moment the AI is
unsure, or the customer asks for a person, or the topic is sensitive (refund, complaint,
cancellation), it **hands off to a human** instead of making something up. The human gets
pinged in Slack/email, opens an agent inbox, and takes over the same conversation live.
An owner dashboard shows the deflection rate and a **"gap report"** of questions the docs
didn't cover.

**New in v2 — anyone can test it, and the funnel sells Raj:**

| Visible feature | Skill it proves |
|---|---|
| Sign up → paste your site → chat with it in ~2 minutes | Self-serve product packaging |
| **Demo mode** on shared free-tier keys, with honest "the free tier ran out today — get your own free key" messaging | Cost-aware production design |
| **BYOK Model Studio**: pick Groq/OpenRouter free open-source models, or paid OpenAI/Gemini/OpenRouter/Anthropic — keys never leave the browser | Multi-provider LLM engineering, security-conscious key handling |
| **LangChain + LangGraph** agent graph with a deterministic escalation node | Modern agent-framework fluency (the stack clients ask for by name) |
| 2 trial workspaces → premium gate → "contact Raj" (LinkedIn/WhatsApp) captured as a lead via n8n | The demo literally generates freelance leads |
| Answers only from the client's real website, with citations | Grounded RAG, no hallucination (the #1 client fear) |
| "I'm not sure — let me get a human" instead of a wrong answer | Escalation logic / responsible AI |
| Human takes over the live conversation, AI steps back | Human-in-the-loop orchestration (n8n) |
| Same agent on web chat AND WhatsApp (optional epic) | Multi-channel integration |
| Deflection rate + gap report | Measurable business value |
| Streaming, fast first token | SSE, async pipeline design |

**Relationship to Projects #1 and #2 (the reuse story — a portfolio talking point):**

| Layer | Comes from | What changes here |
|---|---|---|
| BYOK catalog · runconfig · LangChain factory · gateway · LangGraph graph | **DocChat v3** `backend/llm/` + `backend/graph/` | Ported; graph gains the escalation branch |
| Ingestion (crawl → chunk → embed → upsert) | **DocChat** ingestion (already ported in E2) | Embeds via BYOK factory; per-tenant embed-space pin |
| Chat pipeline (guardrail → rewrite → retrieve → cited stream) | **DocChat** pipeline (already ported in E3) | Becomes a LangGraph `StateGraph` |
| Self-contained email/password auth (PBKDF2 + HS256 JWT) | **DocChat v2** auth | Users live in Supabase Postgres (not Upstash) |
| Supabase stage machine + guarded transitions + RLS views | **LeadFlow** `sql/` (already ported in E1) | Unchanged; + `users`, `premium_leads`, tenant ownership |
| n8n repo-as-source-of-truth + webhook + notify discipline | **LeadFlow** `workflows/` | Handoff + **premium-lead capture** + ops + WhatsApp |
| Light-first colorful glassmorphism design system | **DocChat v2** frontend | One family look across the portfolio |

---

## 2. SYSTEM OVERVIEW

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  SURFACES                                                                     │
│  ┌──────────────────────┐ ┌───────────────────────────┐ ┌──────────────────┐ │
│  │ PORTAL (Next.js)     │ │ Chat widget (embed.js)    │ │ WhatsApp (Meta   │ │
│  │ landing · signup ·   │ │ on any site · streams ·   │ │ Cloud API)       │ │
│  │ onboarding wizard ·  │ │ citations · human-joined  │ │ (optional, E11)  │ │
│  │ MODEL STUDIO (BYOK) ·│ │ demo-exhausted state      │ └────────┬─────────┘ │
│  │ agent inbox ·        │ └────────────┬──────────────┘          │           │
│  │ analytics · premium  │              │ HTTPS + SSE             │ webhook   │
│  │ gate (contact Raj)   │              │ (+ X-LLM-*/X-Embed-*    │           │
│  └──────────┬───────────┘              │  BYOK headers)          │           │
└─────────────┼──────────────────────────┼─────────────────────────┼───────────┘
              ▼                          ▼                         ▼
┌───────────────────────────────────────────┐   ┌────────────────────────────────┐
│  BACKEND "BRAIN" — FastAPI on Railway     │   │  n8n "NERVOUS SYSTEM" — Railway│
│  LangGraph support graph:                 │   │  WF-H handoff notify + hours   │
│   guardrail → route/rewrite → retrieve →  │◄──┤  WF-P premium-lead → Raj       │
│   escalation decision → answer|escalate   │──►│  WF-O ops: SLA sweep + digest  │
│  LangChain factory (5 providers, BYOK)    │   │  WF-W whatsapp adapter (opt)   │
│  auth · trials · demo budget · SSE        │   └───┬────────┬──────────┬────────┘
└───┬──────────┬───────────┬────────────────┘       │        │          │
┌───▼────┐ ┌───▼────┐ ┌────▼─────────────┐    ┌─────▼──┐ ┌───▼───┐ ┌────▼─────┐
│ Qdrant │ │ Upstash│ │  Supabase        │    │ Slack  │ │ Gmail │ │ WhatsApp │
│ Cloud  │ │ Redis  │ │  Postgres        │    │(alerts │ │(alerts│ │  Cloud   │
│(vectors│ │(rate + │ │ users·tenants·   │    │ + leads│ │+leads)│ │  API     │
│ per    │ │ demo   │ │ convos·messages· │    │ to Raj)│ └───────┘ └──────────┘
│ tenant)│ │ budget │ │ escalations·     │    └────────┘
└────────┘ │+embed  │ │ premium_leads·   │      LLMs/embeds: BYOK via LangChain
           │ pin)   │ │ events · RLS)    │      (user's key, per-request headers)
           └────────┘ └──────────────────┘      Demo mode: Raj's Groq+OpenRouter
                                                free-tier keys (env), capped/day
```

Design principle carried from MyShiva/DocChat/LeadFlow: **stateless, featherweight
containers; state lives in managed free tiers.** One deliberate exception ported from
DocChat v3: FlashRank's ~4MB ONNX reranker (degrades to no-op if absent).

**Why two backends (FastAPI *and* n8n) — the deliberate boundary (unchanged from v1):**
- **FastAPI is the brain and system of record.** Low-latency streaming, RAG, the
  escalation *decision*, auth/trials/budgets, and the conversation tables.
- **n8n is the nervous system / ops layer.** "When X happens, notify/route/wait": human
  handoff alerts, business hours, SLA timers, the daily digest, the WhatsApp adapter —
  and new in v2, **premium-lead capture** (the contact-Raj form is an n8n-notified lead,
  which is itself a live demo of the n8n skills being sold).
- The boundary is a thin, versioned webhook contract (§7.2). Talking point: *"FastAPI for
  the real-time RAG core, n8n for the human-ops orchestration — the right tool per job."*

**No new paid accounts.** Same infra as v1 (§9). BYOK usage bills the **user's** key,
never Raj's; demo mode runs only on free-tier models so Raj's cost stays ≈ ₹0.

---

## 3. THE FLOWS

### 3.0 Self-serve onboarding (new in v2 — the portal wizard)

```
Visitor lands on the portal (marketing page: live demo widget + "try it on YOUR site")
  ↓  Sign up (email + password — self-contained auth, no external provider)
  ↓  CREATE WORKSPACE (= tenant) — trial 1 of 2
     name + website URL → E2 crawl kicks off with live SSE progress
     (trial caps: MAX_TRIAL_PAGES env, default 25 pages)
  ↓  PICK BRAINS (Model Studio, skippable — defaults to Demo mode)
     ○ Demo mode      — no key, Raj's free-tier keys, shared daily budget
     ○ Free BYOK      — your Groq / OpenRouter key, curated free open-source models
     ○ Paid BYOK      — your OpenRouter / OpenAI / Gemini / Anthropic key, full picker
  ↓  TRY IT — embedded widget preview chats over the crawled site; console shows
     the conversation; escalation demo button ("ask about a refund")
  ↓  EMBED — copy the one-line <script> snippet for their real site
     (externally embedded widgets run demo mode; BYOK headers exist only in the
      owner's own browser — see §4.4 key-handling truth)
After 2 workspaces → PREMIUM GATE: "HelpFlow for your business, without limits" →
LinkedIn / WhatsApp / email buttons + a short form → POST /api/premium-contact →
Supabase premium_leads row + n8n WF-P pings Raj on Slack/Gmail within seconds.
```

### 3.1 Ingestion — website crawl (`POST /admin/sources`, SSE progress) — as built in E2

Unchanged from v1 except **STEP 4 embeddings now go through the BYOK factory** (§4):
discover (sitemap/BFS, robots.txt, same-domain, page cap) → fetch + extract (trafilatura,
Jina fallback) → chunk (450 tokens / 80 overlap) → **embed with the workspace's configured
embedding model (pinned per tenant, §4.5)** → upsert to Qdrant `helpflow_chunks` with
`{tenant_id, source_id, source_url, page_title, chunk_index, text, created_at}` → record
sources rows + SSE progress. Re-crawl deletes by `source_id` filter first.

### 3.2 Conversation — web widget (`POST /chat/stream`, SSE) — the LangGraph support graph

Same pipeline LAW as v1 (order is frozen; E3 built it; E4 re-expresses it as a
`StateGraph` in `backend/graph/support_graph.py`):

```
load_conversation ──(status=human_assigned?)──► human_turn event · END   (invariant #5)
  ↓
guardrail (pure Python, pre-LLM, invariant #3) ──(blocked?)──► canned refusal · END
  ↓
route_rewrite (one small LLM call via gateway) → {route, queries[], intent}
  route=handoff → skip retrieval        parse fail/timeout → route=retrieve (degrade)
  ↓
retrieve (route=retrieve) — embed queries (PINNED model §4.5) → Qdrant filter
  must=[tenant_id] → RRF → FlashRank rerank (no-op if absent) → top 6 labeled chunks
  low_relevance = best score < RELEVANCE_THRESHOLD
  ↓
escalation_decision (DETERMINISTIC NODE — no LLM; conditional edge, invariant #1)
  escalate if: route=handoff · low_relevance · 2nd consecutive low-conf turn
  ↓                                    ↓
answer (streamed, cited, grounded)   escalate (canned warm handoff stream ·
  SSE token/seq · sources event        guarded UPDATE → needs_human ·
                                       escalations row · fire n8n /webhook/handoff ·
                                       SSE handoff event)
  ↓
persist (BackgroundTasks: messages + events + counters — never blocks)
```

**The SSE contract is FROZEN as built in E3** (`token`/seq, `sources`, `handoff`,
`human_turn`, `done`) — E4 must not change any existing event shape. E4 adds one
**additive** event for tier UX: `{event:"notice", code:"demo_exhausted"|"embed_mismatch"|
"key_invalid", message, links[]}` — the widget renders it as a friendly card, never a raw
error (§4.3).

### 3.3 Human reply delivery (widget ↔ agent, live) — as designed in v1, unchanged

`GET /chat/subscribe?conversation_id=…` SSE; console replies persist + fan out via
Postgres `LISTEN/NOTIFY` (3s-poll fallback). Status events drive the widget banner
("A human joined", "Conversation resolved").

### 3.4 Conversation — WhatsApp (optional, E11) — unchanged from v1

n8n WF-W normalizes Meta Cloud API webhooks → `POST /chat` (non-streaming) → replies back;
`hf:wa:{message_id}` dedup; escalations ride the same WF-H path. WhatsApp conversations
always run **demo mode** (an end customer on WhatsApp has no BYOK headers — same truth as
external embeds, §4.4).

---

## 4. MODEL / AI STRATEGY — BYOK, three tiers, LangChain + LangGraph (fully new in v2)

**The reversal, stated honestly (same as DocChat v3):** v1 said "no frameworks — LiteLLM
only" as a talking point. v2 deliberately reverses it: clients searching Upwork ask for
**LangChain/LangGraph by name**, and the BYOK factory pattern (one `init_chat_model`-style
builder per provider) is genuinely cleaner than hand-rolled failover for 5 providers.
LiteLLM is **removed entirely**. The old talking point becomes a better one: *"I've built
it both ways and can tell you when a framework earns its keep."*

### 4.1 The three tiers

| Tier | Whose key | Models | Limits |
|---|---|---|---|
| **Demo mode** (default, zero setup) | Raj's env keys — Groq + OpenRouter **free-tier open-source models ONLY** (hard rule) | env: `DEMO_REWRITER_MODEL`, `DEMO_ANSWERER_MODEL`, `DEMO_EMBED_MODEL` | Shared **global daily budget** (`hf:demo:{yyyymmdd}:{role}` counters; env caps). Exhausted → friendly explainer, never a raw 429 |
| **Free BYOK** | User's Groq and/or OpenRouter key (both genuinely free, no card) | Curated free open-source catalog (§4.2): Nemotron 3 Ultra/Super/Nano, GPT-OSS 120B, Llama 3.3 70B, Gemma 4, Qwen3-Next + NVIDIA free embedder | Provider's own free-tier limits (surfaced in the UI: Groq ≈30 req/min · 1K/day; OpenRouter `:free` ≈20 req/min · 50–200/day) |
| **Paid BYOK** | User's OpenRouter (with credit) / OpenAI / Gemini / Anthropic key | Full curated picker per provider + custom-model-id escape hatch on OpenRouter | User's own billing; no HelpFlow-side model cap |

Independent of tier, every account has the **2-trial-workspaces gate** (§5.3) — BYOK does
not bypass it (the scarcity is what routes serious users to Raj). Trial caps
(pages/messages) are env-tunable and generous enough for a real evaluation.

### 4.2 The catalog (`backend/llm/catalog.py` — ported from DocChat v3, refreshed July 2026)

One static, typed registry serves backend AND UI: `GET /api/models` returns it verbatim;
the Model Studio renders provider cards, accuracy meters (1–5 editorial tiers, not rotting
benchmark numbers), speed/cost/context chips, and "how to get a key in 4 steps" straight
from it. Adding a model here is the only change needed end-to-end.

Verified against live provider pages **July 10, 2026** (free lineups rot — the `notes`
field carries caveats):

| Provider | Kind | Chat models (headliners) | Embeddings |
|---|---|---|---|
| **Groq** | free (no card) | `llama-3.3-70b-versatile` ★rec (1K req/day) · `openai/gpt-oss-120b` (acc 4) · `openai/gpt-oss-20b` · `qwen/qwen3-32b` · `llama-3.1-8b-instant` (14.4K req/day) | — (none; UI says so) |
| **OpenRouter** | freemium | **`nvidia/nemotron-3-ultra-550b-a55b:free`** (acc 5, 1M ctx — open frontier reasoner, June 2026) · `nvidia/nemotron-3-super-120b-a12b:free` ★rec (acc 4, 1M ctx) · `nvidia/nemotron-3-nano-30b-a3b:free` (fast) · `openai/gpt-oss-120b:free` · `meta-llama/llama-3.3-70b-instruct:free` · `google/gemma-4-31b-it:free` · `qwen/qwen3-next-80b-a3b-instruct:free` (+ custom id escape hatch) | `nvidia/llama-nemotron-embed-vl-1b-v2:free` ★rec (768-dim Matryoshka, $0) · `qwen/qwen3-embedding-0.6b` · `openai/text-embedding-3-small` |
| **Gemini** | freemium | `gemini-3.5-flash` ★rec (free tier) · `gemini-2.5-pro` · `gemini-2.5-flash` · `gemini-3.1-flash-lite` | `gemini-embedding-001` (768) |
| **OpenAI** | paid | `gpt-5.5` · `gpt-5.4` · `gpt-5.4-mini` ★rec · `gpt-4.1` (1M ctx) · `gpt-4o-mini` | `text-embedding-3-small` ★rec · `text-embedding-3-large` |
| **Anthropic** | paid | `claude-fable-5` · `claude-opus-4-8` · `claude-sonnet-5` ★rec · `claude-haiku-4-5-20251001` | — |

`EMBED_PROVIDERS = (openrouter, openai, gemini)` — Groq and Anthropic ship no embedder,
and the UI explains it ("pair your Groq key with a free OpenRouter key for embeddings").

### 4.3 Demo mode — free open-source only, honest when exhausted (Raj hard rule)

- Demo models (env, current picks): rewriter+answerer `groq/llama-3.3-70b-versatile`
  (reliable citer, roomiest free tier), failover `openrouter/nvidia/nemotron-3-super-120b-a12b:free`;
  embeddings `openrouter/nvidia/llama-nemotron-embed-vl-1b-v2:free` (Groq has no embedder —
  OpenRouter's scarcer daily quota is reserved for embeds). **Never a paid or proprietary
  model on Raj's keys.**
- **Global daily budget** in Redis: `hf:demo:{yyyymmdd}:chat` and `:embed`, env caps
  (`DEMO_CHAT_DAILY` default 150, `DEMO_EMBED_DAILY` default 100), checked BEFORE the
  provider call. Over budget → the additive SSE `notice` event / HTTP 429 JSON:
  > *"HelpFlow's demo runs on shared free-tier keys (Groq + OpenRouter's free open-source
  > models) — and today's shared quota is used up. It resets at midnight UTC. Or skip the
  > wait: get your own free key in ~2 minutes — no credit card — at console.groq.com or
  > openrouter.ai, and paste it in Model Studio. Your key never leaves your browser."*
  with buttons: `Get a Groq key` · `Get an OpenRouter key` · `Open Model Studio`. The
  widget/portal render this as a designed card (E7/E8) — this exact honesty is a selling
  point, spec'd, not an afterthought.
- A provider-side failure that slips past the budget check (someone else drained the
  provider quota) maps to the same `demo_exhausted` notice — the user never sees a raw
  provider error.

### 4.4 BYOK key handling — the invariant (ported verbatim from DocChat v3)

- **Keys are never stored server-side. Ever.** They live in the owner's browser
  (`localStorage`) and arrive per-request via headers — `X-LLM-Provider`, `X-LLM-Model`,
  `X-LLM-Key`, `X-Embed-Provider`, `X-Embed-Model`, `X-Embed-Key` — parsed at exactly one
  place: `backend/llm/runconfig.py`. Never logged, never in Redis/Postgres, never in error
  messages.
- `POST /api/models/validate` does a ~1-token live probe so Model Studio can show
  "key works ✓" before the user commits.
- **The honest consequence** (documented in the README as a limitation + roadmap item):
  BYOK powers the owner's own browser sessions — the portal preview, their testing.
  Widgets embedded on third-party sites and WhatsApp serve end customers who have no
  headers → those run **demo mode**. A production deployment would store tenant keys in a
  server-side vault (Supabase Vault / KMS) — deliberately out of scope for a public demo
  where "your key never touches my server" is the stronger trust story.

### 4.5 One embedding space per tenant (ported from DocChat v3)

All embedding providers are pinned to **768 dims** (Matryoshka / native). First crawl pins
`hf:embedsig:{tenant_id}` = `{provider, model, dims}`; later crawls with a different embed
model → **409 with a designed explanation** (re-crawl from scratch to switch); queries
ALWAYS embed with the pinned model. Key resolution for a query embed: request header key →
env demo key (only if the pinned model is demo-servable) → `notice` event telling the
owner to open Model Studio. Deleting a workspace's last source releases the pin.

### 4.6 LangChain factory + gateway + LangGraph graph (ported from DocChat v3)

- `backend/llm/factory.py` — the ONLY place provider objects are built: `ChatOpenAI`
  (covers OpenRouter, Groq, OpenAI via `base_url`), `ChatAnthropic`,
  `ChatGoogleGenerativeAI`; embeddings likewise. **Critical carry-over (DocChat's
  highest-impact live finding):** for **OpenRouter only**, bind
  `extra_body={"reasoning": {"enabled": False}}` — free reasoning models (Nemotron,
  GPT-OSS, Qwen3) otherwise burn an unbounded hidden thinking budget (74s answers) without
  tripping timeouts. Groq 400s on that field — never bind it for Groq/OpenAI/Anthropic/
  Gemini. A test locks this in.
- `backend/llm/gateway.py` — the single chokepoint every agent calls (replaces
  `utils/llm_router.py`): global semaphore (`MAX_CONCURRENT_LLM_CALLS`), per-role timeouts
  (rewrite 8s, answer 30s), `StreamInterrupted` carrying partial tokens (never silently
  restart a stream from token 0). **Demo mode = env-configured failover chain**
  (Groq ↔ OpenRouter free). **BYOK = the user's exact choice, NO silent fallback by
  design** — a paying user's request must never be quietly served by a different model;
  errors surface as designed notices.
- `backend/graph/support_graph.py` — the §3.2 `StateGraph`; conditional edges for
  human-guard, guardrail, route, and the escalation decision. The escalation node stays
  **deterministic and LLM-free** (invariant #1). Sequential in-order fallback if langgraph
  is unimportable (same degrade stance DocChat took).
- `backend/llm/reranker.py` — FlashRank (~4MB ONNX), degrade-to-noop.
- Rewrite + answer share the user's ONE selected chat model in BYOK; demo mode may split
  roles via env.

**Capacity math (demo mode):** 150 chat + 100 embed calls/day fits inside Groq's 1K/day
and OpenRouter's free-tier quota with real headroom ≈ $0.00/month. BYOK costs Raj nothing.

---

## 5. DATA DESIGN

Stores split unchanged from v1: **Qdrant** = knowledge vectors (tenant-filtered);
**Supabase Postgres** = system of record; **Upstash Redis** (`hf:` prefix) = rate limits,
WhatsApp dedup, demo budget counters, embed-space pins. No business state in Redis.

### 5.1 Qdrant — one collection, tenant-filtered (as built in E1/E2, unchanged)

Collection `helpflow_chunks` (768 dims, cosine); payload `tenant_id` (indexed, MANDATORY
filter at the single retrieval choke point, tested), `source_id` (indexed), `source_url`,
`page_title`, `chunk_index`, `text`, `created_at`.

### 5.2 Supabase — tables (migrations in `sql/`; E1's tables unchanged, E5 ADDS three)

As built in E1 (frozen): `tenants` · `sources` · `conversations` (status CHECK enum +
`low_conf_streak`) · `messages` · `escalations` · `events`.

**New in v2 (E5, additive migration `003_users_trials.sql`):**

```
users          id uuid PK · email citext UNIQUE · password_hash text (PBKDF2-HMAC-SHA256,
               stdlib — no bcrypt dep) · trials_used int NOT NULL default 0
               · created_at                     (self-contained auth, DocChat v2 pattern)

premium_leads  id uuid PK · user_id FK NULL · name · email · company · message
               · source text ('gate'|'landing') · created_at
               (the contact-Raj form; WF-P notifies Raj per row)

tenants        + owner_user_id uuid FK NULL (NULL = seeded demo tenant)
               + plan text NOT NULL default 'trial' CHECK (plan IN ('demo','trial','premium'))
```

### 5.3 The trial gate (new in v2 — enforced server-side, invariant #9)

- Creating a workspace increments `users.trials_used` **atomically with the tenant INSERT**
  (`UPDATE users SET trials_used = trials_used + 1 WHERE id=$1 AND trials_used < 2`
  affecting 0 rows → 403 `trial_limit`, no tenant created — the guarded-UPDATE pattern
  yet again). Deleting a workspace does NOT refund a trial.
- Trial workspace caps (env): `MAX_TRIAL_PAGES=25` per crawl, `TRIAL_MESSAGES_DAILY=40`
  per workspace. Friendly designed messages, never bare 429/403.
- `trials_used >= 2` → every create attempt returns the **premium gate** payload:
  Raj's contact links (`RAJ_LINKEDIN_URL`, `RAJ_WHATSAPP_URL`, `RAJ_EMAIL` — env, never
  hardcoded) + the form → `premium_leads` + WF-P. Existing workspaces keep working
  (read/chat within caps) — the gate blocks NEW workspaces, it never bricks a demo
  someone is in the middle of showing their boss.
- `plan='premium'` (set manually by Raj after a deal) lifts the caps for that tenant.

### 5.4 Conversation stage machine — as built in E1/E3, FROZEN (v1 §5.2 verbatim)

`ai_handling → needs_human → human_assigned → resolved` (+ `abandoned`, + hand-back), one
owner per transition, every transition a guarded UPDATE. v2 changes nothing here.

### 5.5 Dashboard access — RLS + masked views (as built in E1, extended in E5)

Console reads only tenant-scoped masked views on the anon key (`v_conversations`,
`v_funnel`, `v_gaps`, `v_events`); service key exists only in FastAPI + n8n. E5 adds
tenant-ownership scoping (a user sees only workspaces where `owner_user_id = their id`)
enforced in the FastAPI layer (JWT → owned tenant ids) — RLS views stay the read path.

### 5.6 Support ethics & safety (README-visible, non-negotiable — v1 §5.4 + BYOK honesty)

Grounded-only answers; escalates instead of guessing; sensitive topics reach a human; the
AI never impersonates a human; PII masked on dashboards; **BYOK keys never stored,
demo-mode limits explained honestly; free tier = open-source models only.**

---

## 6. PROMPT SYSTEM (as built in E3; two additions)

Prompts are `.md` files in `backend/prompts/`, assembled at runtime, never Python strings.
Tenant bits (name, tone, greeting) injected from `tenants.widget_config`.

As built: `answerer_identity.md` · `citation_rules.md` · `router.md` ·
`handoff_message.md` · `offhours_message.md` · `no_sources.md` · `guardrails.md` ·
`gap_cluster.md`.

**New in v2:** `demo_exhausted.md` (the §4.3 explainer copy — it's product copy, so it
lives with the prompts and is editable without a deploy) · `trial_limit.md` (the premium
gate copy: warm, zero-pressure, "this demo has a 2-workspace limit so it stays free to
run — want it for real? talk to Raj:").

---

## 7. INTERFACES

### 7.1 FastAPI (Railway URL)

```
# Auth (new, E5 — DocChat v2 pattern: HS256 JWT, 7-day, Authorization: Bearer)
POST   /api/auth/register             {email, password} → {token, user}
POST   /api/auth/login                {email, password} → {token, user}
GET    /api/auth/me                   → {user, trials_used, workspaces[]}

# BYOK catalog (new, E4 — DocChat v3 pattern)
GET    /api/models                    → the §4.2 catalog verbatim (static, cached)
POST   /api/models/validate           {provider, model, key, kind:'chat'|'embed'}
                                      → {ok, latency_ms | error_code}   (1-token probe)

# Workspaces (new, E5; JWT-scoped — replaces the v1 shared ADMIN_TOKEN for humans;
#            the ADMIN_TOKEN path stays for scripts/seeding)
POST   /api/workspaces                {name, website_url} → 201 {tenant, widget_key}
                                      | 403 trial-gate payload (§5.3)
GET    /api/workspaces                → owned tenants + status + usage
DELETE /api/workspaces/{id}           → tenant + points + rows purged (no trial refund)
POST   /api/premium-contact           {name, email, company?, message} →
                                      premium_leads row + n8n WF-P webhook → 202

# Sources admin (as built in E2; now ALSO reachable JWT-scoped per owned workspace)
POST   /admin/sources                 {url|sitemap_url, max_pages} → SSE crawl progress
GET    /admin/sources · POST /admin/sources/{id}/refresh · DELETE /admin/sources/{id}

# Conversation (as built in E3; X-Widget-Key resolves tenant server-side;
#              optional X-LLM-*/X-Embed-* BYOK headers, parsed only in runconfig.py)
POST   /chat/stream                   → SSE: token/seq · sources · handoff · human_turn ·
                                        done  (+ additive: notice — §3.2)
POST   /chat                          non-streaming sibling (n8n/WhatsApp)
GET    /chat/subscribe                ?conversation_id → SSE: message | status

# Agent console (as built in E3/E1 contracts; JWT-scoped in v2)
GET    /conversations · GET /conversations/{id}/messages
POST   /conversations/{id}/reply|claim|resolve|handback     (guarded transitions)

GET    /health                        → {status, qdrant, supabase, redis, llm}
```

### 7.2 n8n webhooks (Railway URL; header-token auth in-workflow, LeadFlow discipline)

```
POST /webhook/handoff         FastAPI → n8n (E6): escalation notify — Slack + Gmail,
                              business-hours branch, guarded escalations UPDATE, events.
POST /webhook/premium-lead    FastAPI → n8n (E6, NEW WF-P): a premium_leads row was
                              created → Slack DM + Gmail to Raj with name/company/message
                              + a mailto/wa.me quick-reply link. Raj's demo generates
                              Raj's leads — say so in the case study.
POST /webhook/whatsapp        Meta/Twilio inbound (E11). Signature-verified, id-deduped.
POST /webhook/agent-outbound  FastAPI → n8n (E11): deliver a human reply to WhatsApp.
GET  /webhook/health          200 for UptimeRobot.
```

Rate limits (Redis): 30 messages/conversation/hour · `TRIAL_MESSAGES_DAILY=40`/workspace ·
200 messages/tenant/day (premium) · 4 crawls/tenant/day · demo budget §4.3. All exceeded
→ designed JSON the surfaces render warmly.

---

## 8. FRONTEND — the "beautiful display" mandate

**One design language across all surfaces** (this is a portfolio storefront — it must be
gorgeous): light-first colorful **glassmorphism** — the DocChat v2 family look. Plus
Jakarta Sans, CSS-var token system (light/dark, `data-theme` toggle), gradient-mesh hero,
`glass`/`glass-strong` cards, motion (Framer Motion ≥12) for streaming, cards, and state
transitions. The UI epics MUST invoke the `ui-ux-pro-max`/`dataviz` skills before building
screens/charts. Every state — empty, loading, error, demo-exhausted, trial-gate — is a
designed moment, not an apology.

### 8.1 Portal (Next.js 14 App Router on Vercel) — E8 + E9, the biggest surface

- **Landing** (public): hero with a LIVE embedded widget over a seeded demo tenant
  ("ask it anything about this fake company"), the three-tier explainer, architecture
  diagram, "built by Raj" footer with LinkedIn/WhatsApp/GitHub.
- **Auth**: register/login (JWT in localStorage, 401 → logout) — DocChat v2 pattern.
- **Onboarding wizard** (§3.0): name+URL → live crawl progress (SSE) → Model Studio step
  (skippable, defaults demo) → widget preview → embed snippet. The wizard IS the Loom.
- **Model Studio** (ported from DocChat v3, upgraded): provider cards from `GET
  /api/models` — kind badge (free/freemium/paid), accuracy meter, speed/cost/context
  chips, "get a key" steps, live key test (`/api/models/validate`), model picker, and a
  clear "Demo mode" card at the top showing today's remaining shared budget. Selected
  config chip visible in the preview widget composer.
- **Trial + premium gate**: workspace cards show "trial 1 of 2"; the gate screen (after 2)
  is warm and personal — Raj's photo/handle, LinkedIn + WhatsApp + email buttons, the
  short form. This screen is a conversion surface; design it like one.
- **Console** (E9, authenticated): agent inbox (claim/reply/resolve/handback, live),
  sources admin (crawl SSE), analytics — KPI tiles, deflection %, volume chart, top
  questions, and the **Gap Report** hero (dataviz skill).

### 8.2 Chat widget (embeddable, the demo star) — E7

As spec'd in v1 §8.1 (loader `<script data-key>` → iframe React bubble, streaming tokens,
citation chips → sources drawer, "talk to a human", human-joined banner, reconnect with
Last-Event-ID, mobile-first, host-CSS isolated) **plus v2 states**: the `notice` card
(demo-exhausted with the two get-a-key buttons; key-invalid; embed-mismatch), a subtle
"running on free demo mode" footer chip when unkeyed, and theming from tenant config.

### 8.3 Demo host page — `widget/public/demo.html` hosted on Cloudflare Pages (unchanged)

---

## 9. INFRASTRUCTURE & OPS (unchanged infra, two additions)

| Layer | Service | Plan | Cost | Notes |
|---|---|---|---|---|
| Brain | FastAPI on Railway | Hobby (existing) | ₹0 extra | stateless + 4MB FlashRank ONNX |
| Orchestration | n8n on Railway | Hobby (existing) | ~$2–3/mo credit | WF-H · WF-P · WF-O · WF-W |
| Vectors | Qdrant Cloud (existing cluster) | Free | ₹0 | `helpflow_chunks` |
| DB | Supabase Postgres | Free | ₹0 | app tables + `n8n` schema + users/leads |
| Cache/limits | Upstash Redis (existing) | Free | ₹0 | `hf:` prefix: rate + demo budget + embedsig + wa dedup |
| Portal+console | Vercel | Free | ₹0 | Next.js 14 |
| Widget | Cloudflare Pages | Free | ₹0 | embed.js + iframe app + demo.html |
| Alerts+leads | Slack + Gmail | Free | ₹0 | n8n notifications to Raj |
| WhatsApp (opt) | Meta Cloud API test number | Free | ₹0 | E11 |
| LLM/embed | **Demo: Raj's Groq + OpenRouter free-tier keys · BYOK: user's keys** | — | ≈₹0 | LangChain factory |
| Monitoring | UptimeRobot | Free | ₹0 | /health + /webhook/health |

Config discipline unchanged: everything via `config.py` env / n8n `$env`; `.env`
gitignored; workflow JSON + snippets versioned with `// source:` markers; `check-sync.mjs`
proves no drift. Python deps: `langchain`, `langchain-openai`, `langchain-anthropic`,
`langchain-google-genai`, `langgraph`, `flashrank` replace `litellm` (pin
`httpx>=0.28.1,<1` — DocChat hit the exact conflict). **Install into a native-Linux-FS
venv (`/home/raj/.venvs/helpflow`), never into `/mnt/d`** (drvfs is pathologically slow);
and NEVER `railway up` from `/mnt/d` — use the `git archive HEAD | tar -x -C /tmp/...`
recipe (drvfs corrupts files; see DocChat's incident).

---

## 10. REPOSITORY STRUCTURE (v2 delta marked ★)

```
helpflow/
├── docs/ (ARCHITECTURE.md · BUILD-PROMPTS.md · specs/ 00-INDEX + E1..E11)
├── backend/
│   ├── main.py
│   ├── llm/                          ★ ported from DocChat v3
│   │   ├── catalog.py                #   §4.2 registry (the ONE hardcoded-model exception)
│   │   ├── runconfig.py              #   X-LLM-*/X-Embed-* parsing — keys touch ONLY this
│   │   ├── factory.py                #   LangChain builders + reasoning-off for OpenRouter
│   │   ├── gateway.py                #   semaphore · role timeouts · demo chain · BYOK no-fallback
│   │   └── reranker.py               #   FlashRank, degrade-to-noop
│   ├── graph/support_graph.py        ★ LangGraph StateGraph (§3.2)
│   ├── agents/ (rewrite · retrieval · answer · escalation)   # as built; now call gateway
│   ├── pipeline/chat_pipeline.py     # becomes a thin invoker of the graph (E4)
│   ├── ingestion/ (crawler · extractor · chunker · ingest_service)  # as built (E2)
│   ├── channels/ (conversation_store · subscribe)             # as built
│   ├── services/                     ★ users.py · trials.py · demo_budget.py · embed_signature.py
│   ├── utils/ (config · guardrails · rrf · qdrant · redis · supabase · sse · security★)
│   │           # llm_router.py + embeddings.py are DELETED by E4 (replaced by llm/)
│   ├── prompts/ (v1 set + demo_exhausted.md★ + trial_limit.md★)
│   ├── api/ (auth★ · models★ · workspaces★ · premium★ · admin_sources · chat ·
│   │         conversations · health)
│   ├── middleware/ (rate_limit · tenant_auth · jwt_auth★)
│   ├── scripts/ (create_collection · eval_retrieval · seed_demo_tenant · cleanup_orphans)
│   └── tests/  (mirrors modules; external services mocked)
├── workflows/  wf-handoff.json · wf-premium-lead.json★ · wf-ops.json · wf-whatsapp.json
├── snippets/   verify-token.js · business-hours.js · format-lead.js★ · sla-sweep.js ·
│               normalize-wa.js · dedup.js · verify-signature.js
├── sql/        001_schema.sql · 002_views_rls.sql · 003_users_trials.sql★
├── widget/     Vite + React bubble + embed.js + demo.html
├── portal/     ★ Next.js 14 — landing · auth · wizard · Model Studio · console (was console/)
├── scripts/    export-workflows.mjs · check-sync.mjs · apply-sql.sh
└── Dockerfile · requirements.txt · .env.example · README.md · CASE-STUDY.md · CLAUDE.md
```

---

## 11. EPICS (v2 build order)

E1–E3 are **done (merged to main, built to v1 spec)** — their specs stay in the repo with
an "as built" banner. The remaining work is E4–E10 (+E11 optional). One epic per Claude
Code session, prompt from `BUILD-PROMPTS.md`, `/spec-check` gate — unchanged discipline.

| Epic | Name | Side | Depends on | Reuses |
|---|---|---|---|---|
| ~~E1~~ | ✅ Foundation (v1, merged) | — | — | — |
| ~~E2~~ | ✅ Ingestion (v1, merged) | — | — | — |
| ~~E3~~ | ✅ Answer + escalation (v1, merged) | — | — | — |
| **E4** | **Model layer v2** — LiteLLM → LangChain factory/gateway, LangGraph graph, catalog, runconfig, /api/models(+validate), demo budget plumbing, embed pin, reranker; SSE + escalation invariants FROZEN | Backend retrofit | E1–E3 | **DocChat v3 `backend/llm/` + `graph/` (port near-verbatim)** |
| **E5** | **Accounts, workspaces & gates** — auth (users in Supabase), self-serve workspaces, trial counter + caps, premium-contact API + leads table, JWT scoping of admin/console routes | Backend | E4 | DocChat v2 auth (security.py, jwt) |
| **E6** | **n8n orchestration** — WF-H handoff notify (v1 E4 spec, unchanged) + WF-P premium-lead notify | n8n | E3, E5 | LeadFlow n8n discipline |
| **E7** | **Chat widget** — v1 E5 spec + notice states (demo-exhausted card, key-invalid, embed-mismatch) + demo-mode chip | UI | E4, E5, E6 | DocChat frontend patterns |
| **E8** | **Portal: landing + auth + wizard + Model Studio + gates** — the beautiful-display hero | UI | E5, E7 | DocChat v3 ModelStudio + v2 design system |
| **E9** | **Console** — inbox, sources admin, analytics + gap report (v1 E6 spec, inside the portal app) | UI | E8 | LeadFlow dashboard patterns, dataviz |
| **E10** | **Ship** — WF-O ops/digest, check-sync, deploy all, monitoring, README/CASE-STUDY/LOOM (sales artifacts now ALSO tell the BYOK/tiers story) | Polish | E9 | LeadFlow ship playbook |
| E11 | *(optional)* WhatsApp channel (v1 E8 spec; runs demo mode) | n8n | E4, E6 | — |

Suggested schedule: Day 1 E4 · Day 2 E5 · Day 3 E6 · Day 4–5 E7 · Day 6–7 E8 · Day 8 E9 ·
Day 9 E10 · (Day 10 E11).

---

## 12. QUALITY BAR (portfolio non-negotiables — v1's nine, plus three)

1. **Grounded-or-handoff** — deterministic escalation, tested (unchanged).
2. **Tenant isolation everywhere** — Qdrant filter choke point + RLS views + v2 ownership
   scoping (a user can only touch owned workspaces). Tested both sides.
3. **Guardrail before any LLM call** (unchanged).
4. **Guarded UPDATE for every transition** — now ALSO the trial counter (§5.3).
5. **AI never talks over a human** (unchanged).
6. **WhatsApp idempotency** (E11, unchanged).
7. **Timeout + fallback on every external call; degrade, never break** — and in BYOK, NO
   silent model substitution: fallback chains exist only in demo mode.
8. Zero secrets in the repo; n8n repo-sync clean (unchanged).
9. **BYOK keys never stored/logged server-side** — headers parsed only in `runconfig.py`;
   a test greps handlers/logs for key leakage paths.
10. **Demo mode = free-tier open-source models only, budget-capped, honest when
    exhausted** — the `demo_exhausted` copy ships as product copy, tested.
11. **Trial gate is server-enforced** (2 workspaces/account, atomic guarded increment) —
    the premium path (form → premium_leads → WF-P → Raj pinged) is traced end-to-end
    before ship.
12. README: live portal + widget demo, architecture diagram, escalation→takeover GIF,
    Model Studio screenshot, deflection + gap-report screenshots, ethics/safety AND
    BYOK-trust sections, honest limitations (incl. §4.4), real measured numbers only.

---

## 13. v1 → v2 MIGRATION MAP (what E4/E5 actually touch in merged code)

| As built (E1–E3, v1) | v2 disposition |
|---|---|
| `utils/llm_router.py` (LiteLLM Router, roles, semaphore, StreamInterrupted) | **DELETED**; semantics preserved in `llm/gateway.py` (same role names/timeouts, same StreamInterrupted contract — agents' call sites change import only) |
| `utils/embeddings.py` (gemini-embedding-001 via LiteLLM) | **DELETED**; `llm/factory.py` embeddings + `services/embed_signature.py` pin |
| `pipeline/chat_pipeline.py` (linear async orchestrator) | Becomes a thin wrapper that invokes `graph/support_graph.py`; the §3.2 order, early exits, and SSE emissions are behavior-identical (E3's tests keep passing with import updates) |
| `agents/*` (rewrite, retrieval, answer, escalation) | Kept; they call the gateway; retrieval gains the reranker hop; escalation node untouched |
| E3's SSE contract | **FROZEN**, additive `notice` event only |
| `middleware/tenant_auth.py` (X-Widget-Key) + shared ADMIN_TOKEN | Kept; E5 adds `jwt_auth.py`; human-facing admin goes JWT-scoped, ADMIN_TOKEN remains for scripts |
| E2 flagged "revisit per-tenant admin accounts at E6" | Resolved by E5 (owner accounts) |
| Config: `ROUTER_MODEL`/`ANSWER_MODEL`/`EMBED_MODEL` env | Renamed `DEMO_REWRITER_MODEL`/`DEMO_ANSWERER_MODEL`/`DEMO_EMBED_MODEL` (+ demo budget caps, trial caps, JWT_SECRET, RAJ_* contact links) — `.env.example` rewritten |
| `requirements.txt`: litellm | Swapped for langchain-* + langgraph + flashrank; `httpx>=0.28.1,<1` |
| sql 001/002 | Untouched; `003_users_trials.sql` is additive |
| Tests (74+ passing) | All kept green through E4/E5 — a retrofit that breaks E3's escalation truth table or SSE tests is WRONG by definition |
```
