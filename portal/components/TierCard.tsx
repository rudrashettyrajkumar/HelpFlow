import type { LucideIcon } from 'lucide-react'

type Props = {
  icon: LucideIcon
  name: string
  tagline: string
  points: string[]
  highlighted?: boolean
}

/** One card of the three-tier explainer (spec Req 1, honest copy from
 * ARCHITECTURE §4.1 — Demo / Free BYOK / Paid BYOK). */
export function TierCard({ icon: Icon, name, tagline, points, highlighted }: Props) {
  return (
    <div
      className={`glass relative flex flex-col gap-4 rounded-3xl p-6 ${
        highlighted ? 'ring-2 ring-brand' : ''
      }`}
    >
      {highlighted && (
        <span className="absolute -top-3 left-6 rounded-full bg-brand-gradient px-3 py-1 text-[11px] font-bold text-white shadow-glow">
          MOST POPULAR
        </span>
      )}
      <span className="flex size-11 items-center justify-center rounded-2xl bg-brand-gradient text-white shadow-glow">
        <Icon className="size-5" aria-hidden="true" />
      </span>
      <div>
        <h3 className="text-lg font-extrabold">{name}</h3>
        <p className="mt-1 text-sm text-foreground-muted">{tagline}</p>
      </div>
      <ul className="space-y-2.5 text-sm">
        {points.map((point) => (
          <li key={point} className="flex items-start gap-2 text-foreground-muted">
            <span className="mt-1.5 size-1.5 shrink-0 rounded-full bg-brand" aria-hidden="true" />
            {point}
          </li>
        ))}
      </ul>
    </div>
  )
}
