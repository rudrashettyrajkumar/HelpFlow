'use client'

import { useState } from 'react'
import { ChevronDown, FileQuestion, Lightbulb } from 'lucide-react'
import { Glass } from './Glass'
import type { VGapCluster } from '@/lib/supabase'

/** The Gap Report — "docs to write next", ranked by frequency (dataviz
 * skill: compare-magnitude job → sequential single hue, direct labels,
 * selective — spec E9 Req 4, the analytics hero). Bars are relative to the
 * top theme, not an absolute scale: the story is "write this doc first",
 * not exact counts. */
export function GapReport({ clusters }: { clusters: VGapCluster[] }) {
  const [openTheme, setOpenTheme] = useState<string | null>(null)
  const maxFrequency = Math.max(1, ...clusters.map((c) => c.frequency))

  return (
    <Glass strong className="rounded-3xl p-5 sm:p-6">
      <div className="mb-4 flex items-center gap-2">
        <span className="flex size-9 items-center justify-center rounded-xl bg-brand-gradient text-white shadow-glow">
          <Lightbulb className="size-4" aria-hidden="true" />
        </span>
        <div>
          <p className="text-sm font-bold">Gap Report — docs to write next</p>
          <p className="text-xs text-foreground-muted">
            Questions your AI couldn&apos;t answer confidently, clustered into themes.
          </p>
        </div>
      </div>

      {clusters.length === 0 && (
        <div className="flex flex-col items-center gap-2 py-10 text-center">
          <FileQuestion className="size-8 text-foreground-muted" aria-hidden="true" />
          <p className="text-sm text-foreground-muted">
            No gaps clustered yet — this fills in once visitors ask questions your docs
            don&apos;t cover.
          </p>
        </div>
      )}

      <ol className="space-y-2">
        {clusters.map((cluster, i) => {
          const open = openTheme === cluster.theme
          const pct = Math.max(6, (cluster.frequency / maxFrequency) * 100)
          return (
            <li key={cluster.theme} className="rounded-2xl border border-border">
              <button
                onClick={() => setOpenTheme(open ? null : cluster.theme)}
                aria-expanded={open}
                className="flex w-full cursor-pointer items-center gap-3 px-3.5 py-3 text-left"
              >
                <span className="flex size-6 shrink-0 items-center justify-center rounded-full bg-surface-muted text-[11px] font-bold text-foreground-muted">
                  {i + 1}
                </span>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center justify-between gap-2">
                    <p className="truncate text-sm font-semibold">{cluster.theme}</p>
                    <span className="shrink-0 text-xs font-bold text-foreground-muted">
                      {cluster.frequency}×
                    </span>
                  </div>
                  <div className="mt-1.5 h-1.5 w-full overflow-hidden rounded-full bg-surface-muted">
                    <div
                      className="h-full rounded-full bg-brand-gradient"
                      style={{ width: `${pct}%` }}
                    />
                  </div>
                </div>
                <ChevronDown
                  className={`size-4 shrink-0 text-foreground-muted transition-transform ${open ? 'rotate-180' : ''}`}
                  aria-hidden="true"
                />
              </button>
              {open && cluster.example_questions.length > 0 && (
                <ul className="space-y-1.5 border-t border-border px-3.5 py-3 pl-11">
                  {cluster.example_questions.map((q) => (
                    <li key={q} className="text-xs italic text-foreground-muted">
                      &ldquo;{q}&rdquo;
                    </li>
                  ))}
                </ul>
              )}
            </li>
          )
        })}
      </ol>
    </Glass>
  )
}
