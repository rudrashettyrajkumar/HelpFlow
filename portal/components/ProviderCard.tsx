import { Brain, Check, Gem, Route, Zap, type LucideIcon } from 'lucide-react'
import type { ProviderInfo } from '@/lib/types'

const PROVIDER_LOOK: Record<string, { icon: LucideIcon; gradient: string }> = {
  groq: { icon: Zap, gradient: 'from-amber-400 to-orange-500' },
  openrouter: { icon: Route, gradient: 'from-indigo-400 to-violet-500' },
  openai: { icon: Zap, gradient: 'from-emerald-400 to-teal-500' },
  anthropic: { icon: Brain, gradient: 'from-orange-400 to-rose-500' },
  gemini: { icon: Gem, gradient: 'from-sky-400 to-cyan-500' },
}

const KIND_BADGE: Record<ProviderInfo['kind'], { label: string; cls: string }> = {
  free: { label: '100% FREE', cls: 'bg-success/15 text-success' },
  freemium: { label: 'FREE TIER', cls: 'bg-brand/15 text-brand' },
  paid: { label: 'PAID KEY', cls: 'bg-foreground-muted/15 text-foreground-muted' },
}

type Props = {
  provider: ProviderInfo
  selected: boolean
  onSelect: () => void
}

/** One provider tile in the picker grid — rendered ONLY from `GET
 * /api/models` (spec Req 4: "zero hardcoded models in the frontend"). */
export function ProviderCard({ provider, selected, onSelect }: Props) {
  const look = PROVIDER_LOOK[provider.id] ?? PROVIDER_LOOK.openrouter
  const Icon = look.icon
  return (
    <button
      type="button"
      onClick={onSelect}
      aria-pressed={selected}
      className={`glass relative flex cursor-pointer flex-col items-center gap-1.5 rounded-2xl px-2 py-3.5 transition-all hover:-translate-y-0.5 ${
        selected ? 'ring-2 ring-brand' : 'hover:border-brand/40'
      }`}
    >
      {selected && (
        <span className="absolute right-2 top-2 flex size-4 items-center justify-center rounded-full bg-brand text-white">
          <Check className="size-3" aria-hidden="true" />
        </span>
      )}
      <span
        className={`flex size-9 items-center justify-center rounded-xl bg-gradient-to-br ${look.gradient} text-white`}
      >
        <Icon className="size-5" aria-hidden="true" />
      </span>
      <span className="text-xs font-bold">{provider.name}</span>
      <span
        className={`rounded-full px-1.5 py-0.5 text-[9px] font-extrabold tracking-wide ${KIND_BADGE[provider.kind].cls}`}
      >
        {KIND_BADGE[provider.kind].label}
      </span>
    </button>
  )
}
