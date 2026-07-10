# SPEC E9 — Console: agent inbox + sources admin + analytics & gap report

**Epic:** E9 · **Depends on:** E8 (portal shell), E6 (handoff live) · **Architecture refs:** §5.4, §5.5, §7.1, §8.1

## Objective
The business-facing half of the portal: human agents work escalated conversations (claim,
reply live, resolve, hand back to AI); owners manage website sources and watch crawls; and
analytics prove the value — **deflection rate** and the **gap report** of questions the
docs didn't answer. After this epic the full loop is filmable: customer asks → AI
escalates → agent pinged → opens inbox → replies live in the widget → resolves; the owner
watches deflection climb and the gap report fill.

## Read first (don't guess columns) / port
`sql/002_views_rls.sql` for the REAL view shapes (`v_conversations`, `v_funnel`,
`v_gaps`, `v_events`); `backend/api/conversations.py` for the claim/reply/resolve/
handback contract. Port dashboard patterns (anon key, masked views, polling, server-side
tokens) from LeadFlow's `dashboard/`. **Invoke the `dataviz` skill before the tiles /
volume chart / gap report**, and keep the E8 design system (stage-chip colors shared with
the widget).

## Deliverables (inside `portal/`, extending the E8 app)
```
portal/app/app/inbox/                 # conversation list + detail + reply
portal/app/app/sources/               # add/list/refresh/delete sources (crawl SSE)
portal/app/app/analytics/             # deflection, volume, top questions, GAP REPORT
portal/app/api/                       # route handlers holding service/agent tokens server-side
portal/components/ (Inbox, ConversationView, ReplyBox, SourceManager, KpiTiles,
                    VolumeChart, GapReport, StageChip)
backend/scripts/cluster_gaps.py       # offline gap clustering → v_gaps cache (gap_cluster.md)
```

## Requirements
1. **Access**: reads via the **anon key** through the RLS views only, scoped to the
   JWT-owned workspace (E5 ownership); never a base table, never the service key in the
   browser. Agent actions (claim/reply/resolve/handback) go through Next.js route
   handlers that attach the token server-side — after building, grep `.next` to prove
   nothing shipped (LeadFlow's proof step).
2. **Inbox**: `v_conversations` list, status filter, `needs_human` pinned + loud; new
   escalations arrive live (~10s `v_events` poll or SSE). Detail → full transcript →
   **Claim** (guarded `needs_human→human_assigned`) → **Reply** (lands live in the E7
   widget) → **Resolve** / **Hand back to AI**. Show escalation reason + captured
   customer email. While `human_assigned`, the UI states plainly the AI is paused
   (enforcement is E3's; the console reflects it).
3. **Sources admin**: add URL/sitemap → E2 crawl SSE progress → per-page status + chunk
   counts → refresh/delete; trial page-cap note; the embed-mismatch 409 dialog (E8's)
   reused here.
4. **Analytics**: KPI tiles (conversations, **deflection %** = ai_resolved/total,
   escalations, avg first response), volume/day chart, top questions, and the **Gap
   Report** hero — `cluster_gaps.py` batches `low_relevance` escalation questions through
   `prompts/gap_cluster.md` (demo-chain gateway call, offline) into themes cached for
   `v_gaps`; render themes with frequency + example questions framed as "docs to write
   next". Highest-value screen — the Loom's money shot.
5. **Design**: dataviz-skill-governed charts (accessible, light+dark), consistent stage
   colors with the widget, designed empty/loading/error states, mobile-usable.

## Acceptance criteria (walk personally in incognito)
- End-to-end: widget escalation → inbox within ~10s → Claim → reply → live in widget →
  Resolve → leaves the open list. Double-Claim (two tabs) → exactly one assignment.
- Hand back → the widget's AI answers again.
- Add a small site → progress streams → chunks appear → the widget answers from it.
- Deflection rate matches a hand count of `v_funnel`; gap report shows REAL clustered
  themes from seeded/demo traffic (not placeholders).
- Token grep of `.next` clean; anon key sees only masked views.

## Required verification
Build/TS/ESLint clean; Lighthouse on inbox + analytics; deployed Vercel URL; the
token-grep result; screenshot descriptions of tiles + gap report (README/case-study
assets). `/spec-check docs/specs/E9-console.md`.
