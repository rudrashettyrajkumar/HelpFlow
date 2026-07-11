import { Mail } from 'lucide-react'
import { StageChip } from './StageChip'
import type { VConversation } from '@/lib/supabase'

type Filter = 'all' | 'needs_human' | 'human_assigned' | 'resolved'

const FILTERS: { id: Filter; label: string }[] = [
  { id: 'all', label: 'All' },
  { id: 'needs_human', label: 'Needs human' },
  { id: 'human_assigned', label: 'Assigned' },
  { id: 'resolved', label: 'Resolved' },
]

type Props = {
  conversations: VConversation[]
  filter: Filter
  onFilterChange: (f: Filter) => void
  activeConversationId: string | null
  onSelect: (id: string) => void
}

/** The conversation list — `needs_human` pinned + loud (spec E9 Req 2). */
export function Inbox({ conversations, filter, onFilterChange, activeConversationId, onSelect }: Props) {
  const filtered =
    filter === 'all' ? conversations : conversations.filter((c) => c.status === filter)

  // needs_human always floats to the top, regardless of the selected filter/sort.
  const sorted = [...filtered].sort((a, b) => {
    if (a.status === 'needs_human' && b.status !== 'needs_human') return -1
    if (b.status === 'needs_human' && a.status !== 'needs_human') return 1
    return new Date(b.last_activity_at).getTime() - new Date(a.last_activity_at).getTime()
  })

  return (
    <div className="flex h-full flex-col">
      <div className="flex gap-1.5 border-b border-border p-2">
        {FILTERS.map((f) => (
          <button
            key={f.id}
            onClick={() => onFilterChange(f.id)}
            className={`cursor-pointer rounded-lg px-2.5 py-1.5 text-xs font-semibold transition-colors ${
              filter === f.id ? 'bg-brand/15 text-brand' : 'text-foreground-muted hover:text-foreground'
            }`}
          >
            {f.label}
          </button>
        ))}
      </div>

      <div className="flex-1 overflow-y-auto">
        {sorted.length === 0 && (
          <p className="p-6 text-center text-sm text-foreground-muted">No conversations here yet.</p>
        )}
        {sorted.map((c) => (
          <button
            key={c.id}
            onClick={() => onSelect(c.id)}
            className={`flex w-full flex-col gap-1.5 border-b border-border px-4 py-3 text-left transition-colors hover:bg-surface-muted ${
              c.id === activeConversationId ? 'bg-brand/5' : ''
            }`}
          >
            <div className="flex items-center justify-between gap-2">
              <StageChip status={c.status} loud />
              <span className="text-[11px] text-foreground-muted">
                {new Date(c.last_activity_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
              </span>
            </div>
            <p className="truncate text-sm font-medium">{c.last_message_preview || '(no messages yet)'}</p>
            <div className="flex items-center gap-2 text-[11px] text-foreground-muted">
              {c.customer_email && (
                <span className="flex items-center gap-1">
                  <Mail className="size-3" aria-hidden="true" />
                  {c.customer_email}
                </span>
              )}
              {c.escalation_reason && <span>· {c.escalation_reason.replace(/_/g, ' ')}</span>}
            </div>
          </button>
        ))}
      </div>
    </div>
  )
}
