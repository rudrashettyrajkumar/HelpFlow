import { useEffect, useRef, useState } from 'react'
import type { ConversationStatus } from '../api/types'

const API_URL = import.meta.env.VITE_API_URL as string

export type AgentReply = { createdAt: string; body: string }

/** `GET /chat/subscribe` — live human replies + status changes (spec E7 Req 6,
 * ARCHITECTURE §3.3). Uses the browser's native `EventSource` rather than a
 * hand-rolled fetch-stream: this endpoint takes no BYOK/auth headers, and
 * EventSource's built-in auto-reconnect already satisfies "never a raw error,
 * always recovers" (spec Req 7) for a GET-only, header-less stream.
 *
 * `list_messages_since` replays the FULL agent-message history on every fresh
 * connection (no `Last-Event-ID` resume on this endpoint, by backend design —
 * see `channels/subscribe.py`), so replies are de-duped here by `created_at`
 * (the wire shape carries no message id) before being handed to the caller. */
export function useConversationSubscribe(conversationId: string | null) {
  const [replies, setReplies] = useState<AgentReply[]>([])
  const [status, setStatus] = useState<ConversationStatus | null>(null)
  const seenRef = useRef<Set<string>>(new Set())

  useEffect(() => {
    if (!conversationId) return
    seenRef.current = new Set()
    setReplies([])
    setStatus(null)

    const source = new EventSource(
      `${API_URL}/chat/subscribe?conversation_id=${encodeURIComponent(conversationId)}`,
    )

    source.addEventListener('message', (evt) => {
      const data = JSON.parse((evt as MessageEvent).data) as {
        role: string
        body: string
        created_at: string
      }
      if (seenRef.current.has(data.created_at)) return
      seenRef.current.add(data.created_at)
      setReplies((prev) => [...prev, { createdAt: data.created_at, body: data.body }])
    })

    source.addEventListener('status', (evt) => {
      const data = JSON.parse((evt as MessageEvent).data) as { status: ConversationStatus }
      setStatus(data.status)
    })

    return () => source.close()
  }, [conversationId])

  return { replies, status }
}
