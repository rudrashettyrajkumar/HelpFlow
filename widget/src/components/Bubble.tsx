import { MessageCircle, X } from 'lucide-react'

type Props = {
  open: boolean
  hasUnread: boolean
  onClick: () => void
}

/** The floating launcher (spec Req 1). Fixed at the iframe's bottom-right —
 * embed.js sizes/positions the IFRAME itself around this button, so the host
 * page never needs its own floating element. */
export function Bubble({ open, hasUnread, onClick }: Props) {
  return (
    <button
      onClick={onClick}
      aria-label={open ? 'Close chat' : 'Open chat'}
      aria-expanded={open}
      className="fixed bottom-4 right-4 z-[1000] flex size-14 cursor-pointer items-center justify-center rounded-full bg-brand-gradient text-white shadow-bubble transition-transform duration-200 hover:scale-105 active:scale-95"
    >
      {open ? (
        <X className="size-6" aria-hidden="true" />
      ) : (
        <MessageCircle className="size-6" aria-hidden="true" />
      )}
      {!open && hasUnread && (
        <span
          className="absolute right-0.5 top-0.5 size-3 rounded-full bg-destructive ring-2 ring-background"
          aria-hidden="true"
        />
      )}
    </button>
  )
}
