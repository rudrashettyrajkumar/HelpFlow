# SPEC E5 — Accounts, self-serve workspaces, trial gate & premium leads

**Epic:** E5 · **Depends on:** E4 · **Architecture refs:** §3.0, §5.2, §5.3, §5.5, §6, §7.1

## Objective
Turn HelpFlow from seeded-tenants-only into a self-serve product: email/password accounts,
"create a workspace" (= tenant) with a server-enforced **2-trial limit**, trial caps,
JWT-scoped ownership of admin/console routes, and the **premium gate** — a contact-Raj
flow whose submissions land in `premium_leads` and fire the n8n WF-P webhook (built in
E6). After this epic any visitor can register, crawl a site, chat over it, hit the gate on
workspace #3, and Raj gets a lead.

## Port, don't reinvent
DocChat v2's self-contained auth, adapted from Upstash to Supabase Postgres:
`/mnt/d/PortfolioProjects/DocChat/backend/utils/security.py` (stdlib PBKDF2-HMAC-SHA256 —
no bcrypt/passlib dep), `services/users.py`, `middleware/jwt_auth.py`, `api/auth.py`
(register/login/me), HS256 JWT via python-jose (`JWT_SECRET`, `JWT_TTL_DAYS=7`, both
REQUIRED_IN_PROD). The guarded-UPDATE pattern for the trial counter is LeadFlow/E1 DNA.

## Deliverables
```
sql/003_users_trials.sql             # users · premium_leads · tenants + owner_user_id/plan (ADDITIVE)
backend/utils/security.py            # PBKDF2 hash/verify + JWT mint/decode
backend/services/users.py            # register/login/get, asyncpg
backend/services/trials.py           # atomic trial increment + gate payload
backend/middleware/jwt_auth.py       # Bearer → user_id dependency
backend/api/auth.py                  # POST register/login · GET me
backend/api/workspaces.py            # POST/GET/DELETE /api/workspaces
backend/api/premium.py               # POST /api/premium-contact
backend/prompts/trial_limit.md       # the premium-gate copy (§6)
```

## Requirements
1. **Schema** (`003_users_trials.sql`, additive-only — 001/002 untouched): the §5.2
   tables. RLS ON with no anon policy for `users`/`premium_leads` (service-role only).
   Update `scripts/apply-sql.sh --assert` to cover the new tables.
2. **Auth**: register (email format + password ≥8; citext unique → 409), login (constant
   -time verify), `GET /api/auth/me` → `{user, trials_used, workspaces[]}`. Never store or
   log plaintext passwords; JWT carries only `sub` + `exp`.
3. **Workspace create** (`POST /api/workspaces {name, website_url}`): atomically
   `UPDATE users SET trials_used=trials_used+1 WHERE id=$1 AND trials_used<2`; 0 rows →
   **403 gate payload** `{code:"trial_limit", message: prompts/trial_limit.md rendered,
   contact:{linkedin,whatsapp,email} from RAJ_* env, form:true}` and NO tenant row.
   Success → tenant (plan='trial', owner_user_id) + generated widget_key → 201. DELETE
   purges tenant + Qdrant points + rows and does NOT refund the trial. Existing
   workspaces keep working after the gate (it blocks NEW ones only).
4. **Trial caps** (env): crawl `MAX_TRIAL_PAGES=25` (clamp, friendly note in crawl SSE);
   `TRIAL_MESSAGES_DAILY=40` per workspace in the rate-limit middleware → designed 429.
   `plan='premium'` lifts both to the v1 limits (200/day etc.).
5. **Ownership scoping**: `/admin/sources*` and `/conversations*` accept EITHER the
   legacy ADMIN_TOKEN (scripts/seeding, unchanged) OR a JWT whose user owns the tenant —
   resolve via `owner_user_id`; wrong owner → 404 (not 403 — don't leak existence).
   Resolves E2's flagged "revisit per-tenant admin accounts" note.
6. **Premium contact** (`POST /api/premium-contact {name, email, company?, message}`):
   insert `premium_leads` row → fire n8n `POST /webhook/premium-lead` (header
   `X-Lead-Token`, respond-early, 3s timeout, failure = events row `workflow_error` but
   the API still 202s — the row is the source of truth, WF-P is best-effort notify).
   Rate-limit 3/day/IP.
7. **Config additions**: `JWT_SECRET`, `JWT_TTL_DAYS`, `RAJ_LINKEDIN_URL`,
   `RAJ_WHATSAPP_URL`, `RAJ_EMAIL`, `LEAD_TOKEN`, `MAX_TRIAL_PAGES`,
   `TRIAL_MESSAGES_DAILY` — `.env.example` updated with comments.

## Acceptance criteria
- Register → create workspace 1 → crawl (≤25 pages enforced) → chat works; workspace 2
  ok; workspace 3 → 403 gate payload with working contact links; existing two still chat.
- Concurrent double-create at trials_used=1 → exactly one succeeds (guarded UPDATE).
- Owner A cannot read/crawl/reply on owner B's workspace (404); ADMIN_TOKEN path still
  seeds; anon key still sees only masked views.
- Premium form → row in `premium_leads` + webhook fired (capture with a local listener);
  n8n down → 202 + workflow_error event, row intact.
- psql `apply-sql.sh --assert` transcript green on real Supabase.

## Required verification
pytest (auth, trials truth table incl. concurrency, ownership isolation, premium flow,
caps) green; `ruff` clean; paste the curl walkthrough of the full visitor journey +
the psql transcript. `/spec-check docs/specs/E5-accounts-trials.md`.
