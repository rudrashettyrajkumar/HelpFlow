import { useRef, type KeyboardEvent } from 'react'
import { ArrowUp } from 'lucide-react'
import type { LLMConfig } from '../lib/llmConfig'
import { TierChip } from './TierChip'

type Props = {
  value: string
  onChange: (value: string) => void
  onSend: () => void
  disabled: boolean
  config: LLMConfig
  canOpenModelStudio: boolean
}

export function Composer({ value, onChange, onSend, disabled, config, canOpenModelStudio }: Props) {
  const areaRef = useRef<HTMLTextAreaElement>(null)

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      if (value.trim() && !disabled) onSend()
    }
  }

  const autoGrow = () => {
    const el = areaRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, 96)}px`
  }

  return (
    <div className="border-t border-border px-3 pb-3 pt-2">
      <div className="mb-1.5 flex items-center justify-between">
        <TierChip config={config} canOpenModelStudio={canOpenModelStudio} />
        <span className="text-[11px] text-foreground-muted">Powered by HelpFlow</span>
      </div>
      <div className="glass flex items-end gap-2 rounded-2xl px-2 py-1.5">
        <textarea
          ref={areaRef}
          value={value}
          onChange={(e) => {
            onChange(e.target.value)
            autoGrow()
          }}
          onKeyDown={handleKeyDown}
          disabled={disabled}
          rows={1}
          placeholder="Ask a question…"
          aria-label="Message"
          className="max-h-24 flex-1 resize-none bg-transparent px-2 py-2 text-sm leading-relaxed text-foreground placeholder:text-foreground-muted focus:outline-none disabled:opacity-60"
        />
        <button
          onClick={onSend}
          disabled={disabled || !value.trim()}
          aria-label="Send message"
          className="flex size-9 shrink-0 cursor-pointer items-center justify-center rounded-full bg-brand-gradient text-white shadow-glow transition-transform duration-150 hover:scale-105 active:scale-95 disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:scale-100"
        >
          <ArrowUp className="size-4" aria-hidden="true" />
        </button>
      </div>
    </div>
  )
}
