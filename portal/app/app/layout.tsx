'use client'

import { useEffect } from 'react'
import Link from 'next/link'
import { usePathname, useRouter } from 'next/navigation'
import { Loader2, Sliders, Store } from 'lucide-react'
import { Logo } from '@/components/Logo'
import { ThemeToggle } from '@/components/ThemeToggle'
import { TrialBadge } from '@/components/TrialBadge'
import { UserMenu } from '@/components/UserMenu'
import { useAuth } from '@/lib/auth-context'

const NAV = [
  { href: '/app', label: 'Workspaces', icon: Store },
  { href: '/app/studio', label: 'Model Studio', icon: Sliders },
]

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const { user, trialsUsed, initializing } = useAuth()
  const router = useRouter()
  const pathname = usePathname()

  useEffect(() => {
    if (!initializing && !user) router.replace('/login')
  }, [initializing, user, router])

  if (initializing) {
    return (
      <div className="flex min-h-dvh items-center justify-center">
        <Loader2 className="size-6 animate-spin text-brand" aria-hidden="true" />
      </div>
    )
  }

  if (!user) return null // redirecting

  return (
    <div className="min-h-dvh">
      <header className="border-b border-border">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-5 py-4">
          <div className="flex items-center gap-6">
            <Link href="/app">
              <Logo />
            </Link>
            <nav className="hidden items-center gap-1 sm:flex">
              {NAV.map((item) => {
                const active = pathname === item.href
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    className={`flex items-center gap-1.5 rounded-xl px-3 py-2 text-sm font-semibold transition-colors ${
                      active
                        ? 'bg-brand/10 text-brand'
                        : 'text-foreground-muted hover:text-foreground'
                    }`}
                  >
                    <item.icon className="size-4" aria-hidden="true" />
                    {item.label}
                  </Link>
                )
              })}
            </nav>
          </div>
          <div className="flex items-center gap-3">
            <TrialBadge trialsUsed={trialsUsed} />
            <ThemeToggle />
            <UserMenu />
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-5 py-8">{children}</main>
    </div>
  )
}
