'use client'

import { useEffect, useState } from 'react'
import { Check, Sparkles } from 'lucide-react'
import { fetchDemoBudget } from '@/lib/api'
import type { DemoBudget } from '@/lib/types'

type Props = {
  selected: boolean
  onSelect: () => void
}

/** The demo-mode card at the top of Model Studio (spec Req 4): "today's
 * remaining shared budget" + the free-tier honesty copy (ARCHITECTURE §4.3).
 * A fetch failure degrades to hiding the live numbers, never a broken card. */
export function DemoBudgetCard({ selected, onSelect }: Props) {
  const [budget, setBudget] = useState<DemoBudget | null>(null)

  useEffect(() => {
    fetchDemoBudget()
      .then(setBudget)
      .catch(() => setBudget(null))
  }, [])

  return (
    <button
      type="button"
      onClick={onSelect}
      aria-pressed={selected}
      className={`glass flex w-full cursor-pointer items-center justify-between gap-3 rounded-2xl px-4 py-3.5 text-left transition-colors ${
        selected ? 'ring-2 ring-brand' : 'hover:border-brand/40'
      }`}
    >
      <span>
        <span className="flex items-center gap-2 text-sm font-bold">
          <Sparkles className="size-4 text-brand" aria-hidden="true" />
          Demo mode — no key needed
        </span>
        <span className="mt-0.5 block text-xs text-foreground-muted">
          Free-tier open-source models (Groq + OpenRouter), shared daily quota — honest
          when it runs out. Bring your own key for reliable, unshared access.
        </span>
        {budget && (
          <span className="mt-1.5 block text-[11px] font-semibold text-foreground-muted">
            {budget.chat.remaining}/{budget.chat.cap} chat · {budget.embed.remaining}/
            {budget.embed.cap} embed remaining today
          </span>
        )}
      </span>
      {selected && <Check className="size-5 shrink-0 text-brand" aria-hidden="true" />}
    </button>
  )
}
