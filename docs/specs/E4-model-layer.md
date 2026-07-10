# SPEC E4 — Model layer v2: LiteLLM → LangChain factory/gateway + LangGraph graph + BYOK

**Epic:** E4 · **Depends on:** E1–E3 (merged) · **Architecture refs:** §3.2, §4 (all), §10, §13

## Objective
Retrofit the merged E1–E3 brain from LiteLLM to the v2 model layer: a LangChain **factory**
(5 BYOK providers), a **gateway** chokepoint (semaphore, role timeouts, demo failover
chain, StreamInterrupted), the **LangGraph support graph**, the static **catalog** +
`/api/models` endpoints, per-request **BYOK runconfig headers**, the **demo daily budget**,
the **per-tenant embedding-space pin**, and the FlashRank reranker. After this epic the
brain serves demo mode AND any user's key — with every E3 behavior (pipeline order, SSE
contract, escalation truth table, tenant isolation) intact and its tests still green.

## Port, don't reinvent — DocChat v3 did this exact retrofit
Read these FIRST and port near-verbatim (adapting session→tenant, dc:→hf:):
- `/mnt/d/PortfolioProjects/DocChat/backend/llm/` — catalog.py, runconfig.py, factory.py,
  gateway.py, reranker.py
- `/mnt/d/PortfolioProjects/DocChat/backend/graph/chat_graph.py`
- `/mnt/d/PortfolioProjects/DocChat/backend/services/embed_signature.py`
- `/mnt/d/PortfolioProjects/DocChat/backend/tests/llm/test_factory.py` — the
  reasoning-off regression test (the single highest-impact finding of DocChat's live run)

## Deliverables
```
backend/llm/catalog.py               # §4.2 registry (HelpFlow edition — includes
                                     #   nvidia/nemotron-3-ultra-550b-a55b:free, July 2026)
backend/llm/runconfig.py             # X-LLM-*/X-Embed-* header parsing — keys touch ONLY this
backend/llm/factory.py               # LangChain builders; OpenRouter-only reasoning-off
backend/llm/gateway.py               # semaphore · role timeouts · demo chain · BYOK no-fallback
backend/llm/reranker.py              # FlashRank ~4MB ONNX, degrade-to-noop
backend/graph/support_graph.py       # the §3.2 StateGraph
backend/services/demo_budget.py      # hf:demo:{yyyymmdd}:{chat|embed} counters + caps
backend/services/embed_signature.py  # hf:embedsig:{tenant} pin (§4.5)
backend/api/models.py                # GET /api/models · POST /api/models/validate
backend/prompts/demo_exhausted.md    # the §4.3 explainer copy (product copy)
requirements.txt                     # -litellm  +langchain-* +langgraph +flashrank; httpx>=0.28.1,<1
DELETED: backend/utils/llm_router.py, backend/utils/embeddings.py
```

## Requirements
1. **Factory** (`llm/factory.py`): `ChatOpenAI` covers openrouter/groq/openai via
   `base_url`; `ChatAnthropic`; `ChatGoogleGenerativeAI`. Embeddings likewise, ALL pinned
   to 768 dims (Matryoshka `dimensions` where supported). **OpenRouter chat models bind
   `extra_body={"reasoning": {"enabled": False}}`; no other provider gets that field**
   (Groq 400s on it). Port DocChat's factory test to lock it in.
2. **Gateway** (`llm/gateway.py`) replaces `utils/llm_router.py` with the SAME public
   surface (`complete(role,…)`, `stream(role,…)`, `StreamInterrupted(partial_tokens)`,
   role timeouts rewrite=8s/answer=30s, global semaphore held for the whole stream) so
   agent call sites change **imports only**. Demo mode (no runconfig) = env chain
   `DEMO_*_MODEL` with Groq↔OpenRouter-free failover. **BYOK = the user's exact
   provider/model, NO fallback** — failures surface as typed errors the API maps to
   `notice` events (invariant #7 note).
3. **Runconfig** (`llm/runconfig.py`): parse `X-LLM-Provider/Model/Key` +
   `X-Embed-Provider/Model/Key` per request; validate provider ids against the catalog;
   reject unknown combos 422. **Keys must never appear in logs, Redis, Postgres, or error
   bodies** — add the leak-grep test (invariant #9).
4. **Catalog + endpoints** (`llm/catalog.py`, `api/models.py`): the §4.2 table exactly —
   Groq (llama-3.3-70b ★, gpt-oss-120b/20b, qwen3-32b, llama-3.1-8b-instant), OpenRouter
   free (nemotron-3-ultra-550b ★acc5, nemotron-3-super-120b ★rec, nemotron-3-nano-30b,
   gpt-oss-120b:free, llama-3.3-70b:free, gemma-4-31b:free, qwen3-next-80b:free; embed
   nvidia/llama-nemotron-embed-vl-1b-v2:free ★), Gemini, OpenAI, Anthropic; key_steps per
   provider; `allows_custom_model=True` for OpenRouter. `GET /api/models` serves it
   cached; `POST /api/models/validate` does a ~1-token live probe → `{ok, latency_ms}` or
   a typed error code (never echoes the key).
5. **Support graph** (`graph/support_graph.py`): the §3.2 nodes/edges. The escalation
   decision stays the DETERMINISTIC E3 function as a conditional edge — no LLM, no
   change to its truth table. Sequential in-order fallback if `langgraph` is unimportable.
   `pipeline/chat_pipeline.py` becomes a thin invoker; E3's pipeline-order tests
   (guardrail-zero-LLM, human_assigned-zero-LLM, escalation table, SSE sequence) must
   pass unmodified except import paths.
6. **Demo budget** (`services/demo_budget.py`): atomic INCR with midnight-UTC expiry on
   `hf:demo:{yyyymmdd}:chat|embed`; checked BEFORE any demo-mode provider call (chat,
   crawl embed, query embed). Over cap → `demo_exhausted` (SSE `notice` on streams,
   429 JSON elsewhere) rendering `prompts/demo_exhausted.md` + links
   (console.groq.com/keys, openrouter.ai/settings/keys). Provider-side quota errors in
   demo mode map to the SAME notice. BYOK requests never touch these counters.
7. **Embed pin** (`services/embed_signature.py`): first ingest pins
   `{provider, model, dims:768}` at `hf:embedsig:{tenant}`; mismatched later crawl → 409
   `embed_mismatch` with the designed explanation; queries embed with the PINNED model
   (key: header → env-if-demo-servable → notice). Last-source delete releases the pin.
   E2's ingest_service switches from `utils/embeddings.py` to the factory + pin.
8. **SSE contract FROZEN + one additive event**: `{event:"notice", code:
   "demo_exhausted"|"embed_mismatch"|"key_invalid", message, links[]}`. Existing event
   shapes byte-compatible with E3.
9. **Config** (`utils/config.py`): rename `ROUTER_MODEL/ANSWER_MODEL/EMBED_MODEL` →
   `DEMO_REWRITER_MODEL/DEMO_ANSWERER_MODEL/DEMO_EMBED_MODEL`; add `DEMO_CHAT_DAILY=150`,
   `DEMO_EMBED_DAILY=100`, `RERANK_ENABLED=true`. Rewrite `.env.example` with a comment
   per var. Health check's `llm` probe keys off the demo chain.

## Acceptance criteria
- Full pytest suite green (E1–E3 tests adapted for imports only — any behavioral test
  change is a spec violation), plus new tests: factory reasoning-off matrix, gateway demo
  failover + BYOK no-fallback, runconfig parse/reject + key-leak grep, budget
  exhaustion path, embed-pin 409, catalog endpoint shape, graph-vs-sequential parity.
- Live curl transcripts against the seeded tenant: (a) demo-mode chat streams with
  citations; (b) BYOK headers with a real Groq key serve that model (response `model`
  logged); (c) budget forced to 0 → the `notice` event with the §4.3 copy; (d) a
  mismatched X-Embed-Model crawl → 409.
- `grep -r litellm backend/` → empty; `ruff` clean.

## Required verification
Paste: pytest summary, the reasoning-off test output, the four curl transcripts, and the
empty litellm grep. `/spec-check docs/specs/E4-model-layer.md` before done.
