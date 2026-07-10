import { Clock, MessagesSquare, TrendingUp, UserRound } from 'lucide-react'
import { Glass } from './Glass'

type Props = {
  total: number
  deflectionPct: number | null
  escalated: number
  avgFirstResponseMinutes: number | null
}

function StatTile({
  icon: Icon,
  label,
  value,
}: {
  icon: typeof Clock
  label: string
  value: string
}) {
  return (
    <Glass className="flex flex-col gap-2 rounded-2xl p-4">
      <span className="flex size-9 items-center justify-center rounded-xl bg-brand-gradient text-white">
        <Icon className="size-4" aria-hidden="true" />
      </span>
      <p className="text-2xl font-bold leading-none">{value}</p>
      <p className="text-xs text-foreground-muted">{label}</p>
    </Glass>
  )
}

/** Stat-tile KPI row (dataviz skill: "a handful of headline numbers → a KPI
 * row of stat tiles", never a chart) — spec E9 Req 4. */
export function KpiTiles({ total, deflectionPct, escalated, avgFirstResponseMinutes }: Props) {
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
      <StatTile icon={MessagesSquare} label="Conversations" value={total.toLocaleString()} />
      <StatTile
        icon={TrendingUp}
        label="Deflection rate"
        value={deflectionPct === null ? '—' : `${deflectionPct.toFixed(0)}%`}
      />
      <StatTile icon={UserRound} label="Escalations" value={escalated.toLocaleString()} />
      <StatTile
        icon={Clock}
        label="Avg. first response"
        value={avgFirstResponseMinutes === null ? '—' : `${avgFirstResponseMinutes.toFixed(0)}m`}
      />
    </div>
  )
}
