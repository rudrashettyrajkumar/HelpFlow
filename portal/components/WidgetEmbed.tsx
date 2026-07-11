'use client'

import { useEffect, useRef } from 'react'
import { WIDGET_URL } from '@/lib/config'

type Props = {
  widgetKey: string
  /** Defaults to `auto` (follows OS) — same default as embed.js itself. */
  theme?: 'light' | 'dark' | 'auto'
  /** base64url `llmConfig` handoff for the wizard's preview step (spec Req 3
   * step 4) — see widget/src/lib/llmConfig.ts's design note. Omit for the
   * public landing demo (always runs on the seeded tenant's own demo mode). */
  llmConfigParam?: string | null
}

/** Injects the REAL embed.js loader exactly as a client's site would (spec
 * Req 1: "the LIVE widget embedded over the seeded demo tenant") — not a
 * mock. Mirrors widget/public/demo.html's own script-injection pattern so
 * `document.currentScript` resolves correctly inside embed.js. */
export function WidgetEmbed({ widgetKey, theme = 'auto', llmConfigParam }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!widgetKey) return
    const script = document.createElement('script')
    script.src = `${WIDGET_URL}/embed.js`
    script.setAttribute('data-key', widgetKey)
    script.setAttribute('data-theme', theme)
    if (llmConfigParam) script.setAttribute('data-llm-config', llmConfigParam)
    document.body.appendChild(script)
    return () => {
      script.remove()
      // embed.js appends its own iframe straight to <body> — clean it up on
      // unmount/re-key so switching workspaces never stacks widgets.
      document.querySelectorAll('iframe[title="Chat widget"]').forEach((el) => el.remove())
    }
  }, [widgetKey, theme, llmConfigParam])

  return <div ref={containerRef} aria-hidden="true" />
}
