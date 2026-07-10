import { useCallback, useRef, useState } from 'react'
import { streamChat } from '../api/client'
import { ApiError } from '../api/types'
import type { ChatItem } from '../api/types'
import { loadConversationId, saveConversationId } from '../lib/conversation'

const BACKOFF_MS = [1000, 2000, 4000, 8000]
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms))

const RATE_LIMIT_MESSAGE =
  "You're sending messages a little fast — give it a moment and try again."
const GENERIC_ERROR_MESSAGE = 'Something went wrong. Please try again.'
const CONNECTION_LOST_MESSAGE = 'Connection lost. Please try again.'

/** Streams one turn of `/chat/stream` into `items` (port of DocChat's
 * `useChatStream`, extended for HelpFlow's richer event vocabulary: sources,
 * handoff, human_turn, and the additive `notice` — spec E7 Req 2/4/5/7). */
export function useChatStream(widgetKey: string) {
  const [items, setItems] = useState<ChatItem[]>([])
  const [conversationId, setConversationId] = useState<string | null>(() =>
    loadConversationId(widgetKey),
  )
  const [isBusy, setIsBusy] = useState(false)
  const controllerRef = useRef<AbortController | null>(null)

  const patchItem = useCallback((id: string, patch: Partial<ChatItem>) => {
    setItems((prev) => prev.map((it) => (it.id === id ? ({ ...it, ...patch } as ChatItem) : it)))
  }, [])

  const removeItem = useCallback((id: string) => {
    setItems((prev) => prev.filter((it) => it.id !== id))
  }, [])

  /** Adopts the server-minted id of a brand-new conversation (the request
   * carries `conversation_id: null` until the first `done` event confirms
   * it — `/chat/stream`'s SSE frames only started carrying it via spec E7's
   * flagged `done` payload widening). */
  const adoptConversationId = useCallback(
    (id: string) => {
      setConversationId((prev) => {
        if (prev === id) return prev
        saveConversationId(widgetKey, id)
        return id
      })
    },
    [widgetKey],
  )

  const runTurn = useCallback(
    async (assistantId: string, message: string, attempt: number) => {
      const controller = new AbortController()
      controllerRef.current = controller
      let lastSeq = -1
      let sawFirstEvent = false
      let convertedAway = false // notice/human_turn swapped the placeholder for something else

      patchItem(assistantId, { streamState: 'streaming', text: '', sources: [] } as never)

      try {
        for await (const event of streamChat(widgetKey, conversationId, message, controller.signal)) {
          if (!sawFirstEvent) {
            sawFirstEvent = true
            if (event.type === 'human_turn') {
              // AI never talks over a human (invariant #5) — the assistant
              // placeholder never should have rendered a bubble at all.
              removeItem(assistantId)
              convertedAway = true
              return
            }
          }

          if (event.type === 'token') {
            if (event.seq > lastSeq) {
              lastSeq = event.seq
              setItems((prev) =>
                prev.map((it) =>
                  it.id === assistantId && it.kind === 'assistant'
                    ? { ...it, text: it.text + event.t }
                    : it,
                ),
              )
            }
          } else if (event.type === 'sources') {
            patchItem(assistantId, { sources: event.sources } as never)
          } else if (event.type === 'notice') {
            setItems((prev) =>
              prev.map((it) =>
                it.id === assistantId
                  ? { id: assistantId, kind: 'notice', code: event.code, message: event.message, links: event.links }
                  : it,
              ),
            )
            convertedAway = true
          } else if (event.type === 'handoff') {
            setItems((prev) => [
              ...prev,
              { id: `${assistantId}-handoff`, kind: 'handoff', reason: event.reason },
            ])
          } else if (event.type === 'error') {
            patchItem(assistantId, {
              streamState: 'error',
              errorDetail: GENERIC_ERROR_MESSAGE,
            } as never)
            return
          } else if (event.type === 'done') {
            adoptConversationId(event.conversation_id)
            if (!convertedAway) patchItem(assistantId, { streamState: 'done' } as never)
            return
          }
        }
      } catch (err) {
        if (err instanceof ApiError) {
          patchItem(assistantId, {
            streamState: err.status === 429 ? 'rate_limited' : 'error',
            errorDetail: err.status === 429 ? RATE_LIMIT_MESSAGE : GENERIC_ERROR_MESSAGE,
          } as never)
          return
        }
        if (err instanceof DOMException && err.name === 'AbortError') return

        // A real network drop (devtools-offline, dropped wifi) — reconnect by
        // re-running the SAME turn, never surfacing a raw error (spec Req 7).
        if (attempt < BACKOFF_MS.length) {
          patchItem(assistantId, { streamState: 'reconnecting' } as never)
          await sleep(BACKOFF_MS[attempt])
          return runTurn(assistantId, message, attempt + 1)
        }
        patchItem(assistantId, { streamState: 'error', errorDetail: CONNECTION_LOST_MESSAGE } as never)
      } finally {
        controllerRef.current = null
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [widgetKey, conversationId, adoptConversationId],
  )

  const send = useCallback(
    (message: string) => {
      const text = message.trim()
      if (!text || isBusy) return
      const userId = crypto.randomUUID()
      const assistantId = crypto.randomUUID()
      setItems((prev) => [
        ...prev,
        { id: userId, kind: 'user', text },
        { id: assistantId, kind: 'assistant', text: '', sources: [], streamState: 'streaming' },
      ])
      setIsBusy(true)
      runTurn(assistantId, text, 0).finally(() => setIsBusy(false))
    },
    [isBusy, runTurn],
  )

  const retry = useCallback(
    (assistantId: string) => {
      const idx = items.findIndex((it) => it.id === assistantId)
      const userItem = idx > 0 ? items[idx - 1] : null
      if (!userItem || userItem.kind !== 'user' || isBusy) return
      setIsBusy(true)
      runTurn(assistantId, userItem.text, 0).finally(() => setIsBusy(false))
    },
    [items, isBusy, runTurn],
  )

  const stop = useCallback(() => controllerRef.current?.abort(), [])

  return { items, setItems, conversationId, adoptConversationId, send, retry, stop, isBusy }
}
