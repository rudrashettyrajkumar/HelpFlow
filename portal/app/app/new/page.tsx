'use client'

import { useEffect, useRef, useState } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  Clipboard,
  Loader2,
  MessagesSquare,
  SkipForward,
} from 'lucide-react'
import { EmbedSnippet } from '@/components/EmbedSnippet'
import { Glass } from '@/components/Glass'
import { ModelStudioBody } from '@/components/ModelStudioBody'
import { WidgetEmbed } from '@/components/WidgetEmbed'
import { WizardSteps } from '@/components/WizardSteps'
import { crawlSite, createWorkspace, listWorkspaces } from '@/lib/api'
import { useAuth } from '@/lib/auth-context'
import { previewQueryParam } from '@/lib/llmConfig'
import { useTheme } from '@/lib/theme'
import { ApiError } from '@/lib/types'
import type { CrawlProgressEvent } from '@/lib/types'
import { useModelStudio } from '@/lib/useModelStudio'

const ESCALATION_DEMO_QUESTION = 'I want a refund, can you help?'

export default function NewWorkspacePage() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const resumeId = searchParams.get('workspace')
  const { refresh } = useAuth()
  const { theme } = useTheme()
  const studio = useModelStudio()

  const [step, setStep] = useState(1)
  const [name, setName] = useState('')
  const [websiteUrl, setWebsiteUrl] = useState('')
  const [tenantId, setTenantId] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const [crawlEvents, setCrawlEvents] = useState<CrawlProgressEvent[]>([])
  const [crawlDone, setCrawlDone] = useState(false)
  const crawlRanFor = useRef<string | null>(null)

  const [copiedDemo, setCopiedDemo] = useState(false)

  // Resume: opened via "Open" on an existing workspace card — skip straight
  // to the live-preview step.
  useEffect(() => {
    if (!resumeId) return
    listWorkspaces()
      .then((all) => {
        const ws = all.find((w) => w.id === resumeId)
        if (!ws) return
        setTenantId(ws.id)
        setName(ws.name)
        setWebsiteUrl(ws.website_url ?? '')
        setCrawlDone(true)
        setStep(4)
      })
      .catch(() => {
        /* fall through to a normal fresh wizard */
      })
  }, [resumeId])

  const runCrawl = () => {
    if (!tenantId || crawlRanFor.current === tenantId) return
    crawlRanFor.current = tenantId
    setCrawlEvents([])
    setCrawlDone(false)
    ;(async () => {
      try {
        for await (const event of crawlSite(tenantId, websiteUrl)) {
          setCrawlEvents((prev) => [...prev, event])
          if (event.stage === 'ready') setCrawlDone(true)
        }
      } catch (err) {
        // A pre-stream rejection (400/409/429 from admin_sources.py's
        // validation-before-streaming split) carries a real, designed
        // `detail` — e.g. the embed-mismatch 409's re-crawl explanation
        // (spec Req 5). Surface it verbatim instead of a generic message.
        const detail =
          err instanceof ApiError ? err.message : "Couldn't reach the server to crawl your site."
        setCrawlEvents((prev) => [...prev, { stage: 'error', detail }])
      }
    })()
  }

  useEffect(() => {
    if (step === 2 && tenantId) runCrawl()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [step, tenantId])

  const submitStep1 = async (e: React.FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const res = await createWorkspace(name.trim(), websiteUrl.trim())
      setTenantId(res.tenant.id)
      await refresh() // trials_used just incremented — keep the header badge honest
      setStep(2)
    } catch (err) {
      if (err instanceof ApiError && err.gate) {
        router.push('/app/upgrade')
        return
      }
      setError(err instanceof ApiError ? err.message : 'Something went wrong. Please try again.')
    } finally {
      setBusy(false)
    }
  }

  const latestError = crawlEvents.findLast?.((e) => e.stage === 'error') as
    | { stage: 'error'; detail: string }
    | undefined
  const info = crawlEvents.find((e) => e.stage === 'info') as { stage: 'info'; note: string } | undefined
  const fetching = crawlEvents.findLast?.((e) => e.stage === 'fetching') as
    | { stage: 'fetching'; done: number; total: number }
    | undefined
  const embedding = crawlEvents.findLast?.((e) => e.stage === 'embedding') as
    | { stage: 'embedding'; pct: number }
    | undefined
  const ready = crawlEvents.find((e) => e.stage === 'ready') as
    | { stage: 'ready'; pages: number; chunks: number }
    | undefined

  const finishStudio = (skip: boolean) => {
    if (!skip) studio.save()
    setStep(4)
  }

  const copyDemoQuestion = async () => {
    try {
      await navigator.clipboard.writeText(ESCALATION_DEMO_QUESTION)
      setCopiedDemo(true)
      setTimeout(() => setCopiedDemo(false), 2500)
    } catch {
      // clipboard denied — the question is printed on-screen regardless
    }
  }

  return (
    <div className="mx-auto max-w-2xl">
      <h1 className="mb-1 text-2xl font-extrabold tracking-tight">New workspace</h1>
      <p className="mb-6 text-sm text-foreground-muted">
        Paste your site → watch it learn → pick a brain → chat over your own content.
      </p>
      <WizardSteps current={step} />

      {step === 1 && (
        <Glass strong className="rounded-3xl p-6 sm:p-8">
          <form onSubmit={submitStep1} className="space-y-4" noValidate>
            <div>
              <label htmlFor="ws-name" className="mb-1.5 block text-sm font-semibold">
                Business name
              </label>
              <input
                id="ws-name"
                required
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Acme Co"
                className="min-h-[44px] w-full rounded-xl border border-border bg-surface px-3.5 text-sm focus-visible:outline-none"
              />
            </div>
            <div>
              <label htmlFor="ws-url" className="mb-1.5 block text-sm font-semibold">
                Website URL
              </label>
              <input
                id="ws-url"
                type="url"
                required
                value={websiteUrl}
                onChange={(e) => setWebsiteUrl(e.target.value)}
                placeholder="https://acme.example.com"
                className="min-h-[44px] w-full rounded-xl border border-border bg-surface px-3.5 text-sm focus-visible:outline-none"
              />
            </div>
            {error && (
              <p role="alert" className="rounded-xl bg-destructive/10 px-3.5 py-2.5 text-sm font-medium text-destructive">
                {error}
              </p>
            )}
            <button
              type="submit"
              disabled={busy}
              className="flex min-h-[44px] w-full cursor-pointer items-center justify-center gap-2 rounded-xl bg-brand-gradient text-sm font-bold text-white shadow-glow transition-all hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {busy && <Loader2 className="size-4 animate-spin" aria-hidden="true" />}
              Start learning my site
            </button>
          </form>
        </Glass>
      )}

      {step === 2 && (
        <Glass strong className="rounded-3xl p-6 sm:p-8">
          {info && (
            <p className="mb-4 rounded-xl bg-brand/10 px-3.5 py-2.5 text-xs font-medium text-brand">
              {info.note}
            </p>
          )}

          <ol className="space-y-4">
            <CrawlStep label="Discovering pages" active={!fetching && !embedding && !ready} done={!!fetching || !!embedding || !!ready} />
            <CrawlStep
              label={fetching ? `Fetching ${fetching.done}/${fetching.total} pages` : 'Fetching pages'}
              active={!!fetching && !embedding && !ready}
              done={!!embedding || !!ready}
            />
            <CrawlStep
              label={embedding ? `Embedding (${embedding.pct}%)` : 'Embedding content'}
              active={!!embedding && !ready}
              done={!!ready}
            />
            <CrawlStep label={ready ? `Ready — ${ready.pages} pages, ${ready.chunks} chunks` : 'Ready'} active={false} done={!!ready} />
          </ol>

          {latestError && !ready && (
            <div className="mt-5 flex items-start gap-2 rounded-xl bg-destructive/10 px-3.5 py-2.5 text-sm text-destructive">
              <AlertTriangle className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
              <div>
                <p className="font-medium">{latestError.detail}</p>
                <button
                  type="button"
                  onClick={() => {
                    crawlRanFor.current = null
                    runCrawl()
                  }}
                  className="mt-1.5 cursor-pointer text-xs font-bold underline underline-offset-2"
                >
                  Try again
                </button>
              </div>
            </div>
          )}

          <button
            type="button"
            onClick={() => setStep(3)}
            disabled={!crawlDone}
            className="mt-6 flex min-h-[44px] w-full cursor-pointer items-center justify-center gap-2 rounded-xl bg-brand-gradient text-sm font-bold text-white shadow-glow transition-all hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-40 disabled:shadow-none"
          >
            Continue
            <ArrowRight className="size-4" aria-hidden="true" />
          </button>
        </Glass>
      )}

      {step === 3 && (
        <Glass strong className="rounded-3xl p-5 sm:p-6">
          <ModelStudioBody {...studio} />
          <div className="mt-6 flex items-center justify-between gap-3 border-t border-border pt-5">
            <button
              type="button"
              onClick={() => finishStudio(true)}
              className="flex min-h-[44px] cursor-pointer items-center gap-1.5 rounded-xl px-4 text-sm font-semibold text-foreground-muted hover:text-foreground"
            >
              <SkipForward className="size-4" aria-hidden="true" />
              Skip — use demo mode
            </button>
            <button
              type="button"
              onClick={() => finishStudio(false)}
              disabled={studio.draft.mode === 'byok' && !studio.canSaveByok}
              className="flex min-h-[44px] cursor-pointer items-center gap-2 rounded-xl bg-brand-gradient px-5 text-sm font-bold text-white shadow-glow transition-all hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-40 disabled:shadow-none"
            >
              Continue
              <ArrowRight className="size-4" aria-hidden="true" />
            </button>
          </div>
        </Glass>
      )}

      {step === 4 && tenantId && (
        <Glass strong className="rounded-3xl p-6 sm:p-8">
          <div className="mb-5 flex items-center gap-2 text-success">
            <CheckCircle2 className="size-5" aria-hidden="true" />
            <p className="text-sm font-bold">Your widget is live — try it bottom-right.</p>
          </div>

          <Glass className="mb-5 flex items-start gap-3 rounded-2xl p-4">
            <MessagesSquare className="mt-0.5 size-5 shrink-0 text-brand" aria-hidden="true" />
            <div>
              <p className="text-sm font-semibold">See the human handoff in action</p>
              <p className="mt-0.5 text-xs text-foreground-muted">
                Open the chat bubble and ask: <span className="font-mono">&ldquo;{ESCALATION_DEMO_QUESTION}&rdquo;</span>
              </p>
              <button
                type="button"
                onClick={copyDemoQuestion}
                className="mt-2 flex cursor-pointer items-center gap-1.5 rounded-lg border border-border px-2.5 py-1.5 text-xs font-semibold transition-colors hover:border-brand/40"
              >
                <Clipboard className="size-3.5" aria-hidden="true" />
                {copiedDemo ? 'Copied!' : 'Copy the question'}
              </button>
            </div>
          </Glass>

          <EmbedSnippet widgetKey={tenantId} />

          <button
            type="button"
            onClick={() => router.push('/app')}
            className="mt-6 flex min-h-[44px] w-full cursor-pointer items-center justify-center gap-2 rounded-xl border border-border text-sm font-semibold transition-colors hover:border-brand/40"
          >
            Done — back to workspaces
          </button>

          <WidgetEmbed
            widgetKey={tenantId}
            theme={theme}
            llmConfigParam={previewQueryParam()}
          />
        </Glass>
      )}
    </div>
  )
}

function CrawlStep({ label, active, done }: { label: string; active: boolean; done: boolean }) {
  return (
    <li className="flex items-center gap-3">
      <span
        className={`flex size-6 shrink-0 items-center justify-center rounded-full ${
          done ? 'bg-success text-white' : active ? 'bg-brand text-white' : 'bg-surface-muted text-foreground-muted'
        }`}
      >
        {done ? (
          <CheckCircle2 className="size-3.5" aria-hidden="true" />
        ) : active ? (
          <Loader2 className="size-3.5 animate-spin" aria-hidden="true" />
        ) : (
          <span className="size-1.5 rounded-full bg-current" />
        )}
      </span>
      <span className={`text-sm ${active || done ? 'font-semibold' : 'text-foreground-muted'}`}>{label}</span>
    </li>
  )
}
