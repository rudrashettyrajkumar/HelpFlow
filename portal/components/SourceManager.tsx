'use client'

import { useEffect, useState } from 'react'
import {
  AlertTriangle,
  CheckCircle2,
  Clock,
  Loader2,
  Plus,
  RefreshCw,
  Trash2,
  XCircle,
} from 'lucide-react'
import { Glass } from './Glass'
import { crawlSite, deleteSource, fetchSources, refreshSource } from '@/lib/api'
import { ApiError } from '@/lib/types'
import type { CrawlProgressEvent, Source } from '@/lib/types'

const STATUS_LOOK: Record<Source['status'], { icon: typeof Clock; cls: string; label: string }> = {
  crawling: { icon: Loader2, cls: 'text-brand', label: 'Crawling' },
  ready: { icon: CheckCircle2, cls: 'text-success', label: 'Ready' },
  error: { icon: XCircle, cls: 'text-destructive', label: 'Error' },
}

export function SourceManager({ tenantId }: { tenantId: string }) {
  const [sources, setSources] = useState<Source[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [url, setUrl] = useState('')
  const [crawling, setCrawling] = useState(false)
  const [progress, setProgress] = useState<CrawlProgressEvent | null>(null)
  const [crawlError, setCrawlError] = useState<{ detail: string; code: string | null } | null>(null)
  const [busySourceId, setBusySourceId] = useState<string | null>(null)

  const refresh = () => {
    fetchSources(tenantId)
      .then((rows) => {
        setSources(rows)
        setError(null)
      })
      .catch(() => setError("Couldn't load sources — check your session."))
  }

  useEffect(refresh, [tenantId])

  const submitCrawl = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!url.trim() || crawling) return
    setCrawling(true)
    setCrawlError(null)
    setProgress(null)
    try {
      for await (const event of crawlSite(tenantId, url.trim())) {
        setProgress(event)
        if (event.stage === 'error') {
          setCrawlError({ detail: event.detail, code: null })
        }
      }
      setUrl('')
      refresh()
    } catch (err) {
      setCrawlError({
        detail: err instanceof ApiError ? err.message : "Couldn't reach the server to crawl.",
        code: err instanceof ApiError ? err.code : null,
      })
    } finally {
      setCrawling(false)
    }
  }

  const withBusy = async (sourceId: string, fn: () => Promise<unknown>) => {
    setBusySourceId(sourceId)
    try {
      await fn()
      refresh()
    } finally {
      setBusySourceId(null)
    }
  }

  return (
    <div className="space-y-5">
      <Glass strong className="rounded-3xl p-5 sm:p-6">
        <form onSubmit={submitCrawl} className="flex flex-col gap-2 sm:flex-row">
          <input
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="https://example.com or a sitemap URL"
            className="min-h-[44px] flex-1 rounded-xl border border-border bg-surface px-3.5 text-sm focus-visible:outline-none"
          />
          <button
            type="submit"
            disabled={crawling || !url.trim()}
            className="flex min-h-[44px] cursor-pointer items-center justify-center gap-2 rounded-xl bg-brand-gradient px-5 text-sm font-bold text-white shadow-glow transition-all hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {crawling ? <Loader2 className="size-4 animate-spin" aria-hidden="true" /> : <Plus className="size-4" aria-hidden="true" />}
            Add source
          </button>
        </form>

        {progress && !crawlError && (
          <p className="mt-3 flex items-center gap-2 text-xs font-medium text-foreground-muted">
            <Loader2 className="size-3.5 animate-spin" aria-hidden="true" />
            {progress.stage === 'discovering' && 'Discovering pages…'}
            {progress.stage === 'fetching' && `Fetching ${progress.done}/${progress.total} pages…`}
            {progress.stage === 'embedding' && `Embedding (${progress.pct}%)…`}
            {progress.stage === 'ready' && `Done — ${progress.pages} pages, ${progress.chunks} chunks.`}
            {progress.stage === 'info' && progress.note}
          </p>
        )}

        {crawlError && (
          <div className="mt-3 flex items-start gap-2 rounded-xl bg-destructive/10 px-3.5 py-2.5 text-xs text-destructive">
            <AlertTriangle className="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />
            <div>
              <p className="font-medium">{crawlError.detail}</p>
              {crawlError.code === 'embed_mismatch' && (
                <p className="mt-1 text-foreground-muted">
                  This workspace&apos;s knowledge base was built with a different embedding
                  model. Delete all sources below to release it, then crawl again with
                  your new selection.
                </p>
              )}
            </div>
          </div>
        )}
      </Glass>

      {error && (
        <Glass className="flex items-center gap-2 rounded-2xl px-4 py-3 text-sm text-destructive">
          <AlertTriangle className="size-4 shrink-0" aria-hidden="true" /> {error}
        </Glass>
      )}

      {!sources && !error && (
        <div className="flex items-center justify-center gap-2 py-16 text-sm text-foreground-muted">
          <Loader2 className="size-4 animate-spin" aria-hidden="true" /> Loading sources…
        </div>
      )}

      {sources?.length === 0 && (
        <Glass className="rounded-2xl px-4 py-8 text-center text-sm text-foreground-muted">
          No sources yet — add a URL above to start crawling.
        </Glass>
      )}

      {sources && sources.length > 0 && (
        <div className="space-y-2">
          {sources.map((s) => {
            const look = STATUS_LOOK[s.status]
            const Icon = look.icon
            const busy = busySourceId === s.id
            return (
              <Glass key={s.id} className="flex items-center justify-between gap-3 rounded-2xl px-4 py-3">
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium">{s.title || s.url}</p>
                  <p className="truncate text-xs text-foreground-muted">{s.url}</p>
                  {s.error && <p className="mt-0.5 text-xs text-destructive">{s.error}</p>}
                </div>
                <span className={`flex shrink-0 items-center gap-1 text-xs font-semibold ${look.cls}`}>
                  <Icon className={`size-3.5 ${s.status === 'crawling' ? 'animate-spin' : ''}`} aria-hidden="true" />
                  {look.label}
                  {s.chunk_count != null && s.status === 'ready' && ` · ${s.chunk_count} chunks`}
                </span>
                <div className="flex shrink-0 gap-1.5">
                  <button
                    onClick={() => withBusy(s.id, () => refreshSource(tenantId, s.id))}
                    disabled={busy}
                    aria-label="Refresh this page"
                    className="flex size-8 cursor-pointer items-center justify-center rounded-lg text-foreground-muted hover:text-foreground disabled:opacity-40"
                  >
                    <RefreshCw className={`size-4 ${busy ? 'animate-spin' : ''}`} aria-hidden="true" />
                  </button>
                  <button
                    onClick={() => withBusy(s.id, () => deleteSource(tenantId, s.id))}
                    disabled={busy}
                    aria-label="Delete this source"
                    className="flex size-8 cursor-pointer items-center justify-center rounded-lg text-foreground-muted hover:text-destructive disabled:opacity-40"
                  >
                    <Trash2 className="size-4" aria-hidden="true" />
                  </button>
                </div>
              </Glass>
            )
          })}
        </div>
      )}
    </div>
  )
}
