import { AlertCircle, HeartHandshake, Mail, RotateCw } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import type { Components } from 'react-markdown'
import type { ChatItem } from '../api/types'
import { annotateCitations } from '../lib/citations'
import { CitationChip } from './CitationChip'
import { HumanJoinedBanner } from './HumanJoinedBanner'
import { NoticeCard } from './NoticeCard'

type Props = {
  item: ChatItem
  /** True for the first `agent`-kind item in the transcript (spec Req 6). */
  isFirstAgentReply: boolean
  canOpenModelStudio: boolean
  onCitationClick: (n: number) => void
  onRetry: (assistantId: string) => void
}

function markdownComponents(onCitationClick: Props['onCitationClick']): Components {
  return {
    p: ({ children }) => <p className="[&:not(:first-child)]:mt-2">{children}</p>,
    a: ({ href, children }) => {
      if (href?.startsWith('citation:')) {
        const n = Number(href.slice('citation:'.length))
        return <CitationChip n={n} onClick={() => onCitationClick(n)} />
      }
      return (
        <a href={href} target="_blank" rel="noreferrer" className="underline">
          {children}
        </a>
      )
    },
  }
}

export function Message({ item, isFirstAgentReply, canOpenModelStudio, onCitationClick, onRetry }: Props) {
  if (item.kind === 'user') {
    return (
      <div className="animate-fade-up flex justify-end">
        <div className="max-w-[82%] rounded-2xl rounded-br-sm bg-brand-gradient px-4 py-2.5 text-sm text-white shadow-glow">
          {item.text}
        </div>
      </div>
    )
  }

  if (item.kind === 'assistant') {
    const displayText =
      item.streamState === 'streaming' || item.streamState === 'reconnecting'
        ? item.text
        : annotateCitations(item.text, item.sources)

    return (
      <div className="animate-fade-up flex flex-col gap-1.5">
        {item.text && (
          <div className="max-w-[85%] rounded-2xl rounded-bl-sm border border-border bg-surface/60 px-4 py-2.5 text-sm leading-relaxed">
            <div className="prose prose-sm max-w-none dark:prose-invert prose-p:my-0">
              <ReactMarkdown components={markdownComponents(onCitationClick)}>
                {displayText}
              </ReactMarkdown>
            </div>
            {item.streamState === 'streaming' && (
              <span
                className="ml-0.5 inline-block h-3.5 w-0.5 animate-blink bg-brand align-middle motion-reduce:animate-none"
                aria-hidden="true"
              />
            )}
          </div>
        )}

        {item.streamState === 'reconnecting' && (
          <div className="flex items-center gap-1.5 pl-1 text-xs text-foreground-muted">
            <RotateCw className="size-3 animate-spin" aria-hidden="true" />
            Reconnecting…
          </div>
        )}

        {(item.streamState === 'error' || item.streamState === 'rate_limited') && (
          <div className="flex max-w-[85%] items-start gap-2 rounded-xl border border-destructive/25 bg-destructive/10 px-3 py-2 text-xs text-destructive">
            <AlertCircle className="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />
            <span className="flex-1">{item.errorDetail}</span>
            {item.streamState === 'error' && (
              <button
                onClick={() => onRetry(item.id)}
                className="shrink-0 cursor-pointer font-semibold underline underline-offset-2"
              >
                Try again
              </button>
            )}
          </div>
        )}
      </div>
    )
  }

  if (item.kind === 'agent') {
    return (
      <>
        {isFirstAgentReply && <HumanJoinedBanner />}
        <div className="animate-fade-up flex flex-col gap-1">
          <span className="pl-1 text-[11px] font-semibold text-success">Agent</span>
          <div className="max-w-[85%] rounded-2xl rounded-bl-sm border-l-2 border-success bg-surface/60 px-4 py-2.5 text-sm leading-relaxed">
            {item.text}
          </div>
        </div>
      </>
    )
  }

  if (item.kind === 'notice') {
    return (
      <NoticeCard
        code={item.code}
        message={item.message}
        links={item.links}
        canOpenModelStudio={canOpenModelStudio}
      />
    )
  }

  if (item.kind === 'handoff') {
    return (
      <div className="animate-fade-up glass mx-auto flex max-w-[90%] flex-col items-center gap-1.5 rounded-2xl px-4 py-3 text-center">
        <HeartHandshake className="size-5 text-brand" aria-hidden="true" />
        <p className="text-sm font-medium">Connecting you to a person…</p>
        <p className="flex items-center gap-1 text-xs text-foreground-muted">
          <Mail className="size-3.5" aria-hidden="true" />
          No one around right now? Leave your email below and we'll follow up.
        </p>
      </div>
    )
  }

  // resolved
  return (
    <div className="animate-fade-in mx-auto flex w-fit items-center gap-1.5 rounded-full bg-success/15 px-3 py-1 text-xs font-semibold text-success">
      Conversation resolved
    </div>
  )
}
