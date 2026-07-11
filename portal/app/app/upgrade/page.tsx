import { Sparkles } from 'lucide-react'
import { ContactRaj } from '@/components/ContactRaj'
import { Glass } from '@/components/Glass'
import { GradientMesh } from '@/components/GradientMesh'
import { LeadForm } from '@/components/LeadForm'

export default function UpgradePage() {
  return (
    <div className="relative mx-auto max-w-xl">
      <GradientMesh />
      <div className="mb-8 text-center">
        <span className="mx-auto mb-4 flex size-12 items-center justify-center rounded-2xl bg-brand-gradient text-white shadow-glow">
          <Sparkles className="size-6" aria-hidden="true" />
        </span>
        <h1 className="text-3xl font-extrabold tracking-tight">
          HelpFlow for your business, without limits
        </h1>
        <p className="mx-auto mt-2 max-w-md text-foreground-muted">
          You&apos;ve used both trial workspaces — that&apos;s usually a sign HelpFlow is actually
          useful for you. Let&apos;s talk about what you need.
        </p>
      </div>

      <Glass strong className="space-y-8 rounded-3xl p-6 sm:p-8">
        <ContactRaj />
        <div className="h-px bg-border" />
        <LeadForm source="gate" />
      </Glass>
    </div>
  )
}
