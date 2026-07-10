'use client'

import { useState } from 'react'
import { Loader2, Send } from 'lucide-react'

type Props = {
  disabled: boolean
  disabledReason?: string
  onSend: (body: string) => Promise<void>
}

export function ReplyBox({ disabled, disabledReason, onSend }: Props) {
  const [value, setValue] = useState('')
  const [sending, setSending] = useState(false)

  const send = async () => {
    if (!value.trim() || sending || disabled) return
    setSending(true)
    try {
      await onSend(value.trim())
      setValue('')
    } finally {
      setSending(false)
    }
  }

  return (
    <div className="border-t border-border p-3">
      {disabled && disabledReason && (
        <p className="mb-2 text-xs font-medium text-foreground-muted">{disabledReason}</p>
      )}
      <div className="flex items-end gap-2">
        <textarea
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault()
              send()
            }
          }}
          disabled={disabled || sending}
          rows={2}
          placeholder={disabled ? 'Claim this conversation to reply' : 'Reply to the customer…'}
          className="max-h-32 flex-1 resize-none rounded-xl border border-border bg-surface px-3.5 py-2.5 text-sm focus-visible:outline-none disabled:opacity-50"
        />
        <button
          onClick={send}
          disabled={disabled || sending || !value.trim()}
          aria-label="Send reply"
          className="flex size-11 shrink-0 cursor-pointer items-center justify-center rounded-xl bg-brand-gradient text-white shadow-glow transition-transform hover:scale-105 disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:scale-100"
        >
          {sending ? (
            <Loader2 className="size-4 animate-spin" aria-hidden="true" />
          ) : (
            <Send className="size-4" aria-hidden="true" />
          )}
        </button>
      </div>
    </div>
  )
}
