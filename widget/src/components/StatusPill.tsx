import { Loader2 } from 'lucide-react'

type Props = {
  label: string
}

/** Typing/connecting/reconnecting indicator (spec Req 7). */
export function StatusPill({ label }: Props) {
  return (
    <div
      className="animate-fade-in flex w-fit items-center gap-1.5 rounded-full bg-surface-muted px-3 py-1.5 text-xs font-medium text-foreground-muted"
      role="status"
      aria-live="polite"
    >
      <Loader2 className="size-3.5 animate-spin" aria-hidden="true" />
      {label}
    </div>
  )
}
