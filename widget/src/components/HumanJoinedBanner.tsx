import { UserRound } from 'lucide-react'

/** Shown once, right before the first live agent reply renders (spec Req 6:
 * "agent reply → message with display name + 'human joined' banner, first
 * time"). Position in the transcript — not connection state — decides "first
 * time", so it never re-fires on a `/chat/subscribe` reconnect replay. */
export function HumanJoinedBanner() {
  return (
    <div className="animate-fade-in flex items-center justify-center gap-2 py-1">
      <div className="h-px flex-1 bg-border" />
      <span className="flex items-center gap-1.5 whitespace-nowrap rounded-full bg-success/15 px-3 py-1 text-xs font-semibold text-success">
        <UserRound className="size-3.5" aria-hidden="true" />
        A human joined the conversation
      </span>
      <div className="h-px flex-1 bg-border" />
    </div>
  )
}
