import type { ReactNode } from 'react'
import Link from 'next/link'
import { Check } from 'lucide-react'
import { Logo } from './Logo'
import { ThemeToggle } from './ThemeToggle'

const PERKS = [
  'Grounded, cited answers — never a guess',
  'A human takes over the moment the AI doesn\'t know',
  'Free demo mode — no key, no card, chatting in minutes',
]

/** Split layout: branded glassy left rail + form card on the right — ported
 * from DocChat v2's AuthScaffold, same family look (spec: "port DocChat v2's
 * auth-page + AuthContext patterns"). */
export function AuthScaffold({
  title,
  subtitle,
  children,
  footer,
}: {
  title: string
  subtitle: string
  children: ReactNode
  footer: ReactNode
}) {
  return (
    <div className="min-h-dvh lg:grid lg:grid-cols-2">
      <aside className="relative hidden flex-col justify-between overflow-hidden p-12 lg:flex">
        <div className="glass absolute inset-6 -z-10 rounded-3xl" aria-hidden="true" />
        <Link href="/">
          <Logo />
        </Link>
        <div className="max-w-md">
          <h2 className="text-3xl font-extrabold leading-tight">
            An AI support agent that knows <span className="text-gradient">when to get a human</span>.
          </h2>
          <ul className="mt-8 space-y-4">
            {PERKS.map((perk) => (
              <li key={perk} className="flex items-start gap-3">
                <span className="mt-0.5 grid size-6 shrink-0 place-items-center rounded-full bg-brand-gradient text-white">
                  <Check className="size-3.5" aria-hidden="true" />
                </span>
                <span className="text-foreground-muted">{perk}</span>
              </li>
            ))}
          </ul>
        </div>
        <p className="text-sm text-foreground-muted">Built by Raj · LangChain · LangGraph · FastAPI · n8n</p>
      </aside>

      <main className="flex min-h-dvh flex-col items-center justify-center px-5 py-10">
        <div className="mb-6 flex w-full max-w-md items-center justify-between lg:hidden">
          <Link href="/">
            <Logo />
          </Link>
          <ThemeToggle />
        </div>
        <div className="glass-strong w-full max-w-md animate-fade-up rounded-3xl p-8 sm:p-10">
          <div className="mb-8">
            <h1 className="text-2xl font-extrabold tracking-tight">{title}</h1>
            <p className="mt-1.5 text-foreground-muted">{subtitle}</p>
          </div>
          {children}
          <div className="mt-6 text-center text-sm text-foreground-muted">{footer}</div>
        </div>
        <div className="mt-6 hidden lg:block">
          <ThemeToggle />
        </div>
      </main>
    </div>
  )
}
