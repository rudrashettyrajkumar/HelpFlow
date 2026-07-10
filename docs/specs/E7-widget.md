# SPEC E7 — Chat widget (embeddable, the demo star)

**Epic:** E7 · **Depends on:** E4 (SSE + notice events), E5 (widget keys), E6 (handoff live) ·
**Architecture refs:** §3.2, §3.3, §4.3, §7.1, §8, §8.2

## Objective
The thing a client pastes onto their website: one `<script>` tag → a chat bubble that
streams grounded, cited answers, shows citation chips, offers "talk to a human", shows a
live "a human joined" state when an agent takes over — and (v2) renders the tier states
beautifully: the demo-exhausted card with get-a-free-key buttons, key-invalid and
embed-mismatch notices, and a subtle "free demo mode" chip. This screen IS the portfolio
piece and the Loom's hero shot. Bind to the REAL SSE contract from E3/E4 — never guess it.

## Read first (don't guess contracts) / port
`backend/api/chat.py` + `backend/utils/sse.py` for exact `/chat/stream`, `/chat/subscribe`
and `notice` event shapes. Port streaming-client patterns from DocChat's frontend
(`/mnt/d/PortfolioProjects/DocChat/frontend/src/`): fetch-stream SSE parser, reconnect,
citation chip → sources drawer, and the design tokens (§8 family look — light-first
colorful glassmorphism, Plus Jakarta Sans, CSS-var themes). Invoke the `ui-ux-pro-max`
skill before building screens.

## Deliverables
```
widget/embed.js                      # loader: floating bubble + iframe, ?key=WIDGET_KEY + theme
widget/src/App.tsx                   # React 18 + Vite + TS + Tailwind bubble app
widget/src/api/client.ts             # SSE fetch-stream parser (/chat/stream + /chat/subscribe)
widget/src/lib/llmConfig.ts          # read BYOK config from localStorage → X-LLM-*/X-Embed-* headers
widget/src/hooks/ (useChatStream, useConversationSubscribe)
widget/src/components/ (Bubble, MessageList, Message, CitationChip, SourcesDrawer,
                        HumanJoinedBanner, Composer, StatusPill, NoticeCard, TierChip)
widget/public/demo.html              # throwaway host page (for the Loom + landing embed)
widget/README.md                     # one-line embed snippet + config options
```

## Requirements
1. **Loader**: `<script src="…/embed.js" data-key="WIDGET_KEY"></script>` injects bubble +
   iframe; key + theme flow as query params; `tenant_id` resolves SERVER-side from the key
   (invariant #2 — never trust a client tenant_id).
2. **Streaming answer**: POST `/chat/stream` (widget key + localStorage conversation_id +
   message); tokens render live; `{event:"sources"}` → citation chips `[1] [2]`; chip →
   sources drawer (page title + source URL link). First token must feel instant.
3. **BYOK headers**: if the owner configured a model in Model Studio (E8 writes the config
   to localStorage under the shared key), `llmConfig.ts` attaches the `X-LLM-*`/
   `X-Embed-*` headers; otherwise none (demo mode). The `TierChip` in the composer shows
   "Free demo" / the selected model name; clicking it deep-links to Model Studio when the
   widget runs inside the portal preview (hidden on external embeds).
4. **Notice states (v2, THE new UX)**: `{event:"notice", code, message, links[]}` renders
   `NoticeCard` — for `demo_exhausted`: the §4.3 copy, buttons "Get a Groq key" /
   "Get an OpenRouter key" (new tab) / "Open Model Studio" (portal only), and the
   midnight-UTC reset note. For `key_invalid` / `embed_mismatch`: the designed
   explanation. NEVER a raw error string, NEVER a dead end.
5. **Handoff UX**: `{event:"handoff", reason}` → warm "connecting you to a person…" state;
   off-hours → inline email prompt (sent as a normal message the pipeline records);
   composer stays usable.
6. **Live human replies**: `/chat/subscribe` SSE; agent reply → message with display name
   + "human joined" banner (first time); `{status:'resolved'}` → resolved state;
   hand-back → AI quietly resumes.
7. **Resilience** (port DocChat): reconnect with `Last-Event-ID`, backoff 1s/2s/4s/8s;
   typing indicators; 429/limit → friendly inline card; never a hang or raw traceback.
8. **Theming + polish**: business name, brand color, greeting from tenant config; light +
   dark; empty/error/limit states designed; keyboard-navigable, focus trap; mobile-first
   (full-height on phones); iframe isolates host CSS; "Powered by HelpFlow" footer.

## Acceptance criteria (walk personally, incognito, on demo.html)
- Normal question → streams, chips, drawer link works. Off-topic → human handoff state,
  no fabricated answer. Console reply → appears live with the banner, no refresh.
- Demo budget forced to 0 → the demo-exhausted card with working key links (this is a
  Loom beat — make it gorgeous). Bad BYOK key → key-invalid notice.
- With a real Groq key configured → TierChip shows the model; answers still cite.
- Devtools-offline mid-stream → reconnects, never a raw error. 360px width, light + dark,
  host CSS isolated.

## Required verification
`npm run build` clean; TS strict; ESLint clean. Record the exact steps of the
offline-reconnect, human-takeover, and demo-exhausted walkthroughs (they become Loom
beats). `/spec-check docs/specs/E7-widget.md`.
