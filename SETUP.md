# Setup — run HelpFlow locally and see the UI

This gets you a working local stack — backend, widget, and portal, all talking to real
(free-tier) cloud stores — with a seeded demo tenant you can actually chat with. No
Railway/Vercel/Cloudflare account needed for this; those are only for the production
deploy (`docs/runbook.md`).

**n8n is skipped entirely here.** It only handles Slack/Gmail alerts and the SLA/digest
cron — none of that blocks seeing or using the product UI. If `N8N_HANDOFF_URL`/
`N8N_PREMIUM_LEAD_URL` are left blank, FastAPI just skips the notify call and moves on
(this is the "degrade, never break" invariant, not a bug). Set up n8n later, via
`docs/runbook.md` §2, once you want the Slack pings too.

Time estimate: ~20 minutes, most of it waiting on free-tier signups.

---

## 1. Create four free accounts (no credit card on any of them)

| Service | What it's for | Sign up |
|---|---|---|
| **Supabase** | Postgres — conversations, users, escalations | https://supabase.com |
| **Qdrant Cloud** | Vector store — the crawled site's content | https://cloud.qdrant.io |
| **Upstash** | Redis — rate limits, demo budget counters | https://upstash.com |
| **Groq** | Free-tier chat model for demo mode | https://console.groq.com |
| **OpenRouter** | Free-tier fallback + embeddings | https://openrouter.ai |

For each:

1. **Supabase** → New project → wait for it to provision → Settings → Database → copy
   the **Session pooler** connection string (`SUPABASE_DB_URL` — NOT the direct
   connection, it's IPv6-only on the free tier and won't work here) → Settings → API →
   copy the Project URL (`SUPABASE_URL`) and the `anon` `public` key
   (`SUPABASE_ANON_KEY`) and the `service_role` key (`SUPABASE_SERVICE_KEY`).
2. **Qdrant Cloud** → Create cluster (free tier, any region) → copy the cluster URL
   (`QDRANT_URL`) and API key (`QDRANT_API_KEY`).
3. **Upstash** → Create Redis database → REST API tab → copy `UPSTASH_REDIS_REST_URL`
   (→ `UPSTASH_URL`) and `UPSTASH_REDIS_REST_TOKEN` (→ `UPSTASH_TOKEN`).
4. **Groq** → API Keys → Create → copy it (`GROQ_API_KEY`).
5. **OpenRouter** → Keys → Create → copy it (`OPENROUTER_API_KEY`).

---

## 2. Configure the backend

```bash
cd /mnt/d/PortfolioProjects/HelpFlow

# IMPORTANT: build the venv on the native Linux filesystem, not /mnt/d — pip
# installing this dependency set (langchain/langgraph/flashrank) straight onto
# a Windows-mounted drive via WSL is pathologically slow (CLAUDE.md).
python3 -m venv /home/raj/.venvs/helpflow
source /home/raj/.venvs/helpflow/bin/activate
pip install -r requirements.txt

cp .env.example .env
```

Edit `.env` and fill in:

```
ENV=dev
FRONTEND_ORIGIN=*

OPENROUTER_API_KEY=<from step 1>
GROQ_API_KEY=<from step 1>

QDRANT_URL=<from step 1>
QDRANT_API_KEY=<from step 1>

SUPABASE_DB_URL=<session pooler string, from step 1>
SUPABASE_URL=<from step 1>
SUPABASE_ANON_KEY=<from step 1>
SUPABASE_SERVICE_KEY=<from step 1>

UPSTASH_URL=<from step 1>
UPSTASH_TOKEN=<from step 1>

ADMIN_TOKEN=<openssl rand -hex 24>
JWT_SECRET=<openssl rand -hex 32>

RAJ_LINKEDIN_URL=<your profile, or leave blank for now>
RAJ_WHATSAPP_URL=<your wa.me link, or leave blank for now>
RAJ_EMAIL=<your email, or leave blank for now>
```

Leave `HANDOFF_TOKEN`, `N8N_HANDOFF_URL`, `LEAD_TOKEN`, `N8N_PREMIUM_LEAD_URL` blank —
that's the n8n-skip mentioned above. Everything else already has a working default in
`.env.example`.

Generate the two random secrets:
```bash
openssl rand -hex 24   # → ADMIN_TOKEN
openssl rand -hex 32   # → JWT_SECRET
```

---

## 3. Set up the database and vector collection

```bash
SUPABASE_DB_URL="<same value as .env>" scripts/apply-sql.sh --assert
python -m backend.scripts.create_collection
```

The first command applies all six migrations and runs the assertion scripts (schema
shape, RLS, users/trials, events idempotency) — expect `== done ==` with no errors. The
second idempotently creates the `helpflow_chunks` Qdrant collection with its payload
indexes.

---

## 4. Seed a demo tenant with real content (the "sample data" to test against)

```bash
python -m backend.scripts.seed_demo_tenant \
  --name "HelpFlow Demo" \
  --url https://docs.python.org/3/tutorial/ \
  --max-pages 8
```

This crawls a real public docs site (small and crawl-friendly — already smoke-tested
during this project's own build: 8 pages → ~1,000 chunks, no failures) and prints:

```
tenant_id=<uuid> name='HelpFlow Demo' url=https://docs.python.org/3/tutorial/ pages=8 chunks=~1080
```

**Copy that `tenant_id` — you'll need it as the widget key in the next two steps.**
Swap the `--url` for your own site (or any small public docs site) if you'd rather test
against something else; `--max-pages` caps how much it crawls.

---

## 5. Start the backend

```bash
uvicorn backend.main:app --reload
```

Confirm it's healthy: open http://localhost:8000/health — expect
`{"status": "ok", "qdrant": "ok", "supabase": "ok", "redis": "ok", "llm": "ok"}`. If
anything shows `"down"`, recheck that credential in `.env` before moving on.

---

## 6. Start the widget — see it answer questions

```bash
cd widget
cp .env.example .env         # VITE_API_URL=http://localhost:8000 is already the default
npm install
npm run dev
```

Open **`http://localhost:5173/demo.html?key=<tenant_id from step 4>`**.

Try:
- **A real question** — e.g. "What is a list comprehension?" → watch tokens stream in,
  then click the citation chip to see the source page it came from.
- **An escalation** — type "I want a refund" → watch it decline to guess and hand off,
  instead of making up a policy. (No Slack ping without n8n, but the conversation is
  now sitting in Postgres as `needs_human` — see it in the console in step 7.)

---

## 7. Start the portal — the full self-serve flow

```bash
cd portal
cp .env.example .env
npm install
```

Edit `portal/.env`:
```
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_WIDGET_URL=http://localhost:5173
NEXT_PUBLIC_DEMO_TENANT_WIDGET_KEY=<tenant_id from step 4>
NEXT_PUBLIC_SUPABASE_URL=<same as backend's SUPABASE_URL>
NEXT_PUBLIC_SUPABASE_ANON_KEY=<same as backend's SUPABASE_ANON_KEY>
NEXT_PUBLIC_RAJ_NAME=Raj
NEXT_PUBLIC_RAJ_LINKEDIN_URL=<same as .env, or blank>
NEXT_PUBLIC_RAJ_WHATSAPP_URL=<same as .env, or blank>
NEXT_PUBLIC_RAJ_EMAIL=<same as .env, or blank>
```

```bash
npm run dev
```

Open **`http://localhost:3000`**. Walk the whole product:

1. **Landing page** — the live widget in the hero is chatting with the demo tenant from
   step 4 automatically.
2. **Register** — create an account.
3. **Wizard** (`New workspace`) — paste a small site URL (or the same Python docs URL),
   watch the live SSE crawl progress (discovering → fetching → embedding → ready).
4. **Model Studio** (inside the wizard, or `/app/studio`) — paste your real Groq or
   OpenRouter key, click test, watch it show "key works ✓", select the model.
5. **Chat** over your new workspace — now on your own key, not the shared demo budget.
6. **Console** (`/app/inbox`) — the refund-escalation conversation from step 6 (and any
   new ones) shows up here. Claim it, type a reply, send it — then flip back to the
   widget tab and watch the reply arrive live.
7. **Analytics / Gap Report** (`/app/analytics`) — deflection rate, volume, and the
   themed "questions your docs don't answer" report (needs a few escalations first to
   have something to cluster — run `python -m backend.scripts.cluster_gaps` after a few
   escalations to populate it).
8. **Trial gate** — create a 3rd workspace to see the premium-gate screen (LinkedIn/
   WhatsApp/email + the lead form — submitting it writes a row to `premium_leads` even
   without n8n; you just won't get the Slack ping until n8n is set up).

---

## 8. Sanity checks (optional but recommended before touching anything)

```bash
pytest                # 274 tests, external services mocked — should be all green
ruff check .           # should be clean
cd widget && npm run lint && npm run build
cd ../portal && npm run lint && npm run build
```

---

## Troubleshooting

- **`/health` shows `"supabase": "down"`** — double check you used the **session
  pooler** connection string, not the direct one (Supabase free tier's direct host is
  IPv6-only and usually unreachable from WSL).
- **pip install hangs/crawls for minutes** — you're installing into a venv on `/mnt/d`.
  Recreate it at `/home/raj/.venvs/helpflow` (step 2) instead.
- **Widget shows "connection error"** — check `widget/.env`'s `VITE_API_URL` matches
  where `uvicorn` is actually listening, and that `FRONTEND_ORIGIN=*` is still set in
  the backend `.env` (fine for local dev; never in prod — see `docs/runbook.md` §5).
- **Crawl gets 0 pages** — some sites block bots at the network edge; try a different
  small public docs site, or lower `--max-pages` and check the error `detail` printed
  by `seed_demo_tenant.py`.
- **Gap Report is empty** — it's a batch job, not real-time. Generate a couple of
  escalations first, then run `python -m backend.scripts.cluster_gaps`.

---

Once you're happy with the local walkthrough, `docs/runbook.md` has the numbered
checklist for taking this to production (Railway/Vercel/Cloudflare/n8n/UptimeRobot).
