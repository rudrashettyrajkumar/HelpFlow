# Runbook — deploy, ops, and going live

E10's deliverable: turn the built system into production URLs, keep them healthy, and
prove the whole loop works. Read `CLAUDE.md`'s hard constraints before touching any of
this — the two that bite hardest are **never `railway up` from `/mnt/d`** (drvfs
corrupts files mid-upload — this happened once on DocChat) and **demo mode only ever
serves free-tier open-source models**.

Everything here is a numbered checklist for the parts that are dashboard-only. Where a
command exists, it's given verbatim.

---

## 0. Prerequisites

- [ ] Railway account with the existing FastAPI + n8n services (stood up in E1/E6)
- [ ] Supabase project (schema `public` + `n8n`), Qdrant Cloud cluster, Upstash Redis —
      all already live from E1–E6
- [ ] Cloudflare account (Pages), Vercel account
- [ ] Groq + OpenRouter API keys (Raj's demo-mode keys)
- [ ] UptimeRobot account (free tier)
- [ ] `railway` CLI logged in (`railway login`), `node`/`npm`, `psql` on PATH

---

## 1. FastAPI on Railway — the git-archive recipe

**NEVER run `railway up` from `/mnt/d/PortfolioProjects/HelpFlow`.** The repo lives on
a Windows drive mounted into WSL (`drvfs`), and `railway up`'s upload walks the tree in
a way that has corrupted files mid-transfer before (DocChat's incident, documented in
its own runbook). The fix is always the same: archive the exact committed tree, extract
it onto the native Linux filesystem, deploy from there.

1. From `/mnt/d/PortfolioProjects/HelpFlow` (any directory is fine for `git archive` —
   it only reads the git object store, this step alone is safe on drvfs):
   ```bash
   mkdir -p /tmp/helpflow-deploy
   git archive HEAD | tar -x -C /tmp/helpflow-deploy
   ```
2. `cd /tmp/helpflow-deploy` — from here on, every command runs on native ext4, not
   drvfs.
3. `railway link` (select the existing FastAPI service if not already linked in this
   shell) then `railway up`.
4. Watch the build log for the `pip install -r requirements.txt` step to finish clean —
   the `langchain-*`/`langgraph`/`flashrank` stack is the slow part (~2–3 min).
5. Once deployed, `railway logs` and confirm `Application startup complete` with no
   traceback (the create_collection startup call should log once, idempotently).
6. `rm -rf /tmp/helpflow-deploy` when done — it's a disposable snapshot, re-cut it every
   deploy rather than reusing a stale one.

### 1.1 Set the FastAPI environment (Railway → service → Variables)

Every var from `.env.example` with `ENV=prod` (fails fast on any missing required key —
that's the point, it catches a forgotten var at boot instead of at first request).
**v2 additions to double-check** (these are the ones a v1-era Railway service won't
already have):

```
DEMO_REWRITER_MODEL=groq/llama-3.3-70b-versatile
DEMO_ANSWERER_MODEL=groq/llama-3.3-70b-versatile
DEMO_EMBED_MODEL=openrouter/nvidia/llama-nemotron-embed-vl-1b-v2:free
DEMO_CHAT_DAILY=150
DEMO_EMBED_DAILY=100
JWT_SECRET=<openssl rand -hex 32>
JWT_TTL_DAYS=7
RAJ_LINKEDIN_URL=<your profile>
RAJ_WHATSAPP_URL=https://wa.me/<your number, no +>
RAJ_EMAIL=<your contact email>
LEAD_TOKEN=<openssl rand -hex 24>
N8N_PREMIUM_LEAD_URL=<n8n Railway URL, no trailing slash>
PREMIUM_CONTACT_DAILY_PER_IP=3
MAX_TRIAL_PAGES=25
TRIAL_MESSAGES_DAILY=40
```

Plus the pre-existing `OPENROUTER_API_KEY`, `GROQ_API_KEY`, `QDRANT_URL`,
`QDRANT_API_KEY`, `SUPABASE_DB_URL`, `SUPABASE_URL`, `SUPABASE_ANON_KEY`,
`SUPABASE_SERVICE_KEY`, `UPSTASH_URL`, `UPSTASH_TOKEN`, `ADMIN_TOKEN`, `HANDOFF_TOKEN`,
`N8N_HANDOFF_URL`, and set `FRONTEND_ORIGIN` to the **exact** widget + portal origins
(§6 below) — never `*` in prod.

### 1.2 Verify SSE actually streams through the Railway proxy

Railway's edge occasionally buffers responses unless the app is explicit. Confirm with
a real streamed chat:
```bash
curl -N -X POST https://<fastapi-railway-url>/chat/stream \
  -H 'Content-Type: application/json' -H 'X-Widget-Key: <demo tenant id>' \
  -d '{"conversation_id": null, "message": "What do you offer?"}'
```
You should see `event: token` lines arrive incrementally, not all at once at the end.
Do the same for `GET /chat/subscribe?conversation_id=<id>` (open it, then send an agent
reply from the console in another tab — the subscribe stream should push it live).

---

## 2. n8n on Railway

1. Confirm the n8n service is on the same Railway project (already live since E6).
2. n8n editor → **Import from File** → import, in order: `workflows/wf-handoff.json`,
   `workflows/wf-premium-lead.json`, `workflows/wf-ops.json`.
3. Reconnect credentials on every imported node — imports strip credential ids
   (`export-workflows.mjs`'s `NODE_DROP`), so each Postgres/Slack/Gmail node needs its
   credential re-selected by NAME: `supabase-pg`, `slack`, `gmail-alerts`.
4. **Postgres credential (`supabase-pg`)**: host = Supabase session pooler, **"Ignore
   SSL Issues" must be ON** — Supabase's pooler cert isn't in n8n's default trust store,
   and without this it fails as a misleading "password authentication failed" instead of
   an SSL error.
5. **Publish** each workflow (the "Active" toggle is now labeled "Publish" in current
   n8n) — WF-H, WF-P, and **WF-O** all need to be Published, not just saved.
6. Confirm `N8N_BLOCK_ENV_ACCESS_IN_NODE=false` is set on the n8n Railway service —
   without it every `$env.X` reference in a Code/expression node throws "access to env
   vars denied", which silently breaks every workflow at runtime, not import time.
7. Set n8n's `$env` (Railway → n8n service → Variables) — full list, v2 additions
   marked ★:
   ```
   HANDOFF_TOKEN=<same value as FastAPI's HANDOFF_TOKEN>
   LEAD_TOKEN=<same value as FastAPI's LEAD_TOKEN>              ★
   SLACK_CHANNEL=<#channel-id, not the name>
   ONCALL_EMAIL=<your alert inbox>
   BUSINESS_HOURS=MON-FRI 09:00-18:00
   BUSINESS_TZ=Asia/Kolkata
   CONSOLE_BASE_URL=<portal Vercel URL>
   RAJ_WHATSAPP_URL=https://wa.me/<your number>                 ★
   SLA_MINUTES=30                                                ★ E10 — WF-O re-alert threshold
   ABANDON_HOURS=6                                               ★ E10 — WF-O off-hours abandon threshold
   ```
8. **Webhook path gotcha**: n8n auto-prepends `webhook/` to a Webhook node's `path`
   parameter — a node configured with `path: "webhook/handoff"` registers at
   `/webhook/webhook/handoff`, not `/webhook/handoff`. All three workflows in this repo
   already use bare paths (`handoff`, `premium-lead`, `health`) — if you ever hand-edit a
   node in the n8n UI, don't add the prefix back.
9. Note the n8n Railway URL — needed for `N8N_HANDOFF_URL`/`N8N_PREMIUM_LEAD_URL` (step
   1.1) and for UptimeRobot (§7).

---

## 3. Widget → Cloudflare Pages

1. Cloudflare dashboard → Pages → **Create a project** → Connect to Git → this repo.
2. Build settings: root directory `widget/`, build command `npm run build`, output
   directory `dist`.
3. Environment variable: `VITE_API_URL=https://<fastapi-railway-url>`.
4. Deploy. Note the `*.pages.dev` URL (or attach a custom domain).
5. Verify `demo.html` loads and the loader script (`<script data-key>`) boots the
   iframe bubble against the live FastAPI URL — open it, send a message, confirm tokens
   stream in.

---

## 4. Portal → Vercel

1. Vercel dashboard → **Add New Project** → import this repo, root directory `portal/`.
2. Framework preset: Next.js (auto-detected). Environment variables:
   ```
   NEXT_PUBLIC_API_URL=https://<fastapi-railway-url>
   NEXT_PUBLIC_WIDGET_URL=https://<widget-cloudflare-pages-url>
   NEXT_PUBLIC_DEMO_TENANT_WIDGET_KEY=<demo tenant id — §5>
   NEXT_PUBLIC_SUPABASE_URL=<same as SUPABASE_URL>
   NEXT_PUBLIC_SUPABASE_ANON_KEY=<same as SUPABASE_ANON_KEY>
   NEXT_PUBLIC_RAJ_NAME=Raj
   NEXT_PUBLIC_RAJ_LINKEDIN_URL=<same as RAJ_LINKEDIN_URL>
   NEXT_PUBLIC_RAJ_WHATSAPP_URL=<same as RAJ_WHATSAPP_URL>
   NEXT_PUBLIC_RAJ_EMAIL=<same as RAJ_EMAIL>
   ```
3. Deploy. Note the `*.vercel.app` URL (or attach a custom domain).
4. This is also `CONSOLE_BASE_URL` for n8n's `$env` (§2.7) — go back and set it if the
   n8n workflows were imported before this URL existed.

---

## 5. Lock CORS, seed the demo tenant

1. Railway → FastAPI service → set `FRONTEND_ORIGIN` to the exact comma-separated
   origins: `https://<widget>.pages.dev,https://<portal>.vercel.app` (plus any custom
   domains). No `*` in prod — the widget/portal cross-origin key resolution (§4.4) only
   needs to work from these two origins.
2. Restart the FastAPI service so the new `FRONTEND_ORIGIN` takes effect.
3. Seed (or confirm) the demo tenant:
   ```bash
   ADMIN_TOKEN=<...> SUPABASE_DB_URL=<...> QDRANT_URL=<...> QDRANT_API_KEY=<...> \
     python -m backend.scripts.seed_demo_tenant
   ```
4. Copy the printed demo tenant id into `NEXT_PUBLIC_DEMO_TENANT_WIDGET_KEY` (§4.2) and
   redeploy the portal.
5. Open the portal landing page — confirm the live embedded widget answers a real
   question about the seeded demo content, cited.
6. Open `widget/public/demo.html` on Cloudflare Pages directly too — same check,
   standalone host.

---

## 6. UptimeRobot

1. New Monitor → HTTP(s) → `https://<fastapi-railway-url>/health` → interval 5 min →
   alert contact = your on-call email.
2. New Monitor → HTTP(s) → `https://<n8n-railway-url>/webhook/health` → interval 5 min
   → same alert contact.
3. Confirm both show green within one polling cycle. `/health` degrades (still 200) if
   one dependency is down — UptimeRobot only pages on a non-2xx, so a `degraded` status
   won't page; check the JSON body periodically or add a keyword monitor on `"status":
   "ok"` if you want paging on partial degradation too.

---

## 7. WF-O verification (spec E10 acceptance)

**Forced stale-escalation re-alert (fires ONCE):**
1. Trigger a real escalation (ask the demo widget something off-topic, or something
   containing a sensitive intent like "I want a refund").
2. In Supabase, backdate it past the SLA window so the sweep sees it as stale:
   ```sql
   update escalations set notified_at = now() - interval '31 minutes'
    where conversation_id = '<id>' and status = 'notified';
   ```
3. In the n8n editor, manually execute WF-O's "Schedule Hourly Sweep" trigger (or wait
   for the hour). Confirm exactly one `:hourglass_flowing_sand: SLA breach` Slack
   message arrives.
4. Re-run the sweep again (manual execute) without changing anything. Confirm **no
   second** Slack message — `events_sla_realert_escalation_uniq` (sql/006) blocked the
   duplicate `INSERT ... ON CONFLICT DO NOTHING`, so `Mark Realert Once` returned zero
   rows and the Slack node never ran a second time.
5. Paste both the SQL backdate + the two sweep-execution event log rows:
   ```sql
   select type, detail, created_at from events
    where detail->>'escalation_id' = '<escalation id>' order by created_at;
   ```

**Idle off-hours → abandoned (WF-O only writer):**
1. Get a conversation into `needs_human` with no `customer_email` captured.
2. Backdate `last_activity_at` past `ABANDON_HOURS`:
   ```sql
   update conversations set last_activity_at = now() - interval '7 hours'
    where id = '<conversation id>';
   ```
3. Run the sweep during an off-hours window (or temporarily set `BUSINESS_HOURS` to a
   window that excludes now, run the sweep, then set it back).
4. Confirm `conversations.status = 'abandoned'` and an `events` row
   `{type: 'abandoned', detail: {by: 'wf-o', ...}}` exists. Confirm it does **NOT**
   abandon during business hours (re-run with `BUSINESS_HOURS` covering now — status
   stays `needs_human`).

**Daily digest (real numbers, incl. demo budget + leads):**
1. Manually execute WF-O's "Schedule Daily Digest" trigger once.
2. Confirm the Slack message shows: per-tenant deflection %, 24h conversation volume,
   open escalation count, top gap themes (if `gap_clusters` has rows) — AND the v2 ops
   lines: trial signups in 24h, premium leads (24h + all-time), and today's demo-budget
   usage (`hf:demo:{today}:chat` / `:embed` vs. `DEMO_CHAT_DAILY`/`DEMO_EMBED_DAILY`).
3. Re-execute immediately. Confirm **no second** Slack/Gmail message —
   `events_digest_sent_date_uniq` (sql/006) blocks the duplicate `Claim Digest Marker`
   insert, so nothing downstream runs twice for the same UTC date.
4. Paste the digest Slack text + the two `Claim Digest Marker` attempts (first succeeds
   with a returned row, second returns zero rows).

---

## 8. check-sync — prove no drift

```bash
node scripts/check-sync.mjs                 # expect exit 0, every marker "ok"
```
To prove the check actually catches something (don't skip this — an untested test is
worth nothing): open any workflow JSON, hand-edit one Code node's `jsCode` (add a
character), save, re-run `check-sync.mjs` — expect exit 1 with a `DRIFT` line naming the
exact node. Revert (`git checkout -- workflows/<file>.json`), re-run — expect exit 0
again. Paste all three exit codes in the spec-check evidence.

---

## 9. Secret sweep

```bash
grep -rnE "sk-[a-zA-Z0-9]{10,}|gsk_[a-zA-Z0-9]{10,}|eyJ[a-zA-Z0-9_-]{10,}|client_secret[\"' :=]+[a-zA-Z0-9]{8,}|xox[baprs]-[a-zA-Z0-9-]{8,}" \
  --exclude-dir=node_modules --exclude-dir=.next --exclude-dir=dist --exclude-dir=__pycache__ --exclude-dir=.git \
  -r . | grep -v '\.env\.example'
```
Expect empty output. Confirm every var in `.env.example` has a trailing comment
(`awk '/^[A-Z_]+=/{if (index($0,"#")==0) print}' .env.example` — expect empty).

---

## 10. GitHub Actions keepalive secrets

Repo → Settings → Secrets and variables → Actions → add: `QDRANT_URL`,
`QDRANT_API_KEY`, `SUPABASE_DB_URL`, `FASTAPI_BASE_URL`, `N8N_BASE_URL`. Trigger
`.github/workflows/keepalive.yml` once manually (`workflow_dispatch`) to confirm it
runs green before relying on the daily schedule.

---

## 11. Both full production traces (spec E10 acceptance — paste both when done)

**Loop A — grounded-or-handoff:**
question on the live widget → low-relevance/sensitive answer escalates → Slack + Gmail
ping → claim in the console → live reply appears in the widget → resolve in the
console. Screenshot or paste each step's timestamp from `events`.

**Loop B — v2 self-serve/BYOK:**
register on the portal → wizard (name + URL → crawl SSE completes) → Model Studio (add
a real Groq or OpenRouter key, see "key works ✓") → chat over the new workspace with
that key (confirm `X-LLM-*` headers, not demo mode) → create a 2nd, then a 3rd workspace
→ premium gate appears → submit the contact form → Slack DM + Gmail land for Raj with
the lead.

---

## 12. Escalation → takeover GIF — exact capture steps

For the README hero + CASE-STUDY. Record at 2x speed max (the point is legibility, not
padding runtime) — 15–25 seconds is the right length.

1. Open the portal landing page, live demo widget visible.
2. Type a question that forces escalation — e.g. "I want a refund" (sensitive intent,
   deterministic escalate, no waiting on a low-relevance roll).
3. Let the widget show the warm handoff message + the "talk to a human" state.
4. Cut to a Slack window already open to the alert channel — show the
   `:rotating_light: Escalation` message landing (timestamp visible).
5. Cut to the console inbox — click the conversation, click **Claim**.
6. Type a human reply in the console's reply box, send it.
7. Cut back to the widget — show the reply arriving live + the "A human joined" banner.
8. Click **Resolve** in the console. End on the resolved state.

Export as GIF (or MP4 + convert), keep under ~5MB for the README to render inline on
GitHub.

---

## Troubleshooting (n8n + Railway + Supabase gotchas)

- **"password authentication failed" on the Postgres credential** — it's actually a
  missing SSL setting, not a bad password. Turn on "Ignore SSL Issues" on the
  `supabase-pg` credential (§2.4).
- **`$env.X` throws "access to env vars denied"** — set
  `N8N_BLOCK_ENV_ACCESS_IN_NODE=false` on the n8n Railway service (§2.6).
- **A webhook 404s** — check the node's `path` doesn't have a redundant `webhook/`
  prefix (§2.8); check the workflow is Published, not just saved (§2.5).
- **A Set node's `headers`/`body` silently vanish downstream** — `includeOtherFields`
  is a top-level parameter on the Set node, not nested under `options`; wrong placement
  drops the rest of the payload with no error.
- **`railway up` corrupted files / deploy behaves like stale code** — you ran it from
  `/mnt/d`. Stop, re-cut with the git-archive recipe (§1), redeploy from `/tmp`.
- **SSE looks buffered (tokens arrive all at once)** — check Railway's proxy isn't
  buffering; confirm the FastAPI response sets `Cache-Control: no-cache` and isn't
  gzip-compressed (compression buffers chunked responses). Re-test with `curl -N`
  (§1.2) before suspecting the frontend.
- **Cross-project collision**: this Railway n8n instance is shared with LeadFlow.
  HelpFlow owns `/webhook/handoff`, `/webhook/premium-lead`, `/webhook/health`, and (E11)
  `/webhook/whatsapp` + `/webhook/agent-outbound`. If LeadFlow's own premium-lead-notify
  workflow lands on the same instance, it must use a different path — check before
  importing anything new.
