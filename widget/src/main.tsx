import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App'
import './index.css'

// Theme resolution (spec Req 8, ARCHITECTURE §8.2): the widget is a SEPARATE
// document inside embed.js's iframe, so it picks its OWN theme from the
// `?theme=` query param rather than inheriting a host page's dark mode.
// Precedence: explicit `light`/`dark` param (the embedding site's choice) >
// OS `prefers-color-scheme` (param absent or `auto`). Resolved to an
// EXPLICIT `data-theme` value (never left as "auto") so Tailwind's
// `dark:` variant — scoped to `[data-theme="dark"]` — works uniformly.
function resolveTheme(): 'light' | 'dark' {
  const requested = new URLSearchParams(window.location.search).get('theme')
  if (requested === 'light' || requested === 'dark') return requested
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

function applyTheme(theme: 'light' | 'dark') {
  document.documentElement.dataset.theme = theme
}

applyTheme(resolveTheme())

const requestedTheme = new URLSearchParams(window.location.search).get('theme')
if (requestedTheme !== 'light' && requestedTheme !== 'dark') {
  // "auto" (or unset) — track OS changes live for the lifetime of the widget.
  window
    .matchMedia('(prefers-color-scheme: dark)')
    .addEventListener('change', (e) => applyTheme(e.matches ? 'dark' : 'light'))
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
