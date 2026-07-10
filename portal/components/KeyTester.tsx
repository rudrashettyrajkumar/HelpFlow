'use client'

import { useState } from 'react'
import {
  ArrowUpRight,
  CheckCircle2,
  ChevronDown,
  Eye,
  EyeOff,
  KeyRound,
  Loader2,
  ShieldCheck,
  XCircle,
} from 'lucide-react'
import { validateProviderKey } from '@/lib/api'
import type { ProviderInfo } from '@/lib/types'

type ValidationState =
  | { status: 'idle' }
  | { status: 'checking' }
  | { status: 'ok'; latencyMs?: number }
  | { status: 'error'; detail: string }

const ERROR_COPY: Record<string, string> = {
  key_invalid: "That key doesn't work — double-check you copied the whole thing.",
  rate_limited: "That key's rate limit is hit right now — try again in a moment.",
  model_not_found: "That model id isn't available on this key.",
  unknown_provider: 'Unknown provider.',
  provider_error: "Couldn't reach the provider to test this key.",
}

function KeySteps({ provider }: { provider: ProviderInfo }) {
  const [open, setOpen] = useState(false)
  return (
    <div className="rounded-2xl border border-border">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex min-h-[44px] w-full cursor-pointer items-center justify-between gap-2 px-3.5 py-2.5 text-sm font-semibold"
      >
        <span className="flex items-center gap-2">
          <KeyRound className="size-4 text-brand" aria-hidden="true" />
          How to get your {provider.name} key
        </span>
        <ChevronDown className={`size-4 transition-transform ${open ? 'rotate-180' : ''}`} aria-hidden="true" />
      </button>
      {open && (
        <ol className="space-y-2 px-3.5 pb-3">
          {provider.key_steps.map((step, i) => (
            <li key={i} className="flex gap-2.5 text-[13px] leading-snug text-foreground-muted">
              <span className="mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-full bg-brand/10 text-[11px] font-bold text-brand">
                {i + 1}
              </span>
              {step}
            </li>
          ))}
          <a
            href={provider.key_url}
            target="_blank"
            rel="noreferrer"
            className="ml-7 inline-flex min-h-[36px] items-center gap-1 text-[13px] font-semibold text-brand hover:underline"
          >
            Open {provider.key_url.replace('https://', '').split('/')[0]}
            <ArrowUpRight className="size-3.5" aria-hidden="true" />
          </a>
        </ol>
      )}
    </div>
  )
}

type Props = {
  provider: ProviderInfo
  model: string
  apiKey: string
  onApiKeyChange: (value: string) => void
}

/** Key input + live `/api/models/validate` test (spec Req 4). The copy is
 * load-bearing, not decoration: "your key never leaves this browser" is the
 * portal's trust story (ARCHITECTURE §4.4). */
export function KeyTester({ provider, model, apiKey, onApiKeyChange }: Props) {
  const [showKey, setShowKey] = useState(false)
  const [validation, setValidation] = useState<ValidationState>({ status: 'idle' })

  const validate = async () => {
    if (!apiKey || !model) return
    setValidation({ status: 'checking' })
    try {
      const result = await validateProviderKey({ provider: provider.id, model, key: apiKey, kind: 'chat' })
      setValidation(
        result.ok
          ? { status: 'ok', latencyMs: result.latency_ms }
          : { status: 'error', detail: ERROR_COPY[result.error_code ?? ''] ?? 'That key did not validate.' },
      )
    } catch {
      setValidation({ status: 'error', detail: "Couldn't reach the server to test the key." })
    }
  }

  return (
    <div className="space-y-4">
      <p className="text-sm text-foreground-muted">{provider.tagline}</p>
      <KeySteps provider={provider} />

      <div>
        <label htmlFor="byok-key" className="mb-1.5 block text-xs font-bold">
          {provider.name} API key <span className="text-destructive">*</span>
        </label>
        <div className="flex flex-col gap-2 sm:flex-row">
          <div className="relative flex-1">
            <input
              id="byok-key"
              type={showKey ? 'text' : 'password'}
              value={apiKey}
              onChange={(e) => {
                onApiKeyChange(e.target.value.trim())
                setValidation({ status: 'idle' })
              }}
              placeholder={`Paste your ${provider.name} key`}
              autoComplete="off"
              spellCheck={false}
              className="min-h-[44px] w-full rounded-xl border border-border bg-surface px-3.5 pr-11 text-sm focus-visible:outline-none"
            />
            <button
              type="button"
              onClick={() => setShowKey((v) => !v)}
              aria-label={showKey ? 'Hide key' : 'Show key'}
              className="absolute right-1 top-1/2 flex size-9 -translate-y-1/2 cursor-pointer items-center justify-center rounded-lg text-foreground-muted hover:text-foreground"
            >
              {showKey ? <EyeOff className="size-4" aria-hidden="true" /> : <Eye className="size-4" aria-hidden="true" />}
            </button>
          </div>
          <button
            type="button"
            onClick={validate}
            disabled={!apiKey || validation.status === 'checking'}
            className="flex min-h-[44px] cursor-pointer items-center justify-center gap-2 rounded-xl border border-border px-4 text-sm font-semibold transition-colors hover:border-brand/50 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {validation.status === 'checking' ? (
              <Loader2 className="size-4 animate-spin" aria-hidden="true" />
            ) : (
              <ShieldCheck className="size-4" aria-hidden="true" />
            )}
            Test key
          </button>
        </div>
        <div aria-live="polite">
          {validation.status === 'ok' && (
            <p className="mt-1.5 flex items-center gap-1.5 text-xs font-semibold text-success">
              <CheckCircle2 className="size-4" aria-hidden="true" /> Key works
              {validation.latencyMs !== undefined && ` — ${validation.latencyMs}ms`}
            </p>
          )}
          {validation.status === 'error' && (
            <p className="mt-1.5 flex items-start gap-1.5 text-xs font-semibold text-destructive">
              <XCircle className="mt-0.5 size-4 shrink-0" aria-hidden="true" /> {validation.detail}
            </p>
          )}
        </div>
        <p className="mt-1.5 text-[11px] text-foreground-muted">
          Your key never leaves this browser. It&apos;s stored only in localStorage and sent
          straight to {provider.name} on each request — never saved on our servers.
        </p>
      </div>
    </div>
  )
}
