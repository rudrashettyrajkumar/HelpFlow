import { Bot, Check, HeartHandshake, UserRound, XCircle } from 'lucide-react'
import type { VConversation } from '@/lib/supabase'

// Shared stage colors/labels with the widget's own status handling (spec E9
// Req 5: "consistent stage colors with the widget") — the frozen enum from
// helpflow-schema (ai_handling/needs_human/human_assigned/resolved/abandoned).
const LOOK: Record<
  VConversation['status'],
  { label: string; icon: typeof Bot; cls: string }
> = {
  ai_handling: { label: 'AI handling', icon: Bot, cls: 'bg-brand/15 text-brand' },
  needs_human: { label: 'Needs human', icon: HeartHandshake, cls: 'bg-destructive/15 text-destructive' },
  human_assigned: { label: 'Assigned', icon: UserRound, cls: 'bg-success/15 text-success' },
  resolved: { label: 'Resolved', icon: Check, cls: 'bg-foreground-muted/15 text-foreground-muted' },
  abandoned: { label: 'Abandoned', icon: XCircle, cls: 'bg-foreground-muted/15 text-foreground-muted' },
}

export function StageChip({ status, loud = false }: { status: VConversation['status']; loud?: boolean }) {
  const { label, icon: Icon, cls } = LOOK[status]
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-bold ${cls} ${
        loud && status === 'needs_human' ? 'animate-pulse' : ''
      }`}
    >
      <Icon className="size-3.5" aria-hidden="true" />
      {label}
    </span>
  )
}
