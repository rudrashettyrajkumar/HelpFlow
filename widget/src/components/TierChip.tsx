import { ChevronRight, Sparkles } from 'lucide-react'
import type { LLMConfig } from '../lib/llmConfig'

type Props = {
  config: LLMConfig
  /** Only true inside the portal's own preview iframe — hidden on external
   * embeds (spec Req 3). */
  canOpenModelStudio: boolean
}

function openModelStudio() {
  window.parent.postMessage({ type: 'hf:open-model-studio' }, '*')
}

/** "Free demo" / the selected model name, shown in the composer (spec Req 3).
 * Clicking deep-links to Model Studio when the widget runs inside the
 * portal's own preview. */
export function TierChip({ config, canOpenModelStudio }: Props) {
  const label = config.mode === 'byok' ? config.modelName : 'Free demo'

  const content = (
    <>
      <Sparkles className="size-3 text-brand" aria-hidden="true" />
      {label}
      {canOpenModelStudio && <ChevronRight className="size-3" aria-hidden="true" />}
    </>
  )

  const className =
    'flex items-center gap-1 rounded-full border border-border bg-surface-muted px-2.5 py-1 text-[11px] font-medium text-foreground-muted'

  if (!canOpenModelStudio) {
    return <span className={className}>{content}</span>
  }
  return (
    <button
      type="button"
      onClick={openModelStudio}
      className={`${className} cursor-pointer transition-colors hover:text-foreground`}
    >
      {content}
    </button>
  )
}
