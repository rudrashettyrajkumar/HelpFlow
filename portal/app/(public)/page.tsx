import Link from 'next/link'
import { ArrowRight, Briefcase, Code2, Key, Mail, MessageCircle, Sparkles, Wand2 } from 'lucide-react'
import { ArchitectureDiagram } from '@/components/ArchitectureDiagram'
import { GradientMesh } from '@/components/GradientMesh'
import { Logo } from '@/components/Logo'
import { ThemeToggle } from '@/components/ThemeToggle'
import { TierCard } from '@/components/TierCard'
import { WidgetEmbed } from '@/components/WidgetEmbed'
import { DEMO_TENANT_WIDGET_KEY, RAJ } from '@/lib/config'

const TECH_CHIPS = ['LangChain', 'LangGraph', 'FastAPI', 'n8n', 'Qdrant', 'Supabase']

export default function LandingPage() {
  return (
    <div className="relative overflow-x-hidden">
      <nav className="mx-auto flex max-w-6xl items-center justify-between px-5 py-5">
        <Logo />
        <div className="flex items-center gap-2">
          <ThemeToggle />
          <Link
            href="/login"
            className="hidden min-h-[40px] items-center rounded-xl px-3.5 text-sm font-semibold text-foreground-muted hover:text-foreground sm:flex"
          >
            Sign in
          </Link>
          <Link
            href="/register"
            className="flex min-h-[40px] items-center gap-1.5 rounded-xl bg-brand-gradient px-4 text-sm font-bold text-white shadow-glow transition-all hover:brightness-110"
          >
            Get started free
            <ArrowRight className="size-4" aria-hidden="true" />
          </Link>
        </div>
      </nav>

      {/* Hero */}
      <section className="relative px-5 pb-20 pt-10 sm:pt-16">
        <GradientMesh />
        <div className="mx-auto grid max-w-6xl items-center gap-10 lg:grid-cols-[1.1fr_0.9fr]">
          <div className="animate-fade-up">
            <span className="inline-flex items-center gap-1.5 rounded-full bg-brand/15 px-3 py-1 text-xs font-bold text-brand">
              <Sparkles className="size-3.5" aria-hidden="true" />
              Free demo mode — no key, no card
            </span>
            <h1 className="mt-5 text-4xl font-extrabold leading-[1.1] tracking-tight sm:text-5xl">
              An AI support agent that knows{' '}
              <span className="text-gradient">when to get a human</span>.
            </h1>
            <p className="mt-5 max-w-xl text-lg text-foreground-muted">
              Paste your site, watch it learn, and get a grounded, cited chat widget in
              minutes. When the AI genuinely doesn&apos;t know, it hands off to a real
              person instead of guessing.
            </p>
            <div className="mt-8 flex flex-wrap items-center gap-3">
              <Link
                href="/register"
                className="flex min-h-[48px] items-center gap-2 rounded-xl bg-brand-gradient px-6 text-sm font-bold text-white shadow-glow transition-all hover:brightness-110"
              >
                Try it on your own site
                <ArrowRight className="size-4" aria-hidden="true" />
              </Link>
              <a
                href="#tiers"
                className="flex min-h-[48px] items-center rounded-xl border border-border px-6 text-sm font-semibold transition-colors hover:border-brand/40"
              >
                See how it works
              </a>
            </div>
            <p className="mt-4 text-xs text-foreground-muted">
              → Ask the widget anything about this fake company on the right.
            </p>
          </div>

          <div className="relative">
            <div className="glass-strong rounded-3xl p-4 sm:p-6">
              <p className="mb-3 text-xs font-bold uppercase tracking-wide text-foreground-muted">
                Live demo — Acme Co
              </p>
              <div className="flex h-[420px] items-center justify-center rounded-2xl border border-dashed border-border text-center text-sm text-foreground-muted">
                {DEMO_TENANT_WIDGET_KEY ? (
                  <span>Chat bubble is bottom-right of this page →</span>
                ) : (
                  <span className="px-6">
                    Demo tenant not configured yet — set
                    <code className="mx-1 rounded bg-surface-muted px-1.5 py-0.5">
                      NEXT_PUBLIC_DEMO_TENANT_WIDGET_KEY
                    </code>
                    to show the live widget here.
                  </span>
                )}
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Three-tier explainer */}
      <section id="tiers" className="px-5 py-16">
        <div className="mx-auto max-w-6xl">
          <div className="mb-10 text-center">
            <h2 className="text-3xl font-extrabold tracking-tight">Three honest tiers</h2>
            <p className="mx-auto mt-2 max-w-xl text-foreground-muted">
              Start free, no card. Bring your own key whenever you want more control — your
              key never touches our servers.
            </p>
          </div>
          <div className="grid gap-5 sm:grid-cols-3">
            <TierCard
              icon={MessageCircle}
              name="Demo mode"
              tagline="Zero setup — chatting in seconds"
              points={[
                "Raj's shared free-tier keys (Groq + OpenRouter)",
                'Free open-source models only — never paid or proprietary',
                'Shared daily budget; resets midnight UTC, honest when it runs out',
              ]}
              highlighted
            />
            <TierCard
              icon={Key}
              name="Free BYOK"
              tagline="Your own free key, no card"
              points={[
                'Bring a Groq and/or OpenRouter key — genuinely free',
                'Curated open-source models: Nemotron, Llama 3.3, GPT-OSS, Qwen3',
                'Your quota, not a shared one — no rate-limit surprises',
              ]}
            />
            <TierCard
              icon={Wand2}
              name="Paid BYOK"
              tagline="Any provider, your billing"
              points={[
                'OpenRouter, OpenAI, Gemini, or Anthropic',
                'Full model picker + a custom-model-id escape hatch',
                'No HelpFlow-side cap — your account, your limits',
              ]}
            />
          </div>
        </div>
      </section>

      {/* Architecture */}
      <section className="px-5 py-16">
        <div className="mx-auto max-w-6xl">
          <div className="mb-8 text-center">
            <h2 className="text-3xl font-extrabold tracking-tight">How it works</h2>
            <p className="mx-auto mt-2 max-w-xl text-foreground-muted">
              One clean path from your website to a resolved conversation.
            </p>
          </div>
          <ArchitectureDiagram />
          <div className="mt-6 flex flex-wrap justify-center gap-2">
            {TECH_CHIPS.map((chip) => (
              <span
                key={chip}
                className="rounded-full border border-border bg-surface-muted px-3 py-1.5 text-xs font-semibold text-foreground-muted"
              >
                {chip}
              </span>
            ))}
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-border px-5 py-10">
        <div className="mx-auto flex max-w-6xl flex-col items-center justify-between gap-4 sm:flex-row">
          <div className="text-center sm:text-left">
            <Logo />
            <p className="mt-1.5 text-xs text-foreground-muted">
              Built by {RAJ.name} — a self-serve RAG support agent, end to end.
            </p>
          </div>
          <div className="flex items-center gap-3">
            {RAJ.linkedin && (
              <a
                href={RAJ.linkedin}
                target="_blank"
                rel="noreferrer"
                aria-label={`${RAJ.name} on LinkedIn`}
                className="flex size-9 items-center justify-center rounded-full border border-border text-foreground-muted hover:text-foreground"
              >
                <Briefcase className="size-4" aria-hidden="true" />
              </a>
            )}
            {RAJ.github && (
              <a
                href={RAJ.github}
                target="_blank"
                rel="noreferrer"
                aria-label={`${RAJ.name} on GitHub`}
                className="flex size-9 items-center justify-center rounded-full border border-border text-foreground-muted hover:text-foreground"
              >
                <Code2 className="size-4" aria-hidden="true" />
              </a>
            )}
            {RAJ.email && (
              <a
                href={`mailto:${RAJ.email}`}
                aria-label={`Email ${RAJ.name}`}
                className="flex size-9 items-center justify-center rounded-full border border-border text-foreground-muted hover:text-foreground"
              >
                <Mail className="size-4" aria-hidden="true" />
              </a>
            )}
          </div>
        </div>
      </footer>

      {DEMO_TENANT_WIDGET_KEY && <WidgetEmbed widgetKey={DEMO_TENANT_WIDGET_KEY} />}
    </div>
  )
}
