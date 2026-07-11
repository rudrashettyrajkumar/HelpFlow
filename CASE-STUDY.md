# Case study: HelpFlow — an AI support agent that knows when to get a human

**For:** anyone hiring for an AI chatbot who has seen a bad one — the kind that
confidently makes up a return policy, or can't tell a customer it doesn't know
something. This project exists to answer one question honestly: *can I trust this
thing to talk to my customers?*

## The problem with most "AI support agent" demos

Most chatbot demos show you the happy path: ask it something easy, watch it answer
well, move on. They don't show you what happens when a customer asks something the bot
genuinely doesn't know, or asks for a refund, or gets frustrated and wants a person.
That's the moment that actually determines whether a support bot helps your business or
embarrasses it in front of a customer.

HelpFlow is built around that moment, not around it.

## What it does

1. You give it your website. It reads every page, the same way a new support hire
   would skim your docs before their first shift.
2. A customer asks it something. If the answer is in your content, it answers —
   **and shows exactly which page it got the answer from**, so nothing is a black box.
3. If the answer *isn't* in your content, or the customer is upset, or they just want
   a human — it says so, plainly, and hands the conversation to you (or your team)
   **live, in the same chat window the customer is already looking at.** No dropped
   context, no "please repeat your issue to a new person."
4. You get a dashboard showing how often it handled things on its own vs. handed off,
   and — this is the part most support tools skip — **a report of the questions your
   documentation doesn't actually answer**, so you know what to write next.

### The trust demo (escalation → human takeover)

![Escalation to human takeover](docs/assets/takeover.gif)

That GIF is the whole pitch in fifteen seconds: a customer asks something sensitive,
the AI declines to guess, a Slack alert lands, a human claims the conversation from an
inbox, and the reply appears live in the same widget the customer never left. Capture
checklist: `docs/runbook.md` §12.

## Try it yourself, right now, free

You don't have to take my word for the trust story — the second half of this project's
pitch is that you can go verify it in about two minutes, before spending anything:

1. Open the live portal (`<PORTAL_URL>`) and chat with the demo widget on the landing
   page — no signup needed.
2. Register, paste your own website's URL, watch it crawl your actual pages.
3. **Model Studio**: optionally paste a free Groq or OpenRouter API key (both are free,
   no credit card, ~2 minutes to get one) — the studio tests it live and shows "key
   works ✓" before you commit. Your key is stored only in your browser; it's never sent
   to my database.
4. Chat with the agent over your own content. Try asking it a refund question — watch
   it hand off instead of making something up.
5. Get two workspaces free. Want a real deployment for your business, no limits →
   there's a warm, no-pressure "talk to me" screen with LinkedIn/WhatsApp/email and a
   short form.

If you don't want to get a key at all, it still works — on a shared free daily budget
of open-source models, and it tells you honestly when that shared budget runs out for
the day (rather than a cryptic error), with one-click links to get your own free key.

## The reuse story: three projects, composed

This is the third project in a three-project portfolio, and it's deliberately **not**
built from scratch — it's the other two, fused, plus one more reuse of the first:

- **The RAG engine is Project #1 (DocChat)**, a "chat with your documents" tool.
  HelpFlow's crawler, chunker, retrieval + reranking pipeline, and the
  citation-grounded-answer pattern are the same engine, retargeted from PDFs to
  websites and from single-user to multi-tenant.
- **The orchestration is Project #2 (LeadFlow)**, an n8n lead-generation automation
  built around a Postgres stage machine with strict, auditable state transitions.
  HelpFlow's human-handoff alerts, its SLA sweep, and its daily ops digest all run on
  that same discipline — every status change is a single-owner, guarded database
  update, never a race.
- **The bring-your-own-key layer is Project #1 again, a third time (v3)** — DocChat
  went through its own BYOK redesign, and that exact pattern (LangChain factory,
  per-request key headers, a live key-test endpoint, a curated model catalog) is what
  ported into HelpFlow's Model Studio almost unchanged.

The point isn't "I copy-pasted code between projects." It's that each piece was solved
once, properly, and proven working — and a real product got built faster and more
reliably by reusing proven engineering instead of re-solving the same problems a third
time under deadline pressure. That's the same judgment call a client is hiring for.

**The closing loop:** the premium-lead workflow (n8n's WF-P) means this demo doesn't
just showcase the work — every time someone hits the trial limit and reaches out, it
generates a real lead, delivered to Slack and Gmail within seconds. The demo sells
itself while you're reading this sentence.

## Architecture, briefly

Two backends with a clean boundary: a FastAPI "brain" owns the RAG pipeline, the
streaming answers, and the (deterministic, not-an-LLM-call) decision to escalate; an
n8n "nervous system" owns everything that's really "when X happens, notify/route
someone" — Slack/Gmail alerts, business-hours logic, the SLA sweep, the lead pings. See
`docs/ARCHITECTURE.md` for the full design and [README.md](README.md) for the diagram.

## Ethics, by design, not by promise

- The **escalation decision is a deterministic function**, not an LLM call — it can't
  be prompted around.
- **The AI never talks over a human** once one has joined a conversation.
- **Customer emails are masked** on every dashboard view (`j***@x.com`), enforced by
  Postgres row-level security, not by application-layer discipline that could be
  forgotten.
- **API keys never touch my server** — browser-only, one parsing choke point, tested.

## Real, measured numbers

*(Filled in from the live production trace — `docs/runbook.md` §11 — not estimated.
Nothing here ships invented; see the runbook for exactly how each number is captured.)*

| Metric | Value |
|---|---|
| Time to first token, demo mode | `<TBD>` ms |
| Crawl time, a 25-page site | `<TBD>` s |
| Cold visitor → chatting on their own site | `<TBD>` min |
| Deflection rate, demo tenant | `<TBD>` % |
| Demo-mode running cost | ₹0/month (free-tier keys, budget-capped) |

## What I'd build next with a real client

- A server-side key vault so BYOK can cover embedded widgets and WhatsApp traffic, not
  just the owner's own browser session (documented honestly as a v1 limitation, not
  hidden).
- Per-tenant business hours instead of one global window.
- A live-scraped, always-current model catalog instead of a hand-refreshed one.

---

Built by Raj — freelance AI/automation engineer. Portfolio: DocChat (RAG) → LeadFlow
(n8n orchestration) → HelpFlow (this project, fusing both + a third BYOK reuse).
