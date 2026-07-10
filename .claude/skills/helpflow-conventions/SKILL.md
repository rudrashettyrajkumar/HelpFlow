---
name: helpflow-conventions
description: HelpFlow FastAPI backend conventions — config discipline, error degradation, the grounded-or-handoff + tenant-isolation + AI-never-talks-over-human invariants, SSE house style, prompt-file rules, and testing. Use when writing or reviewing ANY backend Python in this repo.
---

# HelpFlow backend conventions

Ported from DocChat's conventions; adds the escalation + multi-tenant + human-handoff
invariants that make this project different. When a util already exists in DocChat, PORT it.

## Config discipline
- Every tunable (model ids, keys, urls, limits, thresholds, `RELEVANCE_THRESHOLD`,
  `MAX_PAGES`, `SENSITIVE_INTENTS`, rate limits, `HANDOFF_TOKEN`, `N8N_HANDOFF_URL`) is read
  from env in `backend/utils/config.py` with a typed default. Service/agent code imports
  `settings` — never calls `os.getenv`, never contains a model string or a magic number.
- Adding a config value = three edits: `config.py`, `.env.example` (blank), and the
  ARCHITECTURE table if user-facing.

## Error degradation (the house style — every external call)
```python
try:
    result = await asyncio.wait_for(call(), timeout=settings.X_TIMEOUT)
except Exception:
    logger.warning("x_failed", exc_info=True)
    result = SAFE_DEFAULT   # defined next to the call, documented
```
- The customer always receives a valid SSE event; no path raises out of the pipeline or hangs
  past its timeout. Partial failure → proceed with what succeeded (one search fails → use the rest).
- Never retry-loop manually around the LLM layer — `llm/gateway.py` owns retries and the
  demo-mode failover chain (v2: LangChain factory + gateway replaced LiteLLM). BYOK
  requests deliberately have NO fallback — never silently substitute a user's model.
- BYOK keys arrive via `X-LLM-*`/`X-Embed-*` headers, parsed ONLY in `llm/runconfig.py` —
  never log/store/echo a key anywhere.
- **n8n being down must not break a chat.** Firing `/webhook/handoff` is fire-and-forget with
  a timeout; a failure is logged, the conversation still becomes `needs_human`, the customer
  still sees the warm handoff message.

## The five invariants that live in code (never weaken; each has a test)
1. **Grounded-or-handoff.** The escalation decision (`agents/escalation.py`) is deterministic
   and runs before any answer: escalate on `route=='handoff'` OR `low_relevance` OR
   `low_conf_streak≥2`. The answer prompt also forbids inventing facts. Never let the model
   "guess" to avoid an escalation.
2. **Tenant isolation.** Every Qdrant search carries the `tenant_id` filter at the ONE choke
   point in `retrieval_agent.py`. Every Supabase read the console makes goes through a
   tenant-scoped RLS view. `tenant_id` is resolved server-side from the widget key — never
   trusted from the client body.
3. **Guardrail before any LLM call.** Injection scan first; blocked → canned refusal, zero
   router calls, not stored. Test asserts zero calls on that path.
4. **Guarded transitions.** Every `conversations`/`escalations` status change is
   `UPDATE ... WHERE id=$1 AND status=$expected`. 0 rows = safe no-op. One owner per
   transition (ARCHITECTURE §5.2).
5. **AI never talks over a human.** If `conversation.status=='human_assigned'`, the pipeline
   persists the user message, writes an event, returns `{event:"human_turn"}` — and produces
   NO AI answer. This guard is the FIRST check after conversation load. Test it first.

## Prompts
- All prompt text lives in `backend/prompts/*.md`, loaded once at startup. Python composes
  blocks (`[CONTEXT]`, `[HISTORY]`, `[QUESTION]`) and injects tenant name/tone — but contains
  no prose. Keep each prompt under ~300 words.

## SSE house style (ported from DocChat utils/sse.py)
- Event framing with `seq` ids, 15s heartbeat, `Last-Event-ID` reconnect support, and
  `guard_stream` output rail (cut the stream if internal markers like `[CONTEXT]` leak).
- Frozen event vocabulary the widget binds to: `token`/`seq`, `sources`, `handoff` (with
  `reason`), `human_turn`, `done`, `error`, and (v2, additive) `notice` (`code:
  demo_exhausted|embed_mismatch|key_invalid`, `message`, `links[]`); on `/chat/subscribe`:
  `message`, `status`. Changing an existing shape is a breaking change — coordinate with E7.

## Testing
- `backend/tests/` mirrors module paths; all external services mocked via `conftest.py` —
  pytest never hits a real API. Live checks (`eval_retrieval.py`, smoke) live in
  `backend/scripts/` and are run deliberately.
- Invariant tests that must never be deleted/weakened: zero router calls on the guardrail
  path AND the human_assigned path; tenant filter on every search + cross-tenant isolation;
  the escalation truth table; a guarded transition is a no-op on an unexpected status.
- Prefer golden tests (exact expected output) for the chunker and prompt assembly.

## Style
- Python 3.12, full type hints, async-first, `ruff` clean before commit.
- Boring beats clever; a solo fresher maintains this. Commit format: `feat(E3): …`.
