import { useEffect, useRef } from 'react'
import type { ChatItem } from '../api/types'
import { Message } from './Message'

type Props = {
  items: ChatItem[]
  canOpenModelStudio: boolean
  onCitationClick: (assistantId: string, n: number) => void
  onRetry: (assistantId: string) => void
}

export function MessageList({ items, canOpenModelStudio, onCitationClick, onRetry }: Props) {
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [items])

  const firstAgentId = items.find((it) => it.kind === 'agent')?.id

  return (
    <div className="flex flex-1 flex-col gap-4 overflow-y-auto px-4 py-4">
      {items.map((item) => (
        <Message
          key={item.id}
          item={item}
          isFirstAgentReply={item.kind === 'agent' && item.id === firstAgentId}
          canOpenModelStudio={canOpenModelStudio}
          onCitationClick={(n) => onCitationClick(item.id, n)}
          onRetry={onRetry}
        />
      ))}
      <div ref={bottomRef} />
    </div>
  )
}
