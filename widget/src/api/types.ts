// Shapes bound to the REAL backend contracts (read from backend/api/chat.py,
// backend/utils/sse.py, backend/pipeline/chat_pipeline.py, backend/api/widget.py —
// never guessed). The SSE contract is FROZEN (ARCHITECTURE invariant #10); `notice`
// is the one additive v2 event.

// Matches `answer_agent.cited_sources()` exactly — never guessed (spec-check
// caught an earlier mismatched draft: `page_title`/`source_url`, not
// `title`/`url`; `cited` drives the SourcesDrawer's dimmed-when-unused state).
export type SourceItem = {
  n: number
  source_url: string
  page_title: string
  snippet: string
  score: number
  cited: boolean
}

export type NoticeLink = { label: string; url: string }

export type NoticeCode = 'demo_exhausted' | 'key_invalid' | 'embed_mismatch'

export type ChatEvent =
  | { type: 'token'; seq: number; t: string }
  | { type: 'sources'; sources: SourceItem[] }
  | { type: 'handoff'; reason: string | null }
  | { type: 'human_turn' }
  | { type: 'notice'; code: NoticeCode; message: string; links: NoticeLink[] }
  | { type: 'error'; detail: string }
  | { type: 'done'; conversation_id: string }

export type ConversationStatus =
  | 'ai_handling'
  | 'needs_human'
  | 'human_assigned'
  | 'resolved'
  | 'abandoned'

export type SubscribeEvent =
  | { type: 'message'; role: string; body: string; created_at: string }
  | { type: 'status'; status: ConversationStatus }

export type WidgetConfig = {
  name: string
  greeting: string | null
  brand_color: string | null
  theme: 'light' | 'dark' | 'auto' | null
}

export class ApiError extends Error {
  status: number
  constructor(message: string, status: number) {
    super(message)
    this.status = status
  }
}

// Client-side transcript model — one item per rendered bubble/card. Distinct
// from `ChatEvent` (the wire shape): a `notice`/`handoff`/`human_turn` on the
// wire mutates or appends to this list rather than mapping 1:1.
export type ChatItem =
  | { id: string; kind: 'user'; text: string }
  | {
      id: string
      kind: 'assistant'
      text: string
      sources: SourceItem[]
      streamState: 'streaming' | 'done' | 'reconnecting' | 'error' | 'rate_limited'
      errorDetail?: string
    }
  | { id: string; kind: 'agent'; text: string; createdAt: string }
  | { id: string; kind: 'notice'; code: NoticeCode; message: string; links: NoticeLink[] }
  | { id: string; kind: 'handoff'; reason: string | null }
  | { id: string; kind: 'resolved' }
