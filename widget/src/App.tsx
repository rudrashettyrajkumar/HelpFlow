import { useEffect, useMemo, useRef, useState } from 'react'
import { AlertTriangle } from 'lucide-react'
import { fetchWidgetConfig } from './api/client'
import type { WidgetConfig } from './api/types'
import { Bubble } from './components/Bubble'
import { Composer } from './components/Composer'
import { MessageList } from './components/MessageList'
import { SourcesDrawer } from './components/SourcesDrawer'
import { StatusPill } from './components/StatusPill'
import { useChatStream } from './hooks/useChatStream'
import { useConversationSubscribe } from './hooks/useConversationSubscribe'
import { hexToRgbTriple } from './lib/color'
import { loadLLMConfig, onLLMConfigChange } from './lib/llmConfig'

const params = new URLSearchParams(window.location.search)
const WIDGET_KEY = params.get('key')
const CAN_OPEN_MODEL_STUDIO = params.get('studio') === '1'

export default function App() {
  if (!WIDGET_KEY) return <MisconfiguredCard />
  return <Widget widgetKey={WIDGET_KEY} />
}

function MisconfiguredCard() {
  return (
    <div className="flex h-dvh items-center justify-center p-6 text-center">
      <div className="glass flex flex-col items-center gap-2 rounded-2xl p-5">
        <AlertTriangle className="size-6 text-destructive" aria-hidden="true" />
        <p className="text-sm font-medium">This chat widget isn't configured correctly.</p>
        <p className="text-xs text-foreground-muted">Missing widget key.</p>
      </div>
    </div>
  )
}

function Widget({ widgetKey }: { widgetKey: string }) {
  const [open, setOpen] = useState(false)
  const [draft, setDraft] = useState('')
  const [tenant, setTenant] = useState<WidgetConfig | null>(null)
  const [activeSource, setActiveSource] = useState<{ assistantId: string; n: number } | null>(null)
  const [llmConfig, setLlmConfig] = useState(loadLLMConfig)
  const lastSeenRepliesRef = useRef(0)
  const appendedRepliesRef = useRef<Set<string>>(new Set())
  const resolvedShownRef = useRef(false)
  const panelRef = useRef<HTMLDivElement>(null)

  const { items, setItems, conversationId, send, retry, isBusy } = useChatStream(widgetKey)
  const { replies, status } = useConversationSubscribe(conversationId)

  useEffect(() => {
    let cancelled = false
    fetchWidgetConfig(widgetKey)
      .then((cfg) => {
        if (cancelled) return
        setTenant(cfg)
        const rgb = cfg.brand_color ? hexToRgbTriple(cfg.brand_color) : null
        if (rgb) document.documentElement.style.setProperty('--brand', rgb)
      })
      .catch(() => {
        // Degrade to a generic header — a misconfigured/unreachable tenant
        // must never block the chat itself from rendering (spec Req 7).
      })
    return () => {
      cancelled = true
    }
  }, [widgetKey])

  useEffect(() => onLLMConfigChange(() => setLlmConfig(loadLLMConfig())), [])

  // Fold live agent replies into the SAME item list `MessageList` renders, so
  // ordering stays chronological-by-arrival without a separate merge pass.
  useEffect(() => {
    for (const r of replies) {
      if (appendedRepliesRef.current.has(r.createdAt)) continue
      appendedRepliesRef.current.add(r.createdAt)
      setItems((prev) => [
        ...prev,
        { id: `agent-${r.createdAt}`, kind: 'agent', text: r.body, createdAt: r.createdAt },
      ])
    }
  }, [replies, setItems])

  useEffect(() => {
    if (status === 'resolved' && !resolvedShownRef.current) {
      resolvedShownRef.current = true
      setItems((prev) => [...prev, { id: `resolved-${Date.now()}`, kind: 'resolved' }])
    } else if (status !== 'resolved') {
      resolvedShownRef.current = false
    }
  }, [status, setItems])

  // Focus trap + Escape-to-close while the panel is open (spec Req 8).
  useEffect(() => {
    if (!open) return
    const panel = panelRef.current
    if (!panel) return
    const focusable = () =>
      Array.from(
        panel.querySelectorAll<HTMLElement>(
          'button:not([disabled]), [href], input, textarea, select, [tabindex]:not([tabindex="-1"])',
        ),
      )
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setOpen(false)
        return
      }
      if (e.key !== 'Tab') return
      const els = focusable()
      if (els.length === 0) return
      const first = els[0]
      const last = els[els.length - 1]
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault()
        last.focus()
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault()
        first.focus()
      }
    }
    document.addEventListener('keydown', onKeyDown)
    focusable()[0]?.focus()
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [open])

  // embed.js's iframe is bubble-sized until told otherwise — it can't know
  // the panel opened without this (host-CSS isolation cuts both ways).
  useEffect(() => {
    window.parent.postMessage({ type: 'hf:widget-state', open }, '*')
  }, [open])

  const hasUnread = !open && replies.length > lastSeenRepliesRef.current

  const toggleOpen = () => {
    setOpen((v) => {
      if (!v) lastSeenRepliesRef.current = replies.length
      return !v
    })
  }

  const activeSources = useMemo(() => {
    if (!activeSource) return []
    const item = items.find((it) => it.id === activeSource.assistantId)
    return item && item.kind === 'assistant' ? item.sources : []
  }, [activeSource, items])

  const handleSend = () => {
    if (!draft.trim() || isBusy) return
    send(draft)
    setDraft('')
  }

  return (
    <>
      {/* Fills whatever box embed.js gives the iframe — never a `sm:` breakpoint:
          the iframe itself is at most 420px wide even in "desktop" open state,
          so a Tailwind `sm:` (640px) rule can never fire from inside it. The
          floating-card look (rounded corners, shadow) vs. mobile full-bleed is
          embed.js's job, applied to the iframe element itself. */}
      {open && (
        <div
          ref={panelRef}
          role="dialog"
          aria-label={`Chat with ${tenant?.name ?? 'us'}`}
          className="glass-strong fixed inset-0 z-[999] flex h-dvh w-screen flex-col overflow-hidden"
        >
          <header className="flex items-center justify-between bg-brand-gradient px-4 py-3.5 text-white">
            <div>
              <p className="text-sm font-bold">{tenant?.name ?? 'Chat with us'}</p>
              <p className="text-xs text-white/80">
                {llmConfig.mode === 'demo' ? 'Usually replies in a few minutes' : 'Online'}
              </p>
            </div>
            <button
              onClick={() => setOpen(false)}
              aria-label="Close chat"
              className="flex size-8 cursor-pointer items-center justify-center rounded-full text-white/90 hover:bg-white/15"
            >
              ×
            </button>
          </header>

          <div className="relative flex flex-1 flex-col overflow-hidden">
            {items.length === 0 ? (
              <EmptyState greeting={tenant?.greeting ?? null} businessName={tenant?.name ?? 'us'} />
            ) : (
              <MessageList
                items={items}
                canOpenModelStudio={CAN_OPEN_MODEL_STUDIO}
                onCitationClick={(assistantId, n) => setActiveSource({ assistantId, n })}
                onRetry={retry}
              />
            )}

            {status === 'needs_human' && (
              <div className="px-4 pb-2">
                <StatusPill label="Waiting for a teammate…" />
              </div>
            )}

            <SourcesDrawer
              sources={activeSources}
              activeN={activeSource?.n ?? null}
              onClose={() => setActiveSource(null)}
            />
          </div>

          <Composer
            value={draft}
            onChange={setDraft}
            onSend={handleSend}
            disabled={isBusy}
            config={llmConfig}
            canOpenModelStudio={CAN_OPEN_MODEL_STUDIO}
          />
        </div>
      )}

      {/* Only rendered while closed — the panel's own header close button (and
          Escape) handle dismissal once open, so the launcher never has to
          float on top of the panel's own content (it used to sit directly
          over the composer's send button). */}
      {!open && <Bubble open={open} hasUnread={hasUnread} onClick={toggleOpen} />}
    </>
  )
}

function EmptyState({ greeting, businessName }: { greeting: string | null; businessName: string }) {
  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-2 px-6 text-center">
      <div className="mb-1 size-11 rounded-2xl bg-brand-gradient shadow-glow" aria-hidden="true" />
      <p className="text-sm font-semibold">{greeting ?? `Hi! How can we help you today?`}</p>
      <p className="text-xs text-foreground-muted">Ask anything about {businessName} — cited answers, or we'll get you a person.</p>
    </div>
  )
}
