# SPEC E6 — Agent console: inbox + admin sources + analytics & gap report

**Epic:** E6 · **Depends on:** E5, E4 · **Architecture refs:** §5.2, §5.3, §7.1, §8.2, §8.3

## Objective
The business-facing app: human agents work escalated conversations (claim, reply live,
resolve, hand back to AI); owners add website sources and watch crawls; and an analytics view
proves the value — **deflection rate** and the **gap report** of questions the docs didn't
answer. After this epic the full loop is filmable: customer asks → AI escalates → agent gets
pinged → opens the inbox → replies live in the widget → resolves; owner sees deflection climb
and the gap report fill.

## Read first (don't guess columns)
`sql/002_views_rls.sql` for the REAL view shapes (`v_conversations`, `v_funnel`, `v_gaps`,
`v_events`) and `backend/api/conversations.py` for the claim/reply/resolve/handback contract.
Port dashboard patterns (anon key, masked views, polling, Vercel deploy) from LeadFlow's
`dashboard/`. **Invoke the `dataviz` skill before building the tiles / volume chart / gap
report.**

## Deliverables
```
console/                               # Next.js 14 App Router + TS + Tailwind
  app/(auth)/login/                    # simple agent login (bearer/session)
  app/inbox/                           # conversation list + detail + reply
  app/sources/                         # admin: add/list/refresh/delete sources (SSE crawl)
  app/analytics/                       # deflection, volume, top questions, gap report
  app/api/                             # route handlers that hold the service/admin token server-side
  lib/ (supabase anon client, api client for FastAPI agent endpoints, types from views)
  components/ (Inbox, ConversationView, ReplyBox, SourceManager, KpiTiles, VolumeChart, GapReport)
```

## Requirements
1. **Auth + tenant scope**: a simple agent login; every read is tenant-scoped through the RLS
   views using the **anon key** (never a base table, never the service key in the browser).
   The FastAPI agent actions (`/conversations/{id}/claim|reply|resolve|handback`) go through
   Next.js route handlers that hold the bearer token server-side — after building, grep the
   `.next` output to prove no token shipped (LeadFlow's proof step).
2. **Inbox**: list conversations from `v_conversations` (filter by status; `needs_human`
   pinned to top and visually loud); new escalations arrive live (poll `v_events` every ~10s
   or SSE). Open one → full transcript via `/conversations/{id}/messages` → **Claim** button
   (`needs_human → human_assigned`, guarded) → **Reply** box (`POST /reply`; the reply reaches
   the widget live via the E5 subscribe channel) → **Resolve** / **Hand back to AI** buttons
   (guarded transitions). Show the escalation reason and the customer's email if captured.
3. **AI-never-talks-over-human is visible**: while a conversation is `human_assigned`, the UI
   makes clear the AI is paused; hand-back re-enables it. (Enforcement is server-side from E3;
   the console just reflects and drives it.)
4. **Sources admin**: add a URL/sitemap → stream the E2 crawl SSE progress → list sources with
   status + chunk counts → refresh / delete. This is the "paste your site, it learns it" moment.
5. **Analytics** (from `v_funnel` + `v_gaps` + `v_events`):
   - KPI tiles: total conversations, **deflection rate %** (ai_resolved / total), escalations,
     avg first-response time.
   - Volume chart (conversations/day) and top questions.
   - **Gap Report**: cluster the `low_relevance` escalation questions into themes (one offline
     flash-lite batch call using `prompts/gap_cluster.md`, run by a small backend script or a
     Next.js server action; results cached to `v_gaps`), each theme with frequency and example
     questions, framed as "docs to write next". This is the highest-value screen — make it the
     analytics hero.
6. **Design system**: consistent stage-chip / status colors shared with the widget; the
   `dataviz` skill governs the tiles, chart, and gap-report visuals (accessible, light + dark).
   Empty/loading/error states designed; mobile-usable; OG tags.

## Acceptance criteria (walk personally in incognito)
- End-to-end: trigger an escalation from the widget → it appears in the inbox within ~10s →
  Claim it → reply → the reply shows live in the widget → Resolve → it leaves the open list.
- Double-click Claim (or two agents) → exactly one assignment (guarded UPDATE proves out).
- Hand back to AI → the widget's AI answers again; status reflects `ai_handling`.
- Add a small site in Sources → progress streams → chunk counts appear → the widget can then
  answer from it.
- Analytics: deflection rate matches a hand count of `v_funnel`; the gap report shows real
  clustered unanswered questions from the seeded data (not placeholders).
- No service/admin token in the client bundle (grep `.next`); anon key only sees masked views.

## Required verification
- `npm run build` clean; TS strict; ESLint clean; Lighthouse pass on inbox + analytics.
- Deployed Vercel URL in the summary; the token-grep result; a screenshot description of the
  deflection tiles + gap report (these become README/case-study assets).
