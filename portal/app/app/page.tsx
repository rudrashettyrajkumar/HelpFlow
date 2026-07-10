'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { AlertTriangle, ArrowRight, ExternalLink, Loader2, Plus, Sparkles } from 'lucide-react'
import { Glass } from '@/components/Glass'
import { listWorkspaces } from '@/lib/api'
import { useAuth } from '@/lib/auth-context'
import type { Workspace } from '@/lib/types'

const MAX_TRIALS = 2

const STATUS_LOOK: Record<Workspace['status'], { label: string; cls: string }> = {
  ready: { label: 'Ready', cls: 'bg-success/15 text-success' },
  crawling: { label: 'Crawling…', cls: 'bg-brand/15 text-brand' },
  empty: { label: 'No sources yet', cls: 'bg-foreground-muted/15 text-foreground-muted' },
}

export default function WorkspacesPage() {
  const { trialsUsed } = useAuth()
  const [workspaces, setWorkspaces] = useState<Workspace[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    listWorkspaces()
      .then(setWorkspaces)
      .catch(() => setError("Couldn't load your workspaces. Refresh to try again."))
  }, [])

  const atCap = trialsUsed >= MAX_TRIALS

  return (
    <div>
      <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-extrabold tracking-tight">Your workspaces</h1>
          <p className="mt-1 text-sm text-foreground-muted">
            Each workspace is one site — its own crawl, its own chat widget.
          </p>
        </div>
        <Link
          href={atCap ? '/app/upgrade' : '/app/new'}
          className="flex min-h-[44px] items-center gap-2 rounded-xl bg-brand-gradient px-4 text-sm font-bold text-white shadow-glow transition-all hover:brightness-110"
        >
          {atCap ? (
            <>
              Unlock more <ArrowRight className="size-4" aria-hidden="true" />
            </>
          ) : (
            <>
              <Plus className="size-4" aria-hidden="true" /> New workspace
            </>
          )}
        </Link>
      </div>

      {error && (
        <Glass className="mb-6 flex items-center gap-2 rounded-2xl px-4 py-3 text-sm text-destructive">
          <AlertTriangle className="size-4 shrink-0" aria-hidden="true" />
          {error}
        </Glass>
      )}

      {workspaces === null && !error && (
        <div className="flex items-center justify-center gap-2 py-24 text-sm text-foreground-muted">
          <Loader2 className="size-4 animate-spin" aria-hidden="true" /> Loading workspaces…
        </div>
      )}

      {workspaces?.length === 0 && (
        <Glass className="flex flex-col items-center gap-3 rounded-3xl px-6 py-16 text-center">
          <span className="flex size-12 items-center justify-center rounded-2xl bg-brand-gradient text-white shadow-glow">
            <Sparkles className="size-6" aria-hidden="true" />
          </span>
          <h2 className="text-lg font-bold">No workspaces yet</h2>
          <p className="max-w-sm text-sm text-foreground-muted">
            Paste a website URL and watch HelpFlow learn it in real time — you&apos;ll be
            chatting over your own content in about two minutes.
          </p>
          <Link
            href="/app/new"
            className="mt-2 flex min-h-[44px] items-center gap-2 rounded-xl bg-brand-gradient px-5 text-sm font-bold text-white shadow-glow transition-all hover:brightness-110"
          >
            Create your first workspace
            <ArrowRight className="size-4" aria-hidden="true" />
          </Link>
        </Glass>
      )}

      {workspaces && workspaces.length > 0 && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {workspaces.map((ws) => (
            <Glass key={ws.id} className="flex flex-col gap-3 rounded-2xl p-5">
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <p className="truncate text-base font-bold">{ws.name}</p>
                  {ws.website_url && (
                    <a
                      href={ws.website_url}
                      target="_blank"
                      rel="noreferrer"
                      className="mt-0.5 flex items-center gap-1 truncate text-xs text-foreground-muted hover:text-brand"
                    >
                      {ws.website_url.replace(/^https?:\/\//, '')}
                      <ExternalLink className="size-3 shrink-0" aria-hidden="true" />
                    </a>
                  )}
                </div>
                {ws.plan === 'trial' && (
                  <span className="shrink-0 rounded-full bg-brand/15 px-2 py-0.5 text-[10px] font-bold text-brand">
                    TRIAL
                  </span>
                )}
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <span
                  className={`rounded-full px-2.5 py-1 text-xs font-semibold ${STATUS_LOOK[ws.status].cls}`}
                >
                  {STATUS_LOOK[ws.status].label}
                </span>
                <span className="text-xs text-foreground-muted">
                  {ws.sources_ready}/{ws.sources_total} pages ready
                </span>
              </div>
              <Link
                href={`/app/new?workspace=${ws.id}`}
                className="mt-1 flex min-h-[40px] items-center justify-center gap-1.5 rounded-xl border border-border text-sm font-semibold transition-colors hover:border-brand/40"
              >
                Open
                <ArrowRight className="size-3.5" aria-hidden="true" />
              </Link>
            </Glass>
          ))}
        </div>
      )}
    </div>
  )
}
