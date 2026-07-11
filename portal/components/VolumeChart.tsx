'use client'

import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { Glass } from './Glass'

type Point = { day: string; count: number }

// Single series → sequential/one hue, no legend needed (dataviz skill: "a
// single series needs no legend box — the title already says what's plotted").
const BAR_COLOR = 'rgb(99 102 241)' // --brand

type TooltipProps = {
  active?: boolean
  payload?: { value: number }[]
  label?: string
}

function ChartTooltip({ active, payload, label }: TooltipProps) {
  if (!active || !payload?.length) return null
  return (
    <div className="glass-strong rounded-xl px-3 py-2 text-xs shadow-soft">
      <p className="font-semibold">{label}</p>
      <p className="text-foreground-muted">{payload[0].value} conversations</p>
    </div>
  )
}

/** Conversations/day — trend over time, one series (spec E9 Req 4). Bars
 * capped at 24px, 4px rounded tops, hairline recessive gridlines, hover
 * tooltip (dataviz skill marks-and-anatomy.md / interaction.md). */
export function VolumeChart({ data }: { data: Point[] }) {
  return (
    <Glass strong className="rounded-3xl p-5">
      <p className="mb-4 text-sm font-bold">Conversation volume (last 14 days)</p>
      <div className="h-56">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 4, right: 4, bottom: 0, left: -20 }}>
            <CartesianGrid vertical={false} stroke="rgb(226 228 240)" strokeDasharray="0" />
            <XAxis
              dataKey="day"
              tick={{ fontSize: 11, fill: 'rgb(100 116 139)' }}
              axisLine={{ stroke: 'rgb(226 228 240)' }}
              tickLine={false}
            />
            <YAxis
              tick={{ fontSize: 11, fill: 'rgb(100 116 139)' }}
              axisLine={false}
              tickLine={false}
              allowDecimals={false}
              width={28}
            />
            <Tooltip content={<ChartTooltip />} cursor={{ fill: 'rgb(99 102 241 / 0.08)' }} />
            <Bar dataKey="count" fill={BAR_COLOR} radius={[4, 4, 0, 0]} maxBarSize={24} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </Glass>
  )
}
