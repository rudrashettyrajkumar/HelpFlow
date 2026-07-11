import { useEffect, useRef } from 'react'
import { ExternalLink, X } from 'lucide-react'
import type { SourceItem } from '../api/types'

type Props = {
  sources: SourceItem[]
  activeN: number | null
  onClose: () => void
}

/** Slide-up sheet (ported from DocChat's `SourcesDrawer`) showing a citation's
 * page title + source URL link (spec Req 2: "chip → sources drawer (page
 * title + source URL link)"). */
export function SourcesDrawer({ sources, activeN, onClose }: Props) {
  const open = activeN !== null
  const refs = useRef<Record<number, HTMLDivElement | null>>({})

  useEffect(() => {
    if (activeN !== null) {
      refs.current[activeN]?.scrollIntoView({ block: 'center', behavior: 'smooth' })
    }
  }, [activeN])

  return (
    <>
      {open && (
        <div
          className="absolute inset-0 z-40 bg-black/40 transition-opacity duration-300"
          onClick={onClose}
          aria-hidden="true"
        />
      )}
      <div
        role="dialog"
        aria-label="Sources"
        aria-hidden={!open}
        className={`glass-strong absolute inset-x-0 bottom-0 z-50 flex max-h-[70%] flex-col rounded-t-3xl transition-transform duration-300 ease-out ${
          open ? 'translate-y-0' : 'translate-y-full'
        }`}
      >
        <div className="flex items-center justify-between border-b border-border px-4 py-3">
          <h2 className="text-sm font-semibold">Sources</h2>
          <button
            onClick={onClose}
            aria-label="Close sources"
            className="flex size-9 cursor-pointer items-center justify-center rounded-md text-foreground-muted hover:text-foreground"
          >
            <X className="size-4" aria-hidden="true" />
          </button>
        </div>
        <div className="flex-1 space-y-2 overflow-y-auto p-3">
          {sources.map((source) => (
            <div
              key={source.n}
              ref={(el) => {
                refs.current[source.n] = el
              }}
              className={`rounded-xl border p-3 transition-colors duration-300 ${
                source.n === activeN ? 'border-brand/40 bg-brand/10' : 'border-border'
              } ${source.cited ? '' : 'opacity-50'}`}
            >
              <div className="mb-1 flex items-center justify-between gap-2">
                <p className="truncate text-sm font-medium" title={source.page_title}>
                  [{source.n}] {source.page_title || source.source_url}
                </p>
                {!source.cited && (
                  <span className="shrink-0 text-[11px] text-foreground-muted">not cited</span>
                )}
              </div>
              <p className="mb-1.5 line-clamp-2 text-xs text-foreground-muted">{source.snippet}</p>
              <a
                href={source.source_url}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1 text-xs text-brand hover:underline"
              >
                {source.source_url}
                <ExternalLink className="size-3" aria-hidden="true" />
              </a>
            </div>
          ))}
        </div>
      </div>
    </>
  )
}
