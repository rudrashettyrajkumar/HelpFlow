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

**New in v2 (design):** HelpFlow is self-serve + **bring-your-own-key** — try it on a
demo mode (shared free-tier keys, honest when the day's budget runs out), a free BYOK
tier (your own Groq / OpenRouter key, curated open-source models like NVIDIA Nemotron 3),
or a paid BYOK tier (your OpenRouter / OpenAI / Gemini / Anthropic key). Keys never leave
your browser. Two trial workspaces per account; want more → talk to Raj.

> **Status:** E1 (Foundation), E2 (Ingestion), E3 (Answer + escalation) built to the v1
> design. Next: E4 retrofits the LLM layer to LangChain + LangGraph + BYOK, then
> accounts/trials (E5), n8n orchestration (E6), widget (E7), portal + Model Studio (E8),
> console (E9), ship (E10).

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
Models: **LangChain + LangGraph** BYOK layer (Groq / OpenRouter / OpenAI / Gemini /
Anthropic — the user's key via per-request headers, never stored) with a free-tier
demo mode (Groq Llama 3.3 70B ↔ OpenRouter Nemotron `:free`, NVIDIA Nemotron embeddings).

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
workflows/  canonical n8n exports (E6+)      snippets/ n8n Code-node JS (E6+)
widget/     embeddable chat bubble (E7)      portal/   landing + Model Studio + console (E8/E9)
docs/       ARCHITECTURE.md · BUILD-PROMPTS.md · specs/
```

Built by Raj — freelance AI/automation engineer.
