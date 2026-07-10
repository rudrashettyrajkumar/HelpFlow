'use client'

import { useCallback, useEffect, useState } from 'react'
import { AlertTriangle, Inbox as InboxIcon, Loader2 } from 'lucide-react'
import { ConversationView } from '@/components/ConversationView'
import { Glass } from '@/components/Glass'
import { Inbox } from '@/components/Inbox'
import { WorkspacePicker } from '@/components/WorkspacePicker'
import { fetchConversations } from '@/lib/supabase'
import type { VConversation } from '@/lib/supabase'
import { useActiveWorkspace } from '@/lib/useActiveWorkspace'

const POLL_MS = 10_000 // spec E9 Req 2: "new escalations arrive live (~10s poll)"

type Filter = 'all' | 'needs_human' | 'human_assigned' | 'resolved'

export default function InboxPage() {
  const { workspaces, active, activeId, setActiveId, error: wsError } = useActiveWorkspace()
  const [conversations, setConversations] = useState<VConversation[] | null>(null)
  const [convoError, setConvoError] = useState<string | null>(null)
  const [filter, setFilter] = useState<Filter>('all')
  const [selectedId, setSelectedId] = useState<string | null>(null)

  const refresh = useCallback(() => {
    if (!activeId) return
    fetchConversations(activeId)
      .then((rows) => {
        setConversations(rows)
        setConvoError(null)
      })
      .catch(() => setConvoError("Couldn't load conversations — check the Supabase anon key config."))
  }, [activeId])

  useEffect(() => {
    if (!activeId) return
    refresh()
    const interval = setInterval(refresh, POLL_MS)
    return () => clearInterval(interval)
  }, [activeId, refresh])

  const selected = conversations?.find((c) => c.id === selectedId) ?? null

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
      <Glass className="flex flex-col items-center gap-2 rounded-3xl px-6 py-16 text-center">
        <InboxIcon className="size-8 text-foreground-muted" aria-hidden="true" />
        <p className="text-sm font-medium">No workspaces yet — create one first.</p>
      </Glass>
    )
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-extrabold tracking-tight">Inbox</h1>
        <WorkspacePicker workspaces={workspaces} activeId={activeId} onChange={setActiveId} />
      </div>

      {convoError && (
        <Glass className="flex items-center gap-2 rounded-2xl px-4 py-3 text-sm text-destructive">
          <AlertTriangle className="size-4 shrink-0" aria-hidden="true" /> {convoError}
        </Glass>
      )}

      {!convoError && !conversations && (
        <div className="flex items-center justify-center gap-2 py-24 text-sm text-foreground-muted">
          <Loader2 className="size-4 animate-spin" aria-hidden="true" /> Loading conversations…
        </div>
      )}

      {!convoError && conversations && (
        <Glass strong className="grid h-[70vh] grid-cols-1 overflow-hidden rounded-3xl md:grid-cols-[340px_1fr]">
          <div className="border-b border-border md:border-b-0 md:border-r">
            <Inbox
              conversations={conversations}
              filter={filter}
              onFilterChange={setFilter}
              activeConversationId={selectedId}
              onSelect={setSelectedId}
            />
          </div>
          <div className="hidden md:block">
            {selected && active ? (
              <ConversationView tenantId={active.id} conversation={selected} onChanged={refresh} />
            ) : (
              <div className="flex h-full items-center justify-center text-sm text-foreground-muted">
                Select a conversation
              </div>
            )}
          </div>
        </Glass>
      )}

      {/* Mobile: detail replaces the list when a conversation is selected */}
      {selected && active && (
        <Glass strong className="fixed inset-0 z-40 flex flex-col rounded-none md:hidden">
          <button
            onClick={() => setSelectedId(null)}
            className="border-b border-border px-4 py-3 text-left text-sm font-semibold text-brand"
          >
            ← Back to inbox
          </button>
          <ConversationView tenantId={active.id} conversation={selected} onChanged={refresh} />
        </Glass>
      )}
    </div>
  )
}
