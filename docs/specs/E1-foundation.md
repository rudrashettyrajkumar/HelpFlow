# SPEC E1 — Foundation: FastAPI skeleton, Supabase schema, Qdrant, n8n, clients

**Epic:** E1 · **Depends on:** — · **Architecture refs:** §2, §4, §5, §7, §9, §10

## Objective
The skeleton that every later epic builds on: a FastAPI app that boots with health checks,
all external-service clients (Qdrant, Supabase, Redis, LiteLLM Router) wired and env-driven,
the input guardrail, the Qdrant collection, the full Supabase schema + RLS views, and n8n
live on Railway. After this epic, `GET /health` is green against real services and `psql`
shows the conversation stage machine enforced by constraints.

## Deliverables
```
backend/main.py                       # FastAPI app, CORS, startup: create collection + prompt load
backend/utils/config.py               # ALL env → typed settings (port DocChat, extend)
backend/utils/llm_router.py           # LiteLLM Router, OpenRouter→Groq failover, semaphore (port DocChat)
backend/utils/guardrails.py           # injection/jailbreak regex scan (port DocChat)
backend/utils/qdrant_client.py        # async client + create_collection helper
backend/utils/supabase_client.py      # service-role client (server-side only)
backend/utils/redis_client.py         # Upstash client, hf: prefix
backend/utils/sse.py                  # event framing, heartbeat, seq ids, guard_stream (port DocChat)
backend/utils/embeddings.py           # batched gemini-embedding-001 @ 768 (port DocChat)
backend/api/health.py                 # GET /health → per-dependency status
backend/middleware/tenant_auth.py     # X-Widget-Key → tenant_id; admin bearer; per-epic stubs ok
backend/scripts/create_collection.py  # idempotent helpflow_chunks + payload indexes
backend/prompts/guardrails.md         # canned injection refusal
sql/001_schema.sql                    # tenants, sources, conversations, messages, escalations, events
sql/002_views_rls.sql                 # v_conversations, v_funnel, v_gaps, v_events + RLS
scripts/apply-sql.sh                  # idempotent psql runner against Supabase
scripts/export-workflows.mjs          # n8n REST → strip ids/creds → workflows/*.json (port LeadFlow)
.env.example                          # every env var from ARCHITECTURE §9, blank
requirements.txt  Dockerfile  README.md (stub)  CLAUDE.md (already written — keep in sync)
backend/tests/ (config, guardrails, health, schema-shape)
workflows/.gitkeep  snippets/.gitkeep  widget/.gitkeep  console/.gitkeep
```
Plus UI-only infra actions delivered as numbered checklists: FastAPI Railway service, n8n
Railway service (Supabase-backed, schema `n8n`), Qdrant collection confirm, Supabase project,
Slack workspace + incoming webhook, Gmail alert account.

## Requirements
1. **Config**: every model id, key, url, limit, threshold from ARCHITECTURE §4/§7/§9 is a
   typed setting in `config.py` read from env with a sane default; service code imports
   `settings`, never calls `os.getenv`, never contains a model string. Port DocChat's
   `config.py` and extend with: `SUPABASE_URL/KEY`, `ADMIN_TOKEN`, `HANDOFF_TOKEN`,
   `N8N_HANDOFF_URL`, `RELEVANCE_THRESHOLD`, `MAX_PAGES`, `SENSITIVE_INTENTS`, rate limits.
2. **Ported utils** (read the DocChat originals first, adapt — strip PDF/session specifics,
   keep the engineering): `llm_router` (failover chain + semaphore + retries owned by the
   Router, never a manual retry loop), `guardrails`, `sse` (framing, 15s heartbeat, seq ids,
   `guard_stream` output rail), `embeddings` (batches of 100). New: `supabase_client`
   (service-role, server-only), `redis_client` (`hf:` prefix).
3. **Qdrant**: `create_collection.py` idempotently creates `helpflow_chunks` (768, cosine)
   with payload indexes on `tenant_id`, `source_id`, `created_at`. Called on startup too.
4. **Supabase schema exactly per ARCHITECTURE §5.2**: tables tenants/sources/conversations/
   messages/escalations/events; `conversations.status` CHECK with EXACTLY the enum
   `ai_handling, needs_human, human_assigned, resolved, abandoned`; `UNIQUE (tenant_id,
   channel, external_ref)` on conversations; `updated_at` trigger; indexes on
   conversations(tenant_id, status), messages(conversation_id), events(conversation_id).
5. **RLS + views per §5.3**: RLS on all base tables, no anon policy on base tables. Views
   granted to anon: `v_conversations` (customer_email masked `j***@x.com`, no raw bodies
   beyond a last-message preview), `v_funnel` (per-tenant status counts + deflection rate),
   `v_gaps` (low_relevance escalations; clustering added in E6 — E1 ships the base view),
   `v_events` (recent activity). Views must be tenant-filterable (accept a tenant_id arg /
   filter column the console passes). Service-role bypasses RLS.
6. **Health**: `GET /health` pings Qdrant, Supabase, Redis, and does a cheap LLM router
   liveness check; returns `{status, qdrant, supabase, redis, llm}` with per-dependency
   ok/degraded — never 500s (a down dependency shows degraded).
7. **n8n on Railway**: `n8nio/n8n` image, DB = Supabase session pooler schema `n8n`,
   `N8N_ENCRYPTION_KEY` generated + saved to the password manager, `WEBHOOK_URL` = Railway
   domain, editor basic auth on, survives redeploy (state in Supabase). `export-workflows.mjs`
   deterministic (sorted keys, ids/creds stripped) — ported from LeadFlow.
8. All env in `.env.example` with a one-line comment each; zero secrets in the repo.

## Acceptance criteria
- `uvicorn` boots; `GET /health` returns 200 with every dependency `ok` against real
  services; killing one dependency shows it `degraded`, not a 500.
- `apply-sql.sh` runs clean twice (idempotent). Inserting a conversation with
  `status='bogus'` fails the CHECK; a duplicate `(tenant_id, channel, external_ref)` fails.
- With the anon key: selecting `v_conversations` works and shows masked emails; selecting
  `conversations` directly returns zero rows / permission denied.
- `create_collection.py` run twice → collection exists once with the three payload indexes.
- n8n editor reachable over HTTPS with basic auth; a scratch workflow survives a redeploy;
  `export-workflows.mjs` second run → empty git diff.

## Required tests
- config: a missing required env fails fast with a clear message; defaults populate.
- guardrails: known injection strings flagged; benign support questions pass.
- health: mocked-down dependency → `degraded` in the payload, still 200.
- schema: a psql assertion script (committed) proving the CHECK, UNIQUE, and RLS behaviors;
  paste its transcript in the session summary.
- Zero secrets: grep for `sk-`, `eyJ`, `client_secret` before committing.
