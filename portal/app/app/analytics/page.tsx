'use client'

import { useEffect, useState } from 'react'
import { AlertTriangle, Loader2 } from 'lucide-react'
import { GapReport } from '@/components/GapReport'
import { Glass } from '@/components/Glass'
import { KpiTiles } from '@/components/KpiTiles'
import { VolumeChart } from '@/components/VolumeChart'
import { WorkspacePicker } from '@/components/WorkspacePicker'
import {
  fetchConversations,
  fetchEvents,
  fetchFunnel,
  fetchGapClusters,
} from '@/lib/supabase'
import type { VConversation, VEvent, VFunnel, VGapCluster } from '@/lib/supabase'
import { useActiveWorkspace } from '@/lib/useActiveWorkspace'

const VOLUME_WINDOW_DAYS = 14

function bucketByDay(conversations: VConversation[]): { day: string; count: number }[] {
  const today = new Date()
  const buckets = new Map<string, number>()
  for (let i = VOLUME_WINDOW_DAYS - 1; i >= 0; i--) {
    const d = new Date(today)
    d.setDate(d.getDate() - i)
    buckets.set(d.toISOString().slice(0, 10), 0)
  }
  for (const c of conversations) {
    const key = c.created_at.slice(0, 10)
    if (buckets.has(key)) buckets.set(key, (buckets.get(key) ?? 0) + 1)
  }
  return [...buckets.entries()].map(([day, count]) => ({
    day: new Date(day).toLocaleDateString([], { month: 'short', day: 'numeric' }),
    count,
  }))
}

/** Average minutes from `escalated` to the first `agent_joined` per
 * conversation — no view exposes this directly, so it's computed here from
 * `v_events` (spec E9 Req 4's 4th KPI tile, honestly derived from existing
 * data rather than a new SQL column). */
function avgFirstResponseMinutes(events: VEvent[]): number | null {
  const escalatedAt = new Map<string, number>()
  const joinedAt = new Map<string, number>()
  for (const e of events) {
    const t = new Date(e.created_at).getTime()
    if (e.type === 'escalated' && !escalatedAt.has(e.conversation_id)) {
      escalatedAt.set(e.conversation_id, t)
    }
    if (e.type === 'agent_joined' && !joinedAt.has(e.conversation_id)) {
      joinedAt.set(e.conversation_id, t)
    }
  }
  const deltas: number[] = []
  for (const [conversationId, start] of escalatedAt) {
    const end = joinedAt.get(conversationId)
    if (end !== undefined && end >= start) deltas.push((end - start) / 60_000)
  }
  if (deltas.length === 0) return null
  return deltas.reduce((a, b) => a + b, 0) / deltas.length
}

export default function AnalyticsPage() {
  const { workspaces, activeId, setActiveId, error: wsError } = useActiveWorkspace()
  const [conversations, setConversations] = useState<VConversation[] | null>(null)
  const [funnel, setFunnel] = useState<VFunnel | null>(null)
  const [events, setEvents] = useState<VEvent[] | null>(null)
  const [clusters, setClusters] = useState<VGapCluster[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!activeId) return
    setConversations(null)
    setFunnel(null)
    setEvents(null)
    setClusters(null)
    Promise.all([
      fetchConversations(activeId),
      fetchFunnel(activeId),
      fetchEvents(activeId),
      fetchGapClusters(activeId),
    ])
      .then(([c, f, e, g]) => {
        setConversations(c)
        setFunnel(f)
        setEvents(e)
        setClusters(g)
      })
      .catch(() => setError("Couldn't load analytics — check the Supabase anon key config."))
  }, [activeId])

  if (wsError) {
    return (
      <Glass className="flex items-center gap-2 rounded-2xl px-4 py-3 text-sm text-destructive">
        <AlertTriangle className="size-4 shrink-0" aria-hidden="true" /> {wsError}
      </Glass>
    )
  }

  if (!workspaces) {
    return (
      <div className="flex items-center justify-center gap-2 py-24 text-sm text-foreground-muted">
        <Loader2 className="size-4 animate-spin" aria-hidden="true" /> Loading…
      </div>
    )
  }

  if (workspaces.length === 0) {
    return (
      <Glass className="rounded-3xl px-6 py-16 text-center text-sm text-foreground-muted">
        No workspaces yet — create one first.
      </Glass>
    )
  }

  const loading = !conversations || !events || !clusters

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-extrabold tracking-tight">Analytics</h1>
        <WorkspacePicker workspaces={workspaces} activeId={activeId} onChange={setActiveId} />
      </div>

      {error && (
        <Glass className="flex items-center gap-2 rounded-2xl px-4 py-3 text-sm text-destructive">
          <AlertTriangle className="size-4 shrink-0" aria-hidden="true" /> {error}
        </Glass>
      )}

      {loading && !error && (
        <div className="flex items-center justify-center gap-2 py-24 text-sm text-foreground-muted">
          <Loader2 className="size-4 animate-spin" aria-hidden="true" /> Loading analytics…
        </div>
      )}

      {!loading && !error && conversations && events && clusters && (
        <>
          <KpiTiles
            total={funnel?.total ?? conversations.length}
            deflectionPct={funnel?.deflection_rate != null ? funnel.deflection_rate * 100 : null}
            escalated={funnel?.escalated ?? 0}
            avgFirstResponseMinutes={avgFirstResponseMinutes(events)}
          />
          <VolumeChart data={bucketByDay(conversations)} />
          <GapReport clusters={clusters} />
        </>
      )}
    </div>
  )
}
