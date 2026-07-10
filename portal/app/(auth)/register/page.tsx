'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { Eye, EyeOff, Loader2 } from 'lucide-react'
import { AuthScaffold } from '@/components/AuthScaffold'
import { useAuth } from '@/lib/auth-context'
import { ApiError } from '@/lib/types'

export default function RegisterPage() {
  const { user, initializing, register } = useAuth()
  const router = useRouter()

  useEffect(() => {
    if (!initializing && user) router.replace('/app')
  }, [initializing, user, router])

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const passwordTooShort = password.length > 0 && password.length < 8

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (passwordTooShort) return
    setBusy(true)
    setError(null)
    try {
      await register(email, password)
      router.push('/app')
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Something went wrong. Please try again.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <AuthScaffold
      title="Create your account"
      subtitle="Two free workspaces to try HelpFlow on real sites — no card needed."
      footer={
        <>
          Already have an account?{' '}
          <Link href="/login" className="font-semibold text-brand hover:underline">
            Sign in
          </Link>
        </>
      }
    >
      <form onSubmit={onSubmit} className="space-y-4" noValidate>
        <div>
          <label htmlFor="email" className="mb-1.5 block text-sm font-semibold">
            Email
          </label>
          <input
            id="email"
            type="email"
            required
            autoComplete="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="min-h-[44px] w-full rounded-xl border border-border bg-surface px-3.5 text-sm focus-visible:outline-none"
            placeholder="you@example.com"
          />
        </div>
        <div>
          <label htmlFor="password" className="mb-1.5 block text-sm font-semibold">
            Password
          </label>
          <div className="relative">
            <input
              id="password"
              type={showPassword ? 'text' : 'password'}
              required
              minLength={8}
              autoComplete="new-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              aria-describedby="password-hint"
              className="min-h-[44px] w-full rounded-xl border border-border bg-surface px-3.5 pr-11 text-sm focus-visible:outline-none"
              placeholder="At least 8 characters"
            />
            <button
              type="button"
              onClick={() => setShowPassword((v) => !v)}
              aria-label={showPassword ? 'Hide password' : 'Show password'}
              className="absolute right-1 top-1/2 flex size-9 -translate-y-1/2 cursor-pointer items-center justify-center rounded-lg text-foreground-muted hover:text-foreground"
            >
              {showPassword ? <EyeOff className="size-4" aria-hidden="true" /> : <Eye className="size-4" aria-hidden="true" />}
            </button>
          </div>
          <p
            id="password-hint"
            className={`mt-1.5 text-xs ${passwordTooShort ? 'font-medium text-destructive' : 'text-foreground-muted'}`}
          >
            {passwordTooShort ? 'Needs at least 8 characters.' : '8+ characters.'}
          </p>
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
          Create account
        </button>
      </form>
    </AuthScaffold>
  )
}
