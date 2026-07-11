'use client'

import { useState } from 'react'
import { Check, Copy } from 'lucide-react'
import { WIDGET_URL } from '@/lib/config'

export function EmbedSnippet({ widgetKey }: { widgetKey: string }) {
  const [copied, setCopied] = useState(false)
  const snippet = `<script src="${WIDGET_URL}/embed.js" data-key="${widgetKey}"></script>`

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(snippet)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      // Clipboard permission denied — the code is still selectable/visible.
    }
  }

  return (
    <div className="glass rounded-2xl p-4">
      <div className="mb-2 flex items-center justify-between">
        <p className="text-xs font-bold uppercase tracking-wide text-foreground-muted">
          Paste before &lt;/body&gt; on your site
        </p>
        <button
          type="button"
          onClick={copy}
          className="flex cursor-pointer items-center gap-1.5 rounded-lg border border-border px-2.5 py-1.5 text-xs font-semibold transition-colors hover:border-brand/40"
        >
          {copied ? (
            <>
              <Check className="size-3.5 text-success" aria-hidden="true" /> Copied
            </>
          ) : (
            <>
              <Copy className="size-3.5" aria-hidden="true" /> Copy
            </>
          )}
        </button>
      </div>
      <pre className="overflow-x-auto rounded-xl bg-surface-muted p-3 text-xs">
        <code>{snippet}</code>
      </pre>
    </div>
  )
}
