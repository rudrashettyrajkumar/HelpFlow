'use client'

import { useState } from 'react'
import { CheckCircle2, Loader2 } from 'lucide-react'
import { premiumContact } from '@/lib/api'
import { RAJ } from '@/lib/config'
import { useAuth } from '@/lib/auth-context'
import { ApiError } from '@/lib/types'

type Props = { source: 'gate' | 'landing' }

/** The short lead-capture form (spec Req 6) → `POST /api/premium-contact` →
 * success state ("Raj usually replies within a few hours"). */
export function LeadForm({ source }: Props) {
  const { user } = useAuth()
  const [name, setName] = useState('')
  const [email, setEmail] = useState(user?.email ?? '')
  const [company, setCompany] = useState('')
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [sent, setSent] = useState(false)

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await premiumContact({ name, email, company: company || undefined, message, source })
      setSent(true)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Something went wrong. Please try again.')
    } finally {
      setBusy(false)
    }
  }

  if (sent) {
    return (
      <div className="flex flex-col items-center gap-2 rounded-2xl bg-success/10 px-5 py-8 text-center">
        <CheckCircle2 className="size-8 text-success" aria-hidden="true" />
        <p className="font-bold">Thanks — that&apos;s sent.</p>
        <p className="text-sm text-foreground-muted">
          {RAJ.name} usually replies within a few hours.
        </p>
      </div>
    )
  }

  return (
    <form onSubmit={onSubmit} className="space-y-3" noValidate>
      <div className="grid gap-3 sm:grid-cols-2">
        <div>
          <label htmlFor="lead-name" className="mb-1.5 block text-xs font-semibold">
            Name
          </label>
          <input
            id="lead-name"
            required
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="min-h-[44px] w-full rounded-xl border border-border bg-surface px-3.5 text-sm focus-visible:outline-none"
          />
        </div>
        <div>
          <label htmlFor="lead-email" className="mb-1.5 block text-xs font-semibold">
            Email
          </label>
          <input
            id="lead-email"
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="min-h-[44px] w-full rounded-xl border border-border bg-surface px-3.5 text-sm focus-visible:outline-none"
          />
        </div>
      </div>
      <div>
        <label htmlFor="lead-company" className="mb-1.5 block text-xs font-semibold">
          Company <span className="font-normal text-foreground-muted">(optional)</span>
        </label>
        <input
          id="lead-company"
          value={company}
          onChange={(e) => setCompany(e.target.value)}
          className="min-h-[44px] w-full rounded-xl border border-border bg-surface px-3.5 text-sm focus-visible:outline-none"
        />
      </div>
      <div>
        <label htmlFor="lead-message" className="mb-1.5 block text-xs font-semibold">
          What are you looking to do?
        </label>
        <textarea
          id="lead-message"
          required
          rows={3}
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          className="w-full resize-none rounded-xl border border-border bg-surface px-3.5 py-2.5 text-sm focus-visible:outline-none"
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
        Send
      </button>
    </form>
  )
}
