import { byokHeaders } from '../lib/llmConfig'
import { ApiError, type ChatEvent, type WidgetConfig } from './types'

const API_URL = import.meta.env.VITE_API_URL as string

async function throwIfError(res: Response): Promise<void> {
  if (res.ok) return
  let detail = `Request failed (${res.status})`
  try {
    const body = await res.json()
    detail = body.detail ?? detail
  } catch {
    // non-JSON error body — keep the generic message
  }
  throw new ApiError(detail, res.status)
}

/** Parses a `text/event-stream` body into `{event, data}` frames — ported from
 * DocChat's `api/client.ts`. Comment lines (`: ping` heartbeats) never surface. */
async function* parseSSE(
  body: ReadableStream<Uint8Array>,
): AsyncGenerator<{ event: string; data: unknown }> {
  const reader = body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) return
      buffer += decoder.decode(value, { stream: true })
      const frames = buffer.split('\n\n')
      buffer = frames.pop() ?? ''
      for (const frame of frames) {
        if (!frame || frame.startsWith(':')) continue
        let eventName = 'message'
        let data: unknown = null
        for (const line of frame.split('\n')) {
          if (line.startsWith('event: ')) eventName = line.slice(7)
          else if (line.startsWith('data: ')) data = JSON.parse(line.slice(6))
        }
        if (data !== null) yield { event: eventName, data }
      }
    }
  } finally {
    reader.releaseLock()
  }
}

export async function fetchWidgetConfig(widgetKey: string): Promise<WidgetConfig> {
  const res = await fetch(`${API_URL}/widget/config`, {
    headers: { 'X-Widget-Key': widgetKey },
  })
  await throwIfError(res)
  return res.json()
}

/** `POST /chat/stream` — the frozen SSE contract (spec E7 Req 2/4/5): token/seq,
 * sources, handoff, human_turn, done, error, plus the additive `notice` event. */
export async function* streamChat(
  widgetKey: string,
  conversationId: string | null,
  message: string,
  signal?: AbortSignal,
): AsyncGenerator<ChatEvent> {
  const res = await fetch(`${API_URL}/chat/stream`, {
    method: 'POST',
    headers: {
      'X-Widget-Key': widgetKey,
      'Content-Type': 'application/json',
      ...byokHeaders(),
    },
    body: JSON.stringify({ conversation_id: conversationId, message }),
    signal,
  })
  await throwIfError(res)
  if (!res.body) return

  for await (const frame of parseSSE(res.body)) {
    yield { type: frame.event, ...(frame.data as object) } as ChatEvent
  }
}
