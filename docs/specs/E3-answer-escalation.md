# SPEC E3 — Answer engine + escalation decision (the brain)


> **STATUS: ✅ BUILT & MERGED (July 2026), to the v1.0 architecture.** Kept for the record.
> ARCHITECTURE v2.0 (BYOK + LangChain/LangGraph) retrofits this epic's LLM layer in **E4**
> and its admin/tenancy in **E5** — see ARCHITECTURE §13 for the exact disposition of each
> module. Where this spec says LiteLLM / gemini-embedding / ADMIN_TOKEN-only, §13 wins.
**Epic:** E3 · **Depends on:** E2 · **Architecture refs:** §3.2, §3.3, §4, §5.2, §6

## Objective
The chat pipeline: a customer message → guardrail → route/rewrite → retrieve → **escalation
decision** → either a streamed grounded cited answer OR a warm handoff, with everything
persisted to Supabase. Plus the human-reply subscribe channel. This is the epic that makes
HelpFlow "grounded-or-handoff". After it, `/chat/stream` answers real questions from the
seeded tenant's docs and escalates correctly on off-topic / sensitive / "get me a human".

## Port, don't reinvent
The whole pipeline shape, the rewrite agent, retrieval + RRF, and the streaming answer agent
are DocChat (`/mnt/d/PortfolioProjects/DocChat/backend/pipeline/chat_pipeline.py`,
`agents/rewrite_agent.py`, `retrieval_agent.py`, `answer_agent.py`, `utils/rrf.py`). Read
them first. NEW here: the `escalation.py` decision, the `intent`/`handoff` route in the
rewriter, conversation persistence in Supabase, and the `/chat/subscribe` SSE channel.

## Deliverables
```
backend/agents/rewrite_agent.py       # route(direct|retrieve|handoff)+queries+intent JSON (port+extend DocChat)
backend/agents/retrieval_agent.py     # embed + tenant-filtered Qdrant + RRF (ONE tenant-filter choke point)
backend/agents/answer_agent.py        # LiteLLM streamed answer + citations (port DocChat)
backend/agents/escalation.py          # deterministic escalate/answer decision (§5.2) — NO llm call
backend/pipeline/chat_pipeline.py     # async orchestrator, both early exits, persistence via BackgroundTasks
backend/channels/conversation_store.py# find-or-create, guarded transitions, message + event persistence
backend/channels/subscribe.py         # GET /chat/subscribe SSE; LISTEN/NOTIFY (or 3s poll) fan-out
backend/api/chat.py                   # POST /chat/stream (SSE), POST /chat (non-stream), GET /chat/subscribe
backend/prompts/ answerer_identity.md  citation_rules.md  router.md  handoff_message.md
                 offhours_message.md  no_sources.md
backend/tests/ (rewrite, retrieval, escalation, pipeline, conversation_store, chat API)
backend/scripts/eval_retrieval.py     # 15 questions vs the seeded tenant, expected source_urls
```

## Requirements
1. **Pipeline order is law (§3.2)**: conversation load/create → (human_assigned guard) →
   guardrail → route/rewrite → retrieve (route=retrieve only) → escalation decision →
   answer OR escalate → persist. Two deterministic early exits before any answer: the
   `human_assigned` guard (invariant #5) and the guardrail (invariant #3).
2. **human_assigned guard**: if the conversation is `human_assigned`, the AI produces NO
   answer — persist the user message, write an `event` so the agent inbox surfaces it, return
   `{event:"human_turn"}`. There must be no code path that lets the AI answer a
   human-assigned conversation. Write this test FIRST.
3. **Guardrail** (ported): injection/jailbreak → canned refusal from `guardrails.md`, zero
   LLM calls, message not stored. A test asserts zero router calls on this path.
4. **Route/rewrite** (`rewrite_agent.py`): one flash-lite call, strict JSON
   `{route, queries, handoff_reason, intent}`; `route=handoff` when the user explicitly asks
   for a human OR `intent ∈ SENSITIVE_INTENTS`. Parse error/timeout → DEFAULT
   `route=retrieve, queries=[message]` (degrade, never raise) — model this on DocChat's
   DEFAULT pattern.
5. **Retrieval** (`retrieval_agent.py`): embed queries (1 batched call) → parallel Qdrant
   search with `must=[tenant_id]` filter applied at ONE choke point → RRF (k=60) → top 6,
   each labeled `[n] {page_title} — {source_url}`. `low_relevance = best cosine <
   RELEVANCE_THRESHOLD`. A test asserts every search call carries the tenant filter and that
   two tenants cannot see each other's chunks.
6. **Escalation decision** (`escalation.py`, deterministic, NO LLM call): escalate if
   `route=='handoff'` OR `low_relevance` OR `conversation.low_conf_streak+this ≥ 2`. Returns
   `(action, reason)` where action ∈ {answer, escalate}. Increment/reset `low_conf_streak`
   accordingly. Pure function, exhaustively unit-tested.
7. **Answer** (`answer_agent.py`, ported): flash → Groq fallback, streamed; prompt =
   `answerer_identity.md` (+ tenant name/tone) + `citation_rules.md` + numbered chunks +
   history + question. Cite `[n]` per factual claim; if a specific fact isn't in the chunks,
   say so and offer a human — never invent policy/prices/dates. SSE token stream (seq ids,
   15s heartbeat, `guard_stream` output rail); final `{event:"sources"}` with cited chunks.
8. **Escalate branch**: stream `handoff_message.md` (warm, human-sounding), guarded UPDATE
   conversation → `needs_human`, insert `escalations` row `{reason}`, fire
   `POST {N8N_HANDOFF_URL}/webhook/handoff` (fire-and-forget, timeout, failure logged not
   raised — n8n being down must not break the customer's chat), final `{event:"handoff",
   reason}`.
9. **Persistence** (`conversation_store.py`, BackgroundTasks — never blocks the stream):
   user + assistant `messages` rows (with citations + confidence), `events` row, rate
   counters. All stage transitions guarded (`WHERE id=$1 AND status=$expected`).
10. **/chat** non-streaming sibling: same pipeline, returns
    `{reply, sources, escalated, reason, conversation_id, status}` — for n8n/WhatsApp (E8).
11. **/chat/subscribe** SSE: pushes `{message}` (agent replies) and `{status}` changes for a
    conversation to open widgets, via Postgres LISTEN/NOTIFY or a 3s poll fallback. Reconnect-safe.
12. **no_sources / offhours**: tenant with 0 docs → canned `no_sources.md`, no LLM. (Off-hours
    messaging is decided in n8n E4; the prompt file ships here for reuse.)

## Acceptance criteria (verify against the seeded tenant, paste transcripts)
- A normal question → streamed answer citing the correct source page(s); first token < ~1.6s.
- An off-topic question (not in the docs) → **escalates** (handoff event), does NOT fabricate.
- "I want to talk to a person" and a "refund" question → escalate via `route=handoff`.
- Two consecutive low-confidence turns → escalate on the second (streak logic).
- A `human_assigned` conversation → user message persisted, `{event:"human_turn"}`, zero LLM
  calls. A human reply via `conversation_store` appears on an open `/chat/subscribe` stream.
- `eval_retrieval.py` against the seeded tenant reports ≥ 12/15 with expected source_urls.

## Required tests
- pipeline: **zero router calls on the guardrail path** and on the human_assigned path
  (write these first); escalate branch fires the handoff and streams the canned message.
- retrieval: tenant-filter present on every search; cross-tenant isolation (A can't read B).
- escalation: exhaustive truth table (handoff / low_relevance / streak combinations).
- rewrite: parse failure → safe default; handoff route on sensitive intent.
- conversation_store: guarded transition is a no-op on an unexpected current status
  (concurrent double-escalate affects one row).
- chat API: SSE event shapes exactly match the frozen contract E5 binds to.
