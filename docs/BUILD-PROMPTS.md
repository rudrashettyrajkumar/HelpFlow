# BUILD PROMPTS — one Claude Code session per epic

How to use: open a fresh Claude Code session in the HelpFlow repo, paste the prompt for the
current epic, review the result, run the verification, then `/spec-check` before committing.
Don't start the next epic in the same session — fresh context per epic keeps quality high.

> Prompts point at the spec + architecture instead of repeating details. The docs are the
> source of truth; the prompt's job is scope + the reuse pointers + guardrails + definition
> of done.
>
> Reality check: FastAPI/widget/console are normal codebases Claude runs directly (pytest,
> uvicorn, npm). n8n is NOT — Claude writes `workflows/*.json` + `snippets/*.js`, you import
> in the n8n editor and paste results back; Claude gives the exact import curl each time.
> Railway/Supabase/Slack/Meta/OAuth steps come to you as numbered checklists.

---

## E1 — Foundation

```
Read docs/ARCHITECTURE.md fully, then implement docs/specs/E1-foundation.md exactly.

Context: portfolio project #3 — an AI customer-support agent. It FUSES my first two
projects. Port heavily, don't reinvent:
- From DocChat (/mnt/d/PortfolioProjects/DocChat/backend/utils/): config.py, llm_router.py,
  guardrails.py, sse.py, embeddings.py — read them and adapt (strip PDF/session specifics,
  keep the engineering: failover chain, semaphore, guard_stream, env-driven config).
- From LeadFlow (/mnt/d/PortfolioProjects/LeadFlow/): sql/ patterns (guarded transitions,
  RLS masked views), scripts/export-workflows.mjs — port the discipline.

Hard rules:
- No LangChain/agent frameworks. Plain Python 3.12 asyncio + FastAPI + LiteLLM.
- The conversations.status CHECK enum and the RLS views are FROZEN contracts for E2–E7 —
  get them exactly per ARCHITECTURE §5.2/§5.3.
- Every model id/key/limit/threshold from config.py env. Every external call timeout+fallback.
- Credential/collection/table names are contracts. Zero secrets in the repo.

Walk me through the Railway (FastAPI + n8n), Supabase, Slack, and Gmail-alert setup as
numbered checklists; do everything file-based yourself. Definition of done: the spec's
acceptance criteria + required tests, including the psql assertion transcript. Ambiguous →
smallest reasonable choice, flag it.
```

---

## E2 — Ingestion (website crawler)

```
Read docs/ARCHITECTURE.md §3.1/§5.1 and implement docs/specs/E2-ingestion.md exactly. E1 is
merged — reuse its config, clients, sse helpers, Qdrant collection.

Port, don't reinvent: the chunker, batched embeddings, and Qdrant upsert come from DocChat
(/mnt/d/PortfolioProjects/DocChat/backend/ingestion/chunker.py + utils/embeddings.py +
utils/qdrant_client.py) — read them first and adapt page-tracking → url/title-tracking. The
ONLY new code is the crawler (discover + fetch + trafilatura/Jina main-content extraction).

Priorities in order: (1) crawler safety — same-domain only, robots.txt, page cap, asset-URL
skipping (write these tests first); (2) extraction quality — trafilatura, Jina fallback for
JS-heavy pages, skip-and-record sub-200-char pages; (3) rollback on mid-crawl embed failure
(no half-ingested tenant); (4) refresh/delete by source_id with no stale points; (5) SSE
progress events matching the spec's exact shapes (E6's admin UI binds to them).

Also write seed_demo_tenant.py and crawl a suitable public docs/help site into a demo tenant;
note the site + chunk count in the commit body. Every Qdrant point payload EXACTLY per §5.1.
Done = spec acceptance criteria + required tests green.
```

---

## E3 — Answer engine + escalation (the brain)

```
Read docs/ARCHITECTURE.md §3.2/§3.3/§4/§5.2/§6 and implement docs/specs/E3-answer-escalation.md
exactly. E1+E2 merged — compose their pieces, don't duplicate.

Port the pipeline shape, rewrite agent, retrieval+RRF, and streaming answer agent from DocChat
(/mnt/d/PortfolioProjects/DocChat/backend/pipeline + agents + utils/rrf.py). Model the
rewrite agent's failure handling on DocChat's DEFAULT pattern: any parse error/timeout → safe
default, never an exception.

The pipeline order in §3.2 is LAW: conversation load → human_assigned guard → guardrail →
route/rewrite → retrieve → escalation decision → answer OR escalate → persist. Write these
tests BEFORE the pipeline: (a) zero llm-router calls on the guardrail path, (b) zero llm-router
calls on the human_assigned path (the AI must NEVER answer a human-assigned conversation —
invariant #5), (c) the escalation truth table.

Three things I'll personally check:
1. Every Qdrant search carries the tenant_id filter at ONE choke point; a test asserts
   cross-tenant isolation (tenant A cannot read tenant B's chunks).
2. Grounded-or-handoff: low_relevance / sensitive intent / explicit human request → escalate,
   never fabricate. The escalation decision is deterministic (NO llm call) and exhaustively tested.
3. The SSE contract (token/seq, sources, handoff, done, human_turn) is frozen — E5 binds to it.

The prompt files (answerer_identity.md, citation_rules.md, router.md, handoff_message.md) are
product-critical: cite [n] per claim, offer a human instead of guessing, never mention
internal machinery, keep each under ~300 words. Verify end-to-end with curl against the seeded
tenant and paste the transcripts (normal answer, off-topic→escalate, refund→escalate,
human_assigned→human_turn) + the eval_retrieval report. Done = acceptance criteria + tests green.
```

---

## E4 — Handoff orchestration (n8n WF-H)

```
Read docs/ARCHITECTURE.md §2/§3.2(5b)/§5.2/§7.2 and implement docs/specs/E4-handoff.md exactly.
E1–E3 merged; FastAPI already fires POST /webhook/handoff on escalation.

Port the n8n discipline from LeadFlow — read
/mnt/d/PortfolioProjects/LeadFlow/.claude/skills/n8n-builder/SKILL.md and its workflows/. This
workflow has NO LLM calls (the brain owns those); it is pure orchestration: notify + business
hours + events.

THE boundary rule of this project: WF-H only NOTIFIES. It must NOT write status='human_assigned'
(the console owns that transition) and must NOT decide escalations (FastAPI owns that). One
owner per transition — respect it.

Get these right: (1) header-token auth + respond-early (FastAPI must not block on n8n);
(2) the escalation UPDATE is guarded (WHERE status='open') so a retried webhook is a no-op;
(3) business-hours branch reads $env, off-hours doesn't ping the on-call storm; (4) Slack OR
Gmail failing still delivers via the other + writes a workflow_error event.

Walk me through the Slack incoming-webhook + Gmail-alert credential setup as checklists, give
me the exact n8n import curl, then we trace a live escalation together. Done = spec acceptance
criteria + both notify transcripts + exported wf-handoff.json matching snippets byte-for-byte.
```

---

## E5 — Chat widget (the demo star)

```
Implement docs/specs/E5-widget.md exactly. Read docs/ARCHITECTURE.md §7.1/§8.1 first, and read
backend/api/chat.py + backend/utils/sse.py to bind to the REAL /chat/stream and /chat/subscribe
event shapes — do NOT guess the contract. Port streaming-client patterns (fetch-stream SSE
parser, reconnect, citation chip → sources drawer) from DocChat's frontend
(/mnt/d/PortfolioProjects/DocChat/frontend/src/).

Stack: Vite + React 18 + TypeScript + Tailwind. embed.js loader injects an iframe; the widget
key resolves tenant_id SERVER-SIDE (never trust a client tenant_id).

Build in spec order (loader+shell → streaming answer + citations → handoff state → live human
replies via /chat/subscribe → resilience → theming/polish) and keep it working against the
live local backend throughout. This screen IS the portfolio and the Loom hero: spend the
budget on streaming smoothness, the citation-chip → source interaction, and the "a human
joined" live transition. Dark+light, mobile-first, host-CSS isolated in the iframe.

Done = the spec's acceptance checklist walked in an incognito window on demo.html, including
the devtools-offline reconnect AND the live human-takeover walkthrough (record the steps —
they become Loom beats). npm run build clean, TS strict.
```

---

## E6 — Console (inbox + admin + analytics)

```
Implement docs/specs/E6-console.md exactly. Read docs/ARCHITECTURE.md §5.2/§5.3/§7.1/§8.2 and
read sql/002_views_rls.sql for the REAL view shapes + backend/api/conversations.py for the
claim/reply/resolve/handback contract — don't guess columns. Port dashboard patterns (anon
key, masked views, server-side token, Vercel) from LeadFlow's dashboard/. INVOKE the dataviz
skill before building the KPI tiles, volume chart, and gap report.

Stack: Next.js 14 App Router + TS + Tailwind. Reads go ONLY through the three anon RLS views;
agent actions go through Next.js route handlers holding the bearer token server-side — after
building, grep the .next output to prove no token shipped.

Build in spec order (auth+shell → inbox list+detail+reply → claim/resolve/handback → sources
admin with crawl SSE → analytics+gap report). Two things matter most: (1) the live loop —
escalation appears in the inbox, Claim → Reply shows live in the widget, Resolve; double-Claim
is one assignment (guarded UPDATE). (2) the Gap Report — cluster real low_relevance questions
into "docs to write next" themes; make it the analytics hero (it's the highest-value Loom
moment). Keep stage-chip colors consistent with the widget.

Done = acceptance checklist walked in incognito (incl. double-claim + token-grep + Lighthouse)
+ deployed Vercel URL in the summary.
```

---

## E7 — Ship

```
Implement docs/specs/E7-ship.md. Everything is built; this session makes it live, observable,
drift-proof, and sellable.

Order: WF-O ops (SLA sweep — force a stale escalation to test; daily digest — verify real
numbers) → check-sync.mjs (run it; edit a node to prove it fails; fix drift) → deploy
(FastAPI + n8n on Railway, widget on Cloudflare Pages, console on Vercel; verify SSE through
the proxy and CORS locked) → UptimeRobot on /health + /webhook/health → secret sweep →
README → CASE-STUDY.md → LOOM-SCRIPT.md → runbook.md.

WF-O owns the needs_human → abandoned transition (guarded, off-hours+idle only) — no other
actor writes it.

For the sales artifacts: audience is a non-technical client on Upwork who fears a bot that
lies to their customers. Lead with the live widget link and a GIF of an escalation → human
takeover. Make grounded-or-handoff and the ethics/safety section SELLING points. Real measured
numbers only (time-to-first-token, crawl seconds, deflection rate, OpenRouter cost). The case
study tells the reuse story: "RAG engine = Project #1, orchestration = Project #2, composed
into a shippable product." Give me exact GIF-recording steps and every dashboard action as a
numbered checklist. Done = production end-to-end trace + acceptance criteria + all three sales
artifacts + empty secret sweep.
```

---

## E8 — WhatsApp channel (OPTIONAL)

```
Only do this after E1–E7 are solid and a WhatsApp story would win a specific client. Read
docs/ARCHITECTURE.md §3.4 and implement docs/specs/E8-whatsapp-optional.md exactly.

n8n owns this channel (webhooks + provider quirks + retries); the brain is untouched — WF-W
normalizes WhatsApp into a POST /chat call and sends the reply back. The conversation model
already supports it via channel + (tenant_id, channel, external_ref) from E1; no schema change.

Provider: Meta WhatsApp Cloud API test number (Twilio sandbox is the fallback if Meta
onboarding stalls — the snippets abstract the payload shape).

Get these right: (1) idempotency — hf:wa:{message_id} dedup, replayed webhook doesn't
double-reply (invariant #6, test by replaying); (2) signature/verify-token check; (3) brain
error → polite fallback + workflow_error event, never a silent drop; (4) handoff outbound —
a console reply reaches the WhatsApp thread; no AI message while human_assigned (invariant #5).

Walk me through the Meta app + number + verify-token setup as a checklist; give the import
curl; we trace a live inbound+outbound + a replay + an escalation together. Done = spec
acceptance criteria + transcripts + exported wf-whatsapp.json matching snippets (check-sync clean).
```
