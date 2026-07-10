import { AlertTriangle, ArrowUpRight, Clock, RefreshCw, Sparkles } from 'lucide-react'
import type { NoticeCode, NoticeLink } from '../api/types'
import { MODEL_STUDIO_PATH } from '../lib/llmConfig'

type Props = {
  code: NoticeCode
  message: string
  links: NoticeLink[]
  /** Only true when this widget is running inside the portal's own preview
   * iframe (E8 wizard/Model Studio) — "Open Model Studio" deep-links there
   * via postMessage; hidden on third-party embeds (spec Req 3/4). */
  canOpenModelStudio: boolean
}

const COPY: Record<NoticeCode, { icon: typeof Sparkles; headline: string }> = {
  demo_exhausted: { icon: Clock, headline: "Today's free demo quota is used up" },
  key_invalid: { icon: AlertTriangle, headline: "That key didn't work" },
  embed_mismatch: { icon: RefreshCw, headline: 'This site needs a fresh crawl' },
}

function openModelStudio() {
  window.parent.postMessage({ type: 'hf:open-model-studio' }, '*')
}

/** The v2 hero moment (spec Req 4, "make it gorgeous" — the Loom's money
 * shot): renders `{event:"notice"}` as a designed card, never a raw error.
 * `demo_exhausted` gets the full honest-copy treatment with working
 * get-a-key buttons; `key_invalid`/`embed_mismatch` get the same visual
 * language with the backend's designed explanation. */
export function NoticeCard({ code, message, links, canOpenModelStudio }: Props) {
  const { icon: Icon, headline } = COPY[code]

  return (
    <div className="animate-pop-in glass-strong relative mx-auto max-w-[92%] overflow-hidden rounded-3xl border border-brand/20 p-5 shadow-glow">
      <div
        className="pointer-events-none absolute -right-10 -top-14 size-40 rounded-full bg-brand-gradient opacity-20 blur-2xl"
        aria-hidden="true"
      />
      <div className="relative flex flex-col items-center gap-3 text-center">
        <div className="flex size-12 items-center justify-center rounded-2xl bg-brand-gradient shadow-glow">
          <Icon className="size-6 text-white" aria-hidden="true" />
        </div>
        <h3 className="text-base font-bold">{headline}</h3>
        <p className="text-sm leading-relaxed text-foreground-muted">{message}</p>

        {code === 'demo_exhausted' && (
          <p className="flex items-center gap-1.5 rounded-full bg-surface-muted px-3 py-1 text-xs font-medium text-foreground-muted">
            <Clock className="size-3.5" aria-hidden="true" />
            Resets at midnight UTC
          </p>
        )}

        <div className="mt-1 flex w-full flex-col gap-2">
          {links.map((link, i) => {
            const isStudio = link.url === MODEL_STUDIO_PATH
            if (isStudio && !canOpenModelStudio) return null

            const className = `flex w-full cursor-pointer items-center justify-center gap-1.5 rounded-xl px-4 py-2.5 text-sm font-semibold transition-transform duration-150 hover:scale-[1.02] active:scale-[0.98] ${
              i === 0
                ? 'bg-brand-gradient text-white shadow-glow'
                : 'glass border border-border text-foreground'
            }`

            if (isStudio) {
              return (
                <button key={link.label} onClick={openModelStudio} className={className}>
                  {link.label}
                  <ArrowUpRight className="size-4" aria-hidden="true" />
                </button>
              )
            }
            return (
              <a
                key={link.label}
                href={link.url}
                target="_blank"
                rel="noreferrer"
                className={className}
              >
                {link.label}
                <ArrowUpRight className="size-4" aria-hidden="true" />
              </a>
            )
          })}
        </div>
      </div>
    </div>
  )
}
