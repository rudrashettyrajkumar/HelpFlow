# HELPFLOW — SOLUTION DESIGN & TECHNICAL ARCHITECTURE
**v1.0 · July 4, 2026 · Budget: ₹0 extra/month (rides on existing free tiers + Railway Hobby) · Timeline: ~1.5 weeks**

> Portfolio Project #3 (the capstone): "An AI customer-support agent trained on your
> website that answers with citations, knows when it doesn't know, and hands off to a
> human instead of guessing — on web chat and WhatsApp." This project deliberately
> **fuses Project #1 and Project #2**: it reuses DocChat's FastAPI RAG brain (crawl →
> chunk → embed → grounded cited streaming answer) and LeadFlow's n8n orchestration +
> Supabase stage machine (human handoff, multi-channel, notifications). Target audience:
> Upwork/Fiverr clients who want "an AI chatbot for my website/WhatsApp that actually
> uses our real docs and escalates to us when needed." This demo IS that gig.

---

## 1. PRODUCT SUMMARY

A business owner pastes their website (or sitemap) URL into HelpFlow's admin. HelpFlow
crawls it, extracts the text, and builds a knowledge base. Then a small chat bubble drops
onto their site (one `<script>` tag) and onto WhatsApp. When a customer asks a question,
the AI answers **only from the business's real docs**, with citations back to the source
page — and the moment it's unsure, or the customer asks for a person, or the topic is
sensitive (refund, complaint, cancellation), it **hands off to a human** instead of making
something up. The human gets pinged in Slack/email, opens an agent inbox, and takes over
the same conversation live — on web or WhatsApp. An owner dashboard shows how many
questions the AI deflected, and a **"gap report"** of questions customers asked that the
docs didn't cover (i.e. what to go write next).

**What this demo is selling (the real product is Raj's skill):**

| Visible feature | Skill it proves |
|---|---|
| Answers only from the client's real website, with citations | Grounded RAG, no hallucination (the #1 client fear) |
| "I'm not sure — let me get a human" instead of a wrong answer | Escalation logic / responsible AI |
| Human takes over the live conversation, AI steps back | Human-in-the-loop orchestration (n8n) |
| Same agent on web chat AND WhatsApp | Multi-channel integration |
| One-line `<script>` embed, themed per business | Real product packaging, not a notebook |
| Deflection rate + "gap report" of unanswered questions | Delivering measurable business value |
| Streaming, sub-2s first token | SSE, async pipeline design |
| Full-stack: FastAPI RAG + n8n + Supabase + widget + inbox | End-to-end delivery in one project |

**Relationship to Projects #1 and #2 (the reuse story — and a portfolio talking point):**

| Layer | Comes from | What changes here |
|---|---|---|
| Config, LiteLLM router, guardrails, SSE, embeddings, RRF | **DocChat** `backend/utils/` | Ported near-verbatim |
| Ingestion (parse → chunk → embed → upsert) | **DocChat** `backend/ingestion/` | PDF parser → **website crawler**; session → **tenant** |
| Chat pipeline (guardrail → rewrite → retrieve → cited stream) | **DocChat** `backend/pipeline/` | Adds the **escalation decision** + persistence |
| Supabase stage machine + guarded transitions + RLS views | **LeadFlow** `sql/` | Lead stages → **conversation/escalation stages** |
| n8n repo-as-source-of-truth + webhook + notify discipline | **LeadFlow** `workflows/` | Outreach → **handoff + WhatsApp** orchestration |
| Next.js dashboard on the anon key + masked views | **LeadFlow** `dashboard/` | Funnel → **agent inbox + deflection analytics** |

Nothing here is invented from scratch that was already solved in #1 or #2. HelpFlow is the
proof that Raj can *compose* production systems, which is exactly what agencies pay for.

---

## 2. SYSTEM OVERVIEW

```
┌───────────────────────────────────────────────────────────────────────────┐
│  CUSTOMER SURFACES                                                          │
│  ┌────────────────────────┐        ┌──────────────────────────┐            │
│  │ Chat widget (embed.js) │        │ WhatsApp (Meta Cloud API) │  optional  │
│  │ on the client's site   │        │  or Twilio sandbox        │            │
│  └───────────┬────────────┘        └──────────────┬───────────┘            │
└──────────────┼──────────────────────────────────── ┼──────────────────────┘
               │ HTTPS + SSE (stream + subscribe)     │ inbound webhook
┌──────────────▼───────────────────────┐   ┌──────────▼─────────────────────┐
│  BACKEND "BRAIN" — FastAPI on Railway │   │  n8n "NERVOUS SYSTEM" — Railway│
│  (ports DocChat pipeline)             │   │  (ports LeadFlow discipline)   │
│  crawl · retrieve · grounded answer   │◄──┤  WF-H handoff notify + hours   │
│  escalation decision · SSE stream     │──►│  WF-W whatsapp adapter (opt)   │
│  conversation store · agent replies   │   │  WF-O ops: SLA sweep + digest  │
└───┬──────────┬───────────┬────────────┘   └───┬────────┬──────────┬────────┘
    │          │           │                    │        │          │
┌───▼────┐ ┌───▼────┐ ┌────▼─────────┐    ┌─────▼──┐ ┌───▼───┐ ┌────▼─────┐
│ Qdrant │ │ Upstash│ │  Supabase    │    │ Slack  │ │ Gmail │ │ WhatsApp │
│ Cloud  │ │ Redis  │ │  Postgres    │    │(agent  │ │(agent │ │  Cloud   │
│(vectors│ │(rate + │ │ tenants·convo│    │ alerts)│ │alerts)│ │  API     │
│ per    │ │ wa dedup│ │ msgs·escal · │    └────────┘ └───────┘ └──────────┘
│ tenant)│ │)       │ │ events · RLS │
└────────┘ └────────┘ │ views)       │        LLM/embeds: OpenRouter → Groq
                      └──────────────┘        (existing credit, LiteLLM Router)
```

Design principle carried from MyShiva/DocChat/LeadFlow: **stateless, featherweight
containers; state lives in managed free tiers.** FastAPI holds no local files or models;
n8n's own DB is Supabase (schema `n8n`), so both Railway containers restart clean.

**Why two backends (FastAPI *and* n8n) — the deliberate boundary:**
- **FastAPI is the brain and system of record.** It owns anything that needs low-latency
  streaming, RAG, and transactional conversation state: retrieval, the grounded answer,
  the escalation *decision*, and the `conversations`/`messages` tables. Streaming a cited
  answer token-by-token to a browser widget is DocChat's signature and n8n cannot do it
  well — so the brain stays in FastAPI.
- **n8n is the nervous system / ops layer.** It owns everything that is "when X happens,
  notify/route/wait": human-agent alerts, business-hours logic, SLA timers, the WhatsApp
  channel adapter, and the daily digest. This is exactly what n8n is best at and what the
  target client wants to see.
- The boundary is a thin, versioned webhook contract (§7). This split is itself a talking
  point: *"I use the right tool for each job — FastAPI for the real-time RAG core, n8n for
  the human-ops orchestration — instead of forcing everything into one."*

**No new paid accounts.** FastAPI = a new Railway service on the existing Hobby plan; n8n =
a new Railway service (or the LeadFlow instance reused with new workflows); Qdrant free
cluster gets a new collection; Supabase free hosts the tables; Upstash Redis with a `hf:`
prefix; widget + console on Cloudflare Pages/Vercel free; OpenRouter existing credit.

---

## 3. THE FLOWS

There are two ingestion-side flows (crawl) and two conversation-side flows (web, WhatsApp),
all converging on one conversation model and one escalation state machine.

### 3.1 Ingestion — website crawl (`POST /admin/sources`, SSE progress)

```
Owner submits a source { url or sitemap_url, max_pages, tenant_id }
  ↓
STEP 1 — DISCOVER (bounded BFS crawl, in-memory)
  If sitemap → read the <loc> list. Else BFS from the URL, same-domain only,
  respect robots.txt, cap at MAX_PAGES (env, default 50), skip binary/asset URLs.
  ↓
STEP 2 — FETCH + EXTRACT (per page, concurrency-limited)
  httpx GET → main-content extraction (trafilatura; Jina Reader r.jina.ai/{url}
  fallback for JS-heavy pages). Strip nav/footer/boilerplate. Reject pages with
  < 200 chars of real text. Record source_url + page title.
  ↓
STEP 3 — CHUNK (ported DocChat chunker)
  450-token chunks, 80 overlap, paragraph-preferring. Each chunk records
  source_url, page_title, chunk_index. (No page numbers — URLs are the citation unit.)
  ↓
STEP 4 — EMBED (batched, gemini-embedding-001 @ 768) → UPSERT to Qdrant
  collection `helpflow_chunks`, payload { tenant_id, source_id, source_url,
  page_title, chunk_index, text, created_at }.
  ↓
STEP 5 — RECORD (Supabase) — sources row per page: status, chunk count, crawled_at.
  Return SSE progress: discovering → fetching 12/50 → embedding 60% → ready {pages,chunks}.
```

Re-crawl (`POST /admin/sources/{id}/refresh`) deletes that source's Qdrant points by
`source_id` filter and re-ingests — no stale ghosts. Crawl is synchronous-with-SSE-progress
(same reasoning as DocChat: a queue is over-engineering at this scale and the progress
stream is a better demo). A slow crawl (>60s) may be backgrounded with a `crawling` status
the admin UI polls.

### 3.2 Conversation — web widget (`POST /chat/stream`, SSE)

```
Customer message arrives { tenant_id, conversation_id?, message }
  ↓
STEP 0 — CONVERSATION LOAD / CREATE (Supabase)
  New conversation_id if absent (server-generated). If status='human_assigned'
  → DO NOT let the AI answer (invariant #5): persist the message, notify the
  assigned agent (event), return {event:"human_turn"}. Pipeline ends.
  ↓
STEP 1 — INPUT GUARDRAIL (ported DocChat, pure Python regex, zero cost)
  Prompt-injection / jailbreak scan → canned refusal, no LLM call, not stored. Ends.
  ↓
STEP 2 — ROUTE + REWRITE (one small LLM call, ~400ms — ported DocChat rewriter)
  Model: flash-lite. Input: message + last 6 turns + tenant name.
  Output (strict JSON):
    { route: "direct" | "retrieve" | "handoff",
      queries: ["standalone query", ...],          # 1–3, when route=retrieve
      handoff_reason: "user_requested" | null,
      intent: "question" | "refund" | "complaint" | "cancel" | "human" | "chitchat" }
  route=handoff → the user explicitly asked for a human, OR intent ∈ sensitive set
    (refund/complaint/cancel/human per SENSITIVE_INTENTS env). Skip retrieval → escalate.
  route=direct → greeting/thanks/"what did you say" → answered from history, no retrieval.
  Parse failure/timeout → DEFAULT route=retrieve, queries=[message]. Degraded beats broken.
  ↓
STEP 3 — RETRIEVE (route=retrieve only; ported DocChat retrieval_agent)
  Embed queries (1 batched call) → parallel Qdrant search, filter must=[tenant_id],
  top-8/query → RRF (k=60) → top 6 chunks, each labeled "[n] {page_title} — {source_url}".
  low_relevance = best cosine < RELEVANCE_THRESHOLD (env, default 0.30).
  ↓
STEP 4 — ESCALATION DECISION (deterministic, the new brain logic — see §5.2)
  Escalate (→ needs_human) if ANY:
    • route == "handoff"
    • low_relevance is True (docs don't cover it — DON'T GUESS)
    • this is the 2nd consecutive low-confidence turn in the conversation
  Otherwise → ANSWER.
  ↓
STEP 5a — ANSWER (streaming; ported DocChat answer_agent)
  Model: flash → Groq fallback. Prompt (§6): support persona + grounding rules +
  numbered chunks + history + question. Cite [n] per claim; if a specific fact isn't
  in the chunks, say so and offer a human — never invent policy/prices/dates.
  SSE token stream (seq ids, 15s heartbeat, guard_stream output rail). Final
  {event:"sources"} carries cited chunks for the widget's citation chips.
  ↓
STEP 5b — ESCALATE (instead of 5a)
  Stream a canned, warm handoff message (prompts/handoff_message.md). Guarded UPDATE
  conversation → 'needs_human'. Insert escalations row {reason}. Fire n8n
  POST /webhook/handoff. Final {event:"handoff", reason}. The widget shows "connecting
  you to a person…".
  ↓
STEP 6 — PERSIST (BackgroundTasks, never blocks)
  messages rows (user + assistant, with citations + confidence), events row, rate counter.

Latency to first token: ~1.2–1.6s (same as DocChat).
```

The orchestrator is one async function (`pipeline/chat_pipeline.py`) — linear, deterministic
early exits, data-driven routing. **No agent framework** (ported stance from DocChat: "I
know when NOT to use LangChain").

### 3.3 Conversation — human reply delivery (widget ↔ agent, live)

The widget holds an SSE subscription per conversation: `GET /chat/subscribe?conversation_id=…`.
The FastAPI publishes `message` and `status` events on it. When a human agent replies via the
console (`POST /conversations/{id}/reply`), the message is persisted and pushed onto every open
subscriber's SSE stream — so the customer sees the human's reply appear live in the same
bubble. Delivery uses Postgres `LISTEN/NOTIFY` (or a 3s poll fallback) — no Redis pub/sub
needed to stay featherweight. Status events also drive the widget banner ("A human joined",
"Conversation resolved").

### 3.4 Conversation — WhatsApp (optional, E8)

```
Customer texts the WhatsApp number
  ↓ Meta Cloud API (or Twilio) → n8n POST /webhook/whatsapp
n8n: verify signature; dedup by message id (hf:wa:{id} in Redis, invariant #7);
     map wa_phone → conversation (find-or-create by tenant+phone)
  ↓ HTTP → FastAPI POST /chat  (non-streaming sibling of /chat/stream)
FastAPI: same pipeline §3.2 minus SSE → returns { reply, sources, escalated, status }
  ↓ n8n: send reply back to WhatsApp (with source links appended as plain text)
  ↓ if escalated → same handoff notify path (WF-H). Human replies in the inbox →
    FastAPI fires an outbound event → n8n WF-W delivers it to the WhatsApp thread.
```

WhatsApp reuses the entire brain — it is just a second channel adapter. This is why the
conversation model is channel-agnostic (`channel` column) from E1.

---

## 4. MODEL / AI STRATEGY

Identical gateway philosophy to all three projects: cheap models, strict JSON contracts,
fallback on failure, degrade-never-break, everything through env-configured LiteLLM Router
(OpenRouter primary → Groq fallback). Same OpenRouter account/key as MyShiva/DocChat.

| Role | Prompt file | Primary (via OpenRouter) | Fallback (Groq) | Contract |
|---|---|---|---|---|
| Route + rewrite + intent | `router.md` | `google/gemini-3.1-flash-lite-preview` | `llama-3.3-70b-versatile` | strict JSON (route/queries/intent) |
| Answer (streamed) | `answerer_identity.md` + `citation_rules.md` | `google/gemini-3-flash-preview` | `llama-3.3-70b-versatile` | cited, grounded, escalate-not-guess |
| Embeddings | — | `google/gemini-embedding-001` (768) | — | crawl + queries |
| (Gap-report clustering, E6, offline) | `gap_cluster.md` | `google/gemini-3.1-flash-lite-preview` | — | batch, non-user-facing |

All model IDs via `backend/utils/config.py` env vars — never hardcoded (invariant carried
from every prior project). Async semaphore caps concurrent LLM calls at 8. **The escalation
decision itself is NOT an LLM call** — it's deterministic (route + low_relevance + streak),
so it's fast, testable, and free. The one intent signal it consumes comes from the rewrite
call it was already making.

**Capacity math:** a busy demo week ≈ 40 conversations/day × 4 turns = 160 turns/day →
~160 rewrite + ~130 answer + ~160 embed calls ≈ 450 calls/day ≈ $0.40/month of existing
OpenRouter credit. Trivial.

---

## 5. DATA DESIGN (the fusion of DocChat's vectors + LeadFlow's state machine)

Two stores, clean split of concerns:
- **Qdrant** — knowledge (vectors), multi-tenant by payload filter (from DocChat).
- **Supabase Postgres** — conversations, escalations, tenants, events, analytics
  (from LeadFlow). This is the system of record and the agent inbox's backing store.
- **Upstash Redis** — rate limits + WhatsApp message-id dedup only (`hf:` prefix). No
  business state lives in Redis.

### 5.1 Qdrant — one collection, tenant-filtered

```
Collection: helpflow_chunks   (768 dims, cosine)
Payload:    tenant_id  (keyword, indexed)   ← tenant isolation — MANDATORY on every search
            source_id  (keyword, indexed)   ← per-source delete / re-crawl
            source_url, page_title, chunk_index, text, created_at
```

Mandatory `tenant_id` filter on every search, applied at one choke point in
`retrieval_agent.py` (ported from DocChat's session-filter choke point). A test asserts no
search can run without it. Capacity: free 1GB cluster easily holds several tenants' sites
(a 50-page site ≈ 300 chunks); non-issue.

### 5.2 Supabase — tables (`public` schema, migrations in `sql/`)

```
tenants        id uuid PK · name · website_url · widget_config jsonb (theme, greeting,
               brand color) · sensitive_intents text[] · created_at
               (a "tenant" = one business using HelpFlow; the demo ships with 1–2 seeded)

sources        id uuid PK · tenant_id FK · url · type ('page'|'sitemap') · title
               · status ('crawling'|'ready'|'error') · chunk_count int · crawled_at
               · error text                     (one row per crawled page)

conversations  id uuid PK · tenant_id FK · channel ('web'|'whatsapp')
               · external_ref text              (wa phone / widget session)
               · status text NOT NULL default 'ai_handling'  (CHECK: the enum below)
               · assigned_agent text · customer_email text · last_activity_at
               · low_conf_streak int default 0  · created_at · updated_at
               UNIQUE (tenant_id, channel, external_ref)   ← find-or-create key

messages       id uuid PK · conversation_id FK · role ('user'|'assistant'|'agent'|'system')
               · body text · citations jsonb [{n, source_url, page_title, snippet}]
               · confidence text ('answered'|'low'|'escalated') · created_at

escalations    id uuid PK · conversation_id FK · reason text
               ('user_requested'|'low_relevance'|'sensitive_intent'|'repeated_low_conf')
               · status ('open'|'notified'|'assigned'|'resolved') · assigned_agent
               · notified_at · resolved_at · created_at

events         id uuid PK · conversation_id FK · type text · detail jsonb · created_at
               (types: answered, escalated, notified, agent_joined, agent_reply,
                resolved, handed_back, whatsapp_in, whatsapp_out, gap_logged,
                workflow_error)
```

### 5.2 Conversation stage machine (the spine — ported from LeadFlow)

```
ai_handling ──escalate──► needs_human ──agent claims──► human_assigned ──resolve──► resolved
     │                        │                              │
     │                        │                              └──hand back──► ai_handling
     └──AI resolved / idle────┴──────────────────────────────────────────► resolved
                                  (off-hours + no email + idle timeout → abandoned)
```
CHECK enum: `ai_handling, needs_human, human_assigned, resolved, abandoned`.

**Transition ownership (one owner per transition — races impossible by construction):**

| Transition | Owner | Guard |
|---|---|---|
| `ai_handling → needs_human` | FastAPI answer engine (escalation decision) | `WHERE status='ai_handling'` |
| `ai_handling → resolved` | FastAPI (AI wrapped it up) / idle sweep | `WHERE status='ai_handling'` |
| `needs_human → human_assigned` | Agent console (claim) | `WHERE status='needs_human'` |
| `human_assigned → resolved` | Agent console (resolve) | `WHERE status='human_assigned'` |
| `human_assigned → ai_handling` | Agent console (hand back) | `WHERE status='human_assigned'` |
| `needs_human → abandoned` | n8n WF-O SLA sweep (off-hours, no email, idle) | `WHERE status='needs_human'` |

Every transition is `UPDATE conversations SET status=$2, updated_at=now() WHERE id=$1 AND
status=$3` (LeadFlow's guarded-transition pattern, ported verbatim). Affecting 0 rows =
someone already moved it (double-claim, double-resolve, race) = safe no-op, not an error.

### 5.3 Dashboard access — RLS + masked views (ported from LeadFlow)

The console/dashboard uses the **anon key** and reads only tenant-scoped, masked views:
- `v_conversations` — id, channel, status, last message preview, escalation reason,
  `last_activity_at`; **customer_email masked** (`j***@x.com`); no raw doc text.
- `v_funnel` — per-tenant counts: total / ai_resolved / escalated / human_resolved →
  **deflection rate** = ai_resolved / total.
- `v_gaps` — questions that escalated for `low_relevance`, clustered (E6), with frequency.
- `v_events` — recent activity feed per conversation for the inbox timeline.

RLS on all base tables; anon has no base-table policy. The **service-role key exists only
inside FastAPI and n8n credentials.** Tenant scoping is enforced in the views (every view
takes a `tenant_id` filter that the console passes and RLS constrains) so one business's
console can never read another's conversations — the multi-tenant isolation invariant
extends from Qdrant to Postgres.

### 5.4 Support ethics & safety (README-visible, non-negotiable)

Grounded-only answers (never invents prices/policies/dates); escalates on uncertainty
rather than guessing; sensitive topics (refund/complaint/cancel/legal) always reach a
human; the AI never impersonates a human ("I'm HelpFlow's assistant"); PII in transcripts
is masked on the public dashboard. These are the trust properties clients actually buy.

---

## 6. PROMPT SYSTEM

Same discipline as every project: prompts are `.md` files in `backend/prompts/`, assembled
at runtime, never Python strings. Tenant-specific bits (business name, tone, greeting) are
injected from `tenants.widget_config`, so one prompt set serves all tenants.

```
answerer_identity.md   Support-agent persona: helpful, concise, on-brand, NEVER invents
                       policy/prices/hours; says "I'm {business}'s AI assistant"; markdown
                       allowed. Tone + business name injected from the tenant row.
citation_rules.md      Cite [n] per factual claim; if the answer isn't fully in the
                       sources, say what you can and offer a human — never fill gaps with
                       assumptions. Never mention "chunks"/"context"/internal machinery.
router.md              Route (direct|retrieve|handoff) + standalone queries + intent
                       classification. Ported from DocChat rewriter, adds handoff+intent.
handoff_message.md     Canned warm "let me connect you with a person" (streamed on escalate).
offhours_message.md    "Our team is offline right now — leave your email and we'll reply."
no_sources.md          Canned "this knowledge base is still being set up" (tenant has 0 docs).
guardrails.md          Canned refusal for injection attempts.
gap_cluster.md         (E6, offline) cluster unanswered questions into themes for v_gaps.

User turn = [CONTEXT] numbered labeled chunks + [HISTORY] last 6 turns + [QUESTION]
```

The persona/tone in `answerer_identity.md` and the sensitive-intent list are the
**retargeting surface**: editing them + swapping the crawled site points the whole product
at a new client. That's the demo pitch (mirrors LeadFlow's "edit scoring.md to retarget").

---

## 7. INTERFACES

### 7.1 FastAPI (Railway URL; `tenant_id` resolved from a public **widget key**, not trusted from the client)

```
# Admin (owner, simple bearer token per tenant — ADMIN_TOKEN env for the demo)
POST   /admin/sources                 {url|sitemap_url, max_pages} → SSE crawl progress
GET    /admin/sources                 → [{id, url, status, chunk_count, crawled_at}]
POST   /admin/sources/{id}/refresh    re-crawl (delete + re-ingest)
DELETE /admin/sources/{id}            remove source + its Qdrant points

# Conversation (public widget; X-Widget-Key header → tenant_id)
POST   /chat/stream                   {conversation_id?, message} → SSE: token/seq …
                                      {event:sources} | {event:handoff,reason} | {done}
POST   /chat                          non-streaming sibling (n8n/WhatsApp) → JSON
GET    /chat/subscribe                ?conversation_id → SSE: {message}|{status} (§3.3)

# Agent console (bearer, tenant-scoped)
GET    /conversations                 ?status= → tenant's conversations (masked)
GET    /conversations/{id}/messages   full transcript for the agent
POST   /conversations/{id}/reply      {body} → persist + push to widget SSE (guarded)
POST   /conversations/{id}/claim      → human_assigned (guarded)
POST   /conversations/{id}/resolve    → resolved (guarded)
POST   /conversations/{id}/handback   → ai_handling (guarded)

GET    /health                        → {status, qdrant, supabase, redis, llm}
```

### 7.2 n8n webhooks (Railway URL; header token checked in-workflow, per LeadFlow)

```
POST /webhook/handoff        FastAPI → n8n: {conversation_id, tenant, reason, transcript_url}
                             → Slack + Gmail alert to the on-call agent; business-hours
                             branch; writes events. Header X-Handoff-Token.
POST /webhook/whatsapp        Meta/Twilio inbound (E8). Signature-verified, id-deduped.
POST /webhook/agent-outbound  FastAPI → n8n (E8): deliver a human reply to a WhatsApp thread.
GET  /webhook/health          200 for UptimeRobot.
```

Rate limits (Redis, per widget-key + per conversation): 30 messages/conversation/hour,
200 messages/tenant/day, 4 crawl jobs/tenant/day. Exceeded → 429 with a friendly JSON the
widget renders. This is the abuse shield (no end-user auth on the widget).

---

## 8. FRONTEND — three surfaces

### 8.1 Chat widget (the demo star, embeddable) — E5

Vanilla `embed.js` loader (one `<script src=…?key=WIDGET_KEY>` tag) that injects an iframe
hosting a React 18 + Vite + Tailwind bubble. No component-library bloat.

```
┌────────────────────────────────────┐
│  ● Acme Support        AI assistant │  ← header: business name + status pill
├────────────────────────────────────┤
│  ▸ Hi! Ask me anything about Acme.  │
│  ▸ [customer] do you ship to Canada?│
│  ◂ Yes — we ship to Canada in 3–5   │
│    business days [1]. citation chip →│  ← click chip = source page opens
│  ── A human has joined ✋ ──────────  │  ← status banner on handoff
│  ◂ [Priya, Acme] Happy to help with │
│    your refund…                     │
├────────────────────────────────────┤
│  [ type a message…            ] ➤   │
│  Talk to a human · powered by …     │  ← explicit escalate button
└────────────────────────────────────┘
```

UX rules (mirror DocChat resilience): SSE streaming with `Last-Event-ID` reconnect
(1s/2s/4s/8s); the `/chat/subscribe` stream shows human replies live; typing indicator;
"Talk to a human" always available; theme (color, greeting, name) from the tenant config;
empty/error/limit states designed; mobile-first (the bubble is often opened on phones).

### 8.2 Agent console — E6

Next.js 14 App Router + Tailmind on Vercel. Two views behind a simple login:
- **Inbox**: list of conversations (filter by status), unread/needs-human highlighted;
  open one → full transcript → reply box → Claim / Resolve / Hand back to AI buttons.
  New human-needed conversations arrive live (poll `v_events` / SSE).
- **Analytics**: KPI tiles (conversations, **deflection rate %**, escalations, avg
  first-response), a volume chart, top questions, and the **Gap Report** — clustered
  unanswered questions with frequency and a "these are the docs to write next" framing.
  The gap report is the highest-value, most-filmable feature for the Loom.

### 8.3 Admin (source management) — folded into E6 console

Add website URL / sitemap → watch crawl progress (SSE) → see per-page status + chunk
counts → refresh/delete. Minimal; the point is "paste your site, it learns it."

Invoke the **dataviz** skill before building the deflection tiles, volume chart, and gap
report (consistent, accessible, light+dark — same rule LeadFlow used for its funnel).

---

## 9. INFRASTRUCTURE & OPS

| Layer | Service | Plan | Cost | Notes |
|---|---|---|---|---|
| Brain | FastAPI on Railway (new service, existing project) | Hobby (existing) | ₹0 extra | featherweight, stateless |
| Orchestration | n8n Docker on Railway (new service, or reuse LeadFlow's) | Hobby (existing) | ~$2–3/mo credit | handoff + whatsapp + ops |
| Vectors | Qdrant Cloud (existing cluster) | Free | ₹0 | collection `helpflow_chunks` |
| DB | Supabase Postgres | Free | ₹0 | `public` app tables + `n8n` schema |
| Cache/limits | Upstash Redis (existing) | Free | ₹0 | `hf:` prefix, rate + wa dedup |
| Widget | Cloudflare Pages | Free | ₹0 | embed.js + iframe app |
| Console | Vercel | Free | ₹0 | agent inbox + analytics |
| Agent alerts | Slack (free workspace) + Gmail | Free | ₹0 | n8n notifications |
| WhatsApp (opt) | Meta WhatsApp Cloud API test number (or Twilio sandbox) | Free | ₹0 | E8 only |
| LLM/embed | OpenRouter (existing credit) + Groq | — | ≈$0.40/mo | LiteLLM Router |
| Monitoring | UptimeRobot | Free | ₹0 | /health + /webhook/health every 5 min |

**Config:** all keys/models/limits/thresholds via `backend/utils/config.py` (FastAPI) and
`$env` (n8n) — never hardcoded. `.env` gitignored, `.env.example` committed blank. n8n
workflow JSON, Code-node JS, and prompts are versioned in the repo with `// source:` /
`<!-- source: -->` markers; `scripts/check-sync.mjs` (E7) proves no drift (LeadFlow
discipline, ported).

**Crons (GitHub Actions / n8n schedule):** daily Qdrant keepalive + orphan-chunk cleanup;
n8n WF-O SLA sweep (escalations open > SLA → re-alert; off-hours + idle → abandoned) +
daily digest (deflection rate, open escalations, gap-report highlights).

---

## 10. REPOSITORY STRUCTURE

```
helpflow/
├── docs/
│   ├── ARCHITECTURE.md               ← this file
│   ├── BUILD-PROMPTS.md              # one Claude Code prompt per epic
│   └── specs/                        # 00-SPEC-INDEX + E1..E7 (+E8 optional)
├── backend/                          # FastAPI "brain" (ports DocChat)
│   ├── main.py
│   ├── pipeline/chat_pipeline.py     # async orchestrator (§3.2) incl. escalation decision
│   ├── agents/
│   │   ├── rewrite_agent.py          # route + queries + intent JSON
│   │   ├── retrieval_agent.py        # embed + tenant-filtered Qdrant + RRF (choke point)
│   │   ├── answer_agent.py           # LiteLLM stream + citations
│   │   └── escalation.py             # deterministic escalate/answer decision (§5.2)
│   ├── ingestion/
│   │   ├── crawler.py                # discover (sitemap/BFS), robots, page cap
│   │   ├── extractor.py              # fetch + trafilatura/Jina main-content extraction
│   │   ├── chunker.py                # ported DocChat chunker (url-tracked)
│   │   └── ingest_service.py         # orchestrates crawl→extract→chunk→embed→upsert
│   ├── channels/
│   │   ├── conversation_store.py     # find-or-create, guarded transitions, message persist
│   │   └── subscribe.py              # /chat/subscribe SSE + LISTEN/NOTIFY fan-out
│   ├── utils/  (config, llm_router, guardrails, rrf, qdrant_client, redis_client,
│   │           supabase_client, sse, embeddings — mostly ported from DocChat)
│   ├── prompts/  (answerer_identity, citation_rules, router, handoff_message,
│   │             offhours_message, no_sources, guardrails, gap_cluster — all .md)
│   ├── api/  (admin_sources.py  chat.py  conversations.py  health.py)
│   ├── middleware/ (rate_limit.py  tenant_auth.py)
│   ├── scripts/  (create_collection.py  eval_retrieval.py  seed_demo_tenant.py
│   │             cleanup_orphans.py)
│   └── tests/    (mirrors module paths; external services mocked)
├── workflows/                        # canonical n8n exports (via export script)
│   ├── wf-handoff.json  wf-whatsapp.json  wf-ops.json
├── snippets/                         # n8n Code-node JS (source of truth)
│   ├── verify-signature.js  dedup.js  normalize-wa.js  business-hours.js
├── n8n-prompts/                      # (none needed — the brain owns all LLM calls)
├── sql/                              # 001_schema.sql  002_views_rls.sql
├── widget/                           # Vite + React embeddable bubble + embed.js loader
├── console/                          # Next.js 14 agent inbox + analytics + admin
├── scripts/                          # export-workflows.mjs  check-sync.mjs
├── Dockerfile  requirements.txt  .env.example  README.md  CASE-STUDY.md  CLAUDE.md
```

---

## 11. EPICS (build order)

This is the capstone and is honestly larger than #1/#2 — **7 core epics + 1 optional**
(WhatsApp). Still one epic per Claude Code session; the reuse from DocChat/LeadFlow keeps
each epic small despite the bigger surface.

| Epic | Name | Side | Depends on | Reuses |
|---|---|---|---|---|
| **E1** | Foundation — FastAPI skeleton, Supabase schema+RLS+views, Qdrant, n8n on Railway, clients, guardrails, health | Backend/Infra | — | DocChat utils, LeadFlow sql/export |
| **E2** | Ingestion — website crawler → extract → chunk → embed → upsert, admin API, crawl SSE | Backend | E1 | DocChat chunker/embed/qdrant |
| **E3** | Answer + escalation — pipeline, rewrite+intent, retrieval, escalation decision, streaming, persistence | Backend + AI | E2 | DocChat pipeline/agents |
| **E4** | Handoff orchestration — WF-H notify (Slack/Gmail), business hours, escalation state, agent-reply delivery | n8n | E3 | LeadFlow n8n discipline |
| **E5** | Chat widget — embeddable loader + React bubble, streaming, citations, handoff/human-joined states, subscribe | UI | E3 (API), E4 (handoff) | DocChat frontend patterns |
| **E6** | Console — agent inbox (claim/reply/resolve/handback) + admin sources + analytics + gap report | UI | E5, E4 | LeadFlow dashboard patterns |
| **E7** | Ship — WF-O ops/digest, check-sync, deploy all, monitoring, README, case study, Loom | Polish | E6 | LeadFlow ship playbook |
| **E8** | *(optional)* WhatsApp channel — WF-W adapter, dedup, /chat non-stream wiring, outbound delivery | n8n | E3, E4 | — |

One epic per session. Every spec ends with **Acceptance criteria** + **Required
tests/verification**; DONE only when tests pass, `ruff`/`build` clean, and `/spec-check`
passes. Suggested schedule: Day 1 E1 · Day 2 E2 · Day 3 E3 · Day 4 E4 · Day 5 E5 ·
Day 6–7 E6 · Day 8 E7 · (Day 9 E8 optional).

---

## 12. QUALITY BAR (portfolio non-negotiables)

1. **Grounded-or-handoff:** the AI never invents an answer. Low relevance / sensitive
   intent / explicit request → escalate to a human. Verified with an off-topic and a
   "refund" question against the seeded tenant; a test asserts escalation fires and no
   answer is fabricated.
2. **Tenant isolation everywhere:** every Qdrant search carries the `tenant_id` filter
   (one choke point, tested) and every console read goes through tenant-scoped RLS views.
   A test asserts tenant A cannot retrieve tenant B's chunks or conversations.
3. **Guardrail before any LLM call;** injection attempts never reach a model. Tested.
4. **Every conversation transition is a guarded UPDATE** — double-claim/double-resolve are
   no-ops. Tested with a concurrent-claim simulation.
5. **AI never talks over a human:** once `human_assigned`, the AI produces no messages for
   that conversation until hand-back. Verified end-to-end.
6. **WhatsApp idempotency (E8):** the same inbound message id is processed exactly once.
7. Every external call has timeout + fallback; the user always gets a response.
8. Zero secrets in the repo; `.env.example` complete; n8n repo-sync clean (check-sync).
9. README: live widget demo (embedded on a throwaway site), architecture diagram, GIF of
   an escalation → human takeover, deflection-rate + gap-report screenshots, honest
   limitations, and the ethics/safety section. Real measured numbers only.
```