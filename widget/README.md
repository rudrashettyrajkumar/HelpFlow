# HelpFlow chat widget

Embed on any site with one script tag:

```html
<script src="https://YOUR_WIDGET_DOMAIN/embed.js" data-key="WIDGET_KEY"></script>
```

## Config options (script tag attributes)

| Attribute | Required | Values | Default |
|---|---|---|---|
| `data-key` | yes | the workspace's widget key (from the onboarding wizard / Model Studio) | — |
| `data-theme` | no | `light` \| `dark` \| `auto` | `auto` (follows the visitor's OS) |

Business name, greeting, and brand color come from the tenant's own config
(set in the portal) — not script tag attributes — so they stay in sync
however many pages embed the widget.

## Local development

```bash
cp .env.example .env    # set VITE_API_URL to your local FastAPI (default http://localhost:8000)
npm install
npm run dev              # Vite dev server
```

`public/demo.html` is a throwaway host page for manually testing the loader
exactly as a visitor would see it (open it via the dev server, e.g.
`http://localhost:5173/demo.html?key=<a real widget key>`).

## Build

```bash
npm run build             # tsc -b && vite build → dist/
```

`dist/` ships `index.html` (the widget app) + `embed.js` + the built assets;
deploy the whole directory as-is (Cloudflare Pages, ARCHITECTURE §8.3).

## BYOK

If the workspace owner configured a model in Model Studio (E8), the widget
reads that config from `localStorage` (`hf_llm_config_v1`, shared contract —
`src/lib/llmConfig.ts`) and sends it as `X-LLM-*`/`X-Embed-*` headers.
Third-party embeds and end customers never have this config — they always run
in free demo mode (ARCHITECTURE §4.4: BYOK covers the owner's own browser
only).
