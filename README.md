# HelpFlow

An AI customer-support agent trained on a business's own website: it crawls the
site, answers customer questions **with citations**, knows when it doesn't know,
and **hands off to a human** instead of guessing — on a web chat widget and
(optionally) WhatsApp. A human takes over the live conversation from an agent
inbox; an owner dashboard shows the deflection rate and a "gap report" of
questions the docs didn't cover.

Portfolio project #3 (the capstone). It deliberately **fuses** two earlier
projects: DocChat's FastAPI RAG brain and LeadFlow's n8n orchestration +
Supabase stage machine. See `docs/ARCHITECTURE.md` for the full design.

> **Status:** early build — E1 (Foundation) only. Ingestion, the answer/escalation
> pipeline, the widget, the console, and handoff orchestration land in E2–E7.

## Architecture at a glance

Two backends, one thin webhook boundary (ARCHITECTURE §2):

- **FastAPI brain** (`backend/`) — RAG, streaming grounded answers, the
  escalation *decision*, and the conversation store. Anything real-time or
  transactional.
- **n8n nervous system** (`workflows/`, `snippets/`) — human-agent alerts,
  business hours, SLA timers, WhatsApp, the daily digest. Anything "when X,
  notify/route".

Stores: Qdrant (vectors, tenant-filtered) · Supabase Postgres (conversations,
the stage machine, RLS masked views) · Upstash Redis (`hf:` rate limits + dedup).
Models via LiteLLM Router (OpenRouter → Groq). No LangChain / agent frameworks.

## Backend — local dev

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # fill in the blanks

uvicorn backend.main:app --reload      # → http://localhost:8000/health
pytest                                 # unit tests (external services mocked)
ruff check .

python -m backend.scripts.create_collection            # idempotent Qdrant setup
SUPABASE_DB_URL=... scripts/apply-sql.sh --assert       # schema + views + RLS + assertions
```

## Repository layout

```
backend/    FastAPI brain (utils, api, middleware, scripts, prompts, tests)
sql/        001_schema.sql · 002_views_rls.sql · assert_schema.sql
scripts/    apply-sql.sh · export-workflows.mjs
workflows/  canonical n8n exports (E4+)      snippets/ n8n Code-node JS (E4+)
widget/     embeddable chat bubble (E5)      console/  agent inbox + analytics (E6)
docs/       ARCHITECTURE.md · BUILD-PROMPTS.md · specs/
```

Built by Raj — freelance AI/automation engineer.
