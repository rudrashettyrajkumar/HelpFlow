'use client'

import { useEffect, useState } from 'react'
import { AlertTriangle, CircleUserRound, HandHelping, Loader2, UserCheck } from 'lucide-react'
import { ReplyBox } from './ReplyBox'
import { StageChip } from './StageChip'
import {
  claimConversation,
  fetchConversationMessages,
  handbackConversation,
  replyToConversation,
  resolveConversation,
} from '@/lib/api'
import type { VConversation } from '@/lib/supabase'
import type { ConversationMessage } from '@/lib/types'

type Props = {
  tenantId: string
  conversation: VConversation
  onChanged: () => void
}

const ROLE_LOOK: Record<string, string> = {
  user: 'ml-auto bg-brand-gradient text-white',
  assistant: 'mr-auto border border-border bg-surface',
  agent: 'mr-auto border-l-2 border-success bg-surface',
  system: 'mx-auto bg-surface-muted text-foreground-muted text-xs',
}

export function ConversationView({ tenantId, conversation, onChanged }: Props) {
  const [messages, setMessages] = useState<ConversationMessage[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [actionBusy, setActionBusy] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)

  useEffect(() => {
    setMessages(null)
    setError(null)
    fetchConversationMessages(tenantId, conversation.id)
      .then(setMessages)
      .catch(() => setError("Couldn't load this conversation. Try again."))
  }, [tenantId, conversation.id])

  const runAction = async (fn: () => Promise<unknown>) => {
    setActionBusy(true)
    setActionError(null)
    try {
      await fn()
      onChanged()
    } catch {
      setActionError('That action failed — someone may have already moved this conversation.')
    } finally {
      setActionBusy(false)
    }
  }

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between gap-3 border-b border-border px-4 py-3">
        <div>
          <div className="flex items-center gap-2">
            <StageChip status={conversation.status} />
            {conversation.assigned_agent && (
              <span className="flex items-center gap-1 text-xs text-foreground-muted">
                <CircleUserRound className="size-3.5" aria-hidden="true" />
                {conversation.assigned_agent}
              </span>
            )}
          </div>
          {conversation.escalation_reason && (
            <p className="mt-1 text-xs text-foreground-muted">
              Escalated: {conversation.escalation_reason.replace(/_/g, ' ')}
              {conversation.customer_email && ` · ${conversation.customer_email}`}
            </p>
          )}
        </div>
        <div className="flex shrink-0 gap-2">
          {conversation.status === 'needs_human' && (
            <button
              onClick={() => runAction(() => claimConversation(tenantId, conversation.id))}
              disabled={actionBusy}
              className="flex min-h-[36px] cursor-pointer items-center gap-1.5 rounded-xl bg-brand-gradient px-3 text-xs font-bold text-white shadow-glow disabled:opacity-60"
            >
              <HandHelping className="size-3.5" aria-hidden="true" /> Claim
            </button>
          )}
          {conversation.status === 'human_assigned' && (
            <>
              <button
                onClick={() => runAction(() => handbackConversation(tenantId, conversation.id))}
                disabled={actionBusy}
                className="flex min-h-[36px] cursor-pointer items-center gap-1.5 rounded-xl border border-border px-3 text-xs font-semibold disabled:opacity-60"
              >
                Hand back to AI
              </button>
              <button
                onClick={() => runAction(() => resolveConversation(tenantId, conversation.id))}
                disabled={actionBusy}
                className="flex min-h-[36px] cursor-pointer items-center gap-1.5 rounded-xl bg-success px-3 text-xs font-bold text-white disabled:opacity-60"
              >
                <UserCheck className="size-3.5" aria-hidden="true" /> Resolve
              </button>
            </>
          )}
        </div>
      </div>

      {conversation.status === 'human_assigned' && (
        <p className="flex items-center gap-1.5 bg-success/10 px-4 py-1.5 text-[11px] font-medium text-success">
          The AI is paused on this conversation — only your replies reach the customer.
        </p>
      )}

      {actionError && (
        <p className="flex items-center gap-1.5 bg-destructive/10 px-4 py-1.5 text-[11px] font-medium text-destructive">
          <AlertTriangle className="size-3.5" aria-hidden="true" /> {actionError}
        </p>
      )}

      <div className="flex-1 space-y-3 overflow-y-auto p-4">
        {error && <p className="text-sm text-destructive">{error}</p>}
        {!messages && !error && (
          <div className="flex items-center justify-center gap-2 py-16 text-sm text-foreground-muted">
            <Loader2 className="size-4 animate-spin" aria-hidden="true" /> Loading transcript…
          </div>
        )}
        {messages?.map((m) => (
          <div key={m.id} className={`max-w-[80%] rounded-2xl px-3.5 py-2 text-sm ${ROLE_LOOK[m.role]}`}>
            {m.role === 'agent' && <p className="mb-0.5 text-[10px] font-bold uppercase text-success">Agent</p>}
            {m.body}
          </div>
        ))}
      </div>

      <ReplyBox
        disabled={conversation.status !== 'human_assigned' || actionBusy}
        disabledReason={
          conversation.status === 'needs_human' ? 'Claim this conversation to reply.' : undefined
        }
        onSend={async (body) => {
          await replyToConversation(tenantId, conversation.id, body)
          setMessages((prev) => [
            ...(prev ?? []),
            {
              id: `local-${Date.now()}`,
              role: 'agent',
              body,
              citations: [],
              confidence: null,
              created_at: new Date().toISOString(),
            },
          ])
          onChanged()
        }}
      />
    </div>
  )
}
