# SPEC E5 — Chat widget (embeddable, the demo star)

**Epic:** E5 · **Depends on:** E3 (live API), E4 (handoff exists) · **Architecture refs:** §7.1, §8.1

## Objective
The thing a client pastes onto their website: one `<script>` tag → a chat bubble that streams
grounded, cited answers, shows citation chips, offers "talk to a human", and — when the AI
escalates or a human takes over — shows a live "a human joined" state with the agent's real
replies appearing in the same thread. This screen IS the portfolio piece and the Loom's hero
shot. Bind to the REAL SSE contracts from E3 — do not guess them.

## Read first (don't guess the contract)
`backend/api/chat.py` and `backend/utils/sse.py` for the exact `/chat/stream`,
`/chat/subscribe` event shapes. Port streaming-client patterns from DocChat's frontend
(`/mnt/d/PortfolioProjects/DocChat/frontend/src/`) — fetch-streaming SSE parser, reconnect,
citation chip → sources UX.

## Deliverables
```
widget/embed.js                       # loader: injects an iframe, passes ?key=WIDGET_KEY + theme
widget/src/App.tsx                     # the bubble app (React 18 + Vite + Tailwind)
widget/src/api/client.ts               # SSE fetch-stream parser for /chat/stream + /chat/subscribe
widget/src/hooks/ (useChatStream, useConversationSubscribe)
widget/src/components/ (Bubble, MessageList, Message, CitationChip, SourcesDrawer,
                        HumanJoinedBanner, Composer, StatusPill)
widget/public/demo.html                # a throwaway host page that embeds the widget (for the Loom)
widget/README.md                       # the one-line embed snippet + config options
```

## Requirements
1. **Loader** (`embed.js`): a business adds `<script src="…/embed.js"
   data-key="WIDGET_KEY"></script>`. It injects a floating bubble + an iframe hosting the app;
   the widget key + theme flow through as query params. The app resolves `tenant_id` server-side
   from the key (never trusts a client-sent tenant_id — invariant #2).
2. **Streaming answer**: POST `/chat/stream` with the widget key + conversation_id (persisted
   in `localStorage`) + message; render tokens live; on `{event:"sources"}` show citation chips
   `[1] [2]`; click a chip → sources drawer with page title + a link to the source URL.
3. **Handoff UX**: on `{event:"handoff", reason}` show a warm "connecting you to a person…"
   state and (per §3.2/E4) if the reason implies off-hours, prompt for the customer's email
   inline (posts to `/chat/stream` as the next message OR a small `customer_email` field — keep
   it simple: send it as a normal message the pipeline records; the console shows it). Keep the
   composer usable so the customer can keep typing.
4. **Live human replies**: hold a `/chat/subscribe` SSE connection for the conversation; when an
   agent reply arrives (`{message, role:'agent'}`) render it with the agent's display name and a
   "human joined" banner the first time; on `{status:'resolved'}` show a resolved state; on
   `{status:'ai_handling'}` (hand-back) quietly re-enable AI answers.
5. **Resilience** (port DocChat): SSE reconnect with `Last-Event-ID`, exponential backoff
   1s/2s/4s/8s; never a raw error or a hang; typing indicator during streaming and while
   waiting for a human; 429 rate-limit → friendly inline message.
6. **Theming**: business name, brand color, greeting, and launcher icon come from the tenant
   config (passed via the key resolution / a `GET /widget/config` call). Empty/error/limit
   states all designed. Mobile-first (bubble opens full-height on phones). "Powered by
   HelpFlow" footer (removable per tenant later).
7. **Accessibility & polish**: keyboard-navigable, focus trap in the open bubble, prefers
   dark/light, sub-frame so host-site CSS can't leak in. This is the highest-effort screen —
   spend the budget on streaming smoothness and the human-joined transition.

## Acceptance criteria (walk personally in an incognito window on demo.html)
- Ask a normal question → tokens stream, citation chips appear, clicking one opens the source
  page. First token feels instant.
- Ask an off-topic question → the "getting a human" state appears (no fabricated answer).
- With the console (or a manual `POST /conversations/{id}/reply` in E3) sending a reply, the
  agent's message appears live in the widget with the "a human joined" banner — without a
  page refresh.
- Kill the network in devtools mid-stream → it reconnects and continues, never shows a raw error.
- Works at 360px width; light and dark; host page CSS doesn't bleed into the bubble.

## Required verification
- `npm run build` clean; TypeScript strict; ESLint clean.
- Record the exact steps used for the offline-reconnect and the human-takeover walkthroughs
  in the summary (these become the Loom beats).
