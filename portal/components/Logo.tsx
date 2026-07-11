import { MessageCircle } from 'lucide-react'

export function Logo({ className = '' }: { className?: string }) {
  return (
    <span className={`inline-flex items-center gap-2 font-extrabold tracking-tight ${className}`}>
      <span className="flex size-7 items-center justify-center rounded-xl bg-brand-gradient text-white shadow-glow">
        <MessageCircle className="size-4" aria-hidden="true" />
      </span>
      HelpFlow
    </span>
  )
}
