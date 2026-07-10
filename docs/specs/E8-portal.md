# SPEC E8 — Portal: landing, auth, onboarding wizard, Model Studio, trial & premium gates

**Epic:** E8 · **Depends on:** E5 (auth/workspaces/gate APIs), E7 (widget for the preview) ·
**Architecture refs:** §3.0, §4.1–§4.4, §5.3, §7.1, §8, §8.1

## Objective
The storefront — the "beautiful display" mandate lives here. A public landing page with a
LIVE demo widget, signup/login, the onboarding wizard (paste your site → watch it learn →
pick your brain → chat), the **Model Studio** (BYOK provider cards + live key test), the
trial counter, and the **premium gate** (contact Raj — LinkedIn/WhatsApp/email + lead
form). A visitor must get from landing to chatting-over-their-own-site in ~2 minutes, and
a client skimming the portfolio must think "this person ships products, not notebooks."

## Read first / port
- DocChat v3 Model Studio (`/mnt/d/PortfolioProjects/DocChat/frontend/src/` —
  ModelStudio modal, provider cards, accuracy meters, key test, ModelChip, llmConfig.ts)
  — port the pattern into Next.js, upgraded from modal to a full studio page/panel.
- DocChat v2 design system (`docs/DESIGN-SYSTEM.md`, index.css tokens): light-first
  colorful glassmorphism, Plus Jakarta Sans, CSS-var light/dark themes, GradientMesh,
  glass cards, motion. Same family look — this is the portfolio's flagship.
- **Invoke `ui-ux-pro-max` before building each screen** (and `dataviz` if any chart
  sneaks in here rather than E9).

## Stack
Next.js 14 App Router + TypeScript + Tailwind on Vercel (`portal/`). The E9 console
builds inside this same app later — structure routes accordingly:
`(public)/` landing · `(auth)/login|register` · `app/` authenticated shell
(wizard, workspaces, studio; E9 adds inbox/sources/analytics).

## Deliverables
```
portal/app/(public)/page.tsx          # landing: hero + LIVE widget + tiers + architecture + Raj
portal/app/(auth)/login|register/     # JWT auth pages (localStorage, 401→logout interceptor)
portal/app/app/page.tsx               # workspace cards ("trial 1 of 2") + create
portal/app/app/new/                   # the onboarding wizard (4 steps, §3.0)
portal/app/app/studio/                # Model Studio
portal/app/app/upgrade/               # the premium gate screen + lead form
portal/lib/ (api client, auth context, llmConfig shared with widget, types)
portal/components/ (GradientMesh, Glass, ProviderCard, AccuracyMeter, KeyTester,
                    ModelPicker, DemoBudgetCard, TrialBadge, WizardSteps, EmbedSnippet,
                    ContactRaj, LeadForm, ThemeToggle, Logo, UserMenu)
```

## Requirements
1. **Landing (public)**: gradient-mesh hero, one-line pitch ("An AI support agent that
   knows when to get a human"), the LIVE widget embedded over the seeded demo tenant
   ("ask this fake company anything"), the three-tier explainer (Demo / Free BYOK / Paid
   BYOK — honest copy from §4.1), a small architecture diagram, tech-stack chips
   (LangChain · LangGraph · FastAPI · n8n · Qdrant · Supabase), and a "built by Raj"
   footer with LinkedIn/WhatsApp/GitHub (RAJ_* env via NEXT_PUBLIC config). OG tags +
   real favicon — this link gets pasted in proposals.
2. **Auth**: register/login against `/api/auth/*`; JWT in localStorage; AuthContext +
   Bearer header; 401 anywhere → logout redirect. Password field UX done properly.
3. **Wizard** (`app/new`): Step 1 name+URL → POST /api/workspaces (403 → route to
   upgrade); Step 2 live crawl SSE progress (discovering → fetching n/25 → embedding →
   ready, with the page-cap note); Step 3 Model Studio inline (skippable — "Demo mode"
   preselected, remaining shared budget shown via a small GET); Step 4 the E7 widget
   LIVE over their content + "try asking about a refund" escalation demo button + the
   copy-paste embed snippet. The wizard is the Loom's spine — every step must feel alive.
4. **Model Studio**: provider cards rendered from `GET /api/models` ONLY (no hardcoded
   models in the frontend — the catalog is the single source): kind badge
   (free/freemium/paid), tagline, accuracy meter (1–5), speed/cost/context chips,
   collapsible "get a key in 4 steps", key input + **live test** via
   `/api/models/validate` (✓ + latency or the typed error), chat-model picker +
   embedding-model picker (only embed-capable providers; explain Groq/Anthropic have
   none), OpenRouter custom-model-id field. Config persists in localStorage under the
   key shared with the widget (`llmConfig.ts`); keys NEVER sent anywhere except the
   validate probe + per-request headers; say exactly that in the UI ("your key never
   leaves this browser"). The Demo-mode card sits first, showing today's remaining
   shared budget and the free-tier honesty copy.
5. **Trial UX**: workspace cards show "Trial 1 of 2" badges; at 2, the create button
   becomes "Unlock more →" routing to the gate. The embed-mismatch 409 (changed embed
   model) surfaces as a designed dialog offering re-crawl.
6. **Premium gate** (`app/upgrade`): warm, personal, zero-pressure — Raj's
   name/photo/positioning line, LinkedIn + WhatsApp + email buttons, the short lead form
   → POST /api/premium-contact → success state ("Raj usually replies within a few
   hours"). Design it like the conversion surface it is.
7. **Quality**: TS strict, ESLint clean, `npm run build` clean; light+dark; mobile;
   designed empty/loading/error states everywhere; Lighthouse ≥90 on the landing;
   no secret/token in the client bundle (grep `.next`).

## Acceptance criteria (walk personally in incognito)
- Cold visitor: landing → chat with the live demo widget → register → wizard → chatting
  over THEIR site in ~2 min (time it, note it — it's a README number).
- Model Studio: a real Groq key validates ✓, gets picked, the preview widget's TierChip
  shows it, answers flow on it; a garbage key shows the friendly error.
- Demo budget at 0 → the studio's demo card and the widget both explain it honestly with
  working key links.
- Workspace #3 → the gate; form → (with E6 live) Raj's Slack/Gmail ping within seconds.
- Bundle grep: no JWT_SECRET/service keys; user keys only in localStorage.

## Required verification
Build/lint/TS clean; Lighthouse score; the timed cold-visitor walkthrough steps; bundle
grep output; deployed Vercel preview URL. `/spec-check docs/specs/E8-portal.md`.
