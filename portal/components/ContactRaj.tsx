import { Briefcase, Mail, MessageCircle } from 'lucide-react'
import { RAJ } from '@/lib/config'

/** The warm, personal contact block for the premium gate (spec Req 6):
 * "zero-pressure — name/photo/positioning line, LinkedIn + WhatsApp +
 * email buttons." No photo asset shipped with this repo, so the avatar is a
 * monogram — swap for a real photo when deploying. */
export function ContactRaj() {
  return (
    <div className="flex flex-col items-center gap-3 text-center">
      <span className="flex size-16 items-center justify-center rounded-full bg-brand-gradient text-2xl font-extrabold text-white shadow-glow">
        {RAJ.name.charAt(0)}
      </span>
      <div>
        <p className="text-lg font-extrabold">{RAJ.name}</p>
        <p className="text-sm text-foreground-muted">Built HelpFlow end to end — happy to talk through your use case.</p>
      </div>
      <div className="flex flex-wrap items-center justify-center gap-2">
        {RAJ.linkedin && (
          <a
            href={RAJ.linkedin}
            target="_blank"
            rel="noreferrer"
            className="flex min-h-[40px] items-center gap-1.5 rounded-xl border border-border px-3.5 text-sm font-semibold transition-colors hover:border-brand/40"
          >
            <Briefcase className="size-4" aria-hidden="true" /> LinkedIn
          </a>
        )}
        {RAJ.whatsapp && (
          <a
            href={RAJ.whatsapp}
            target="_blank"
            rel="noreferrer"
            className="flex min-h-[40px] items-center gap-1.5 rounded-xl border border-border px-3.5 text-sm font-semibold transition-colors hover:border-brand/40"
          >
            <MessageCircle className="size-4" aria-hidden="true" /> WhatsApp
          </a>
        )}
        {RAJ.email && (
          <a
            href={`mailto:${RAJ.email}`}
            className="flex min-h-[40px] items-center gap-1.5 rounded-xl border border-border px-3.5 text-sm font-semibold transition-colors hover:border-brand/40"
          >
            <Mail className="size-4" aria-hidden="true" /> Email
          </a>
        )}
      </div>
    </div>
  )
}
