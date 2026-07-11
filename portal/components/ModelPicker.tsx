import { Check } from 'lucide-react'
import { AccuracyMeter } from './AccuracyMeter'
import type { ModelInfo, ProviderInfo } from '@/lib/types'

const SPEED_LABEL: Record<ModelInfo['speed'], string> = {
  blazing: 'Blazing',
  fast: 'Fast',
  balanced: 'Balanced',
  deliberate: 'Deliberate',
}

function ModelCard({
  model,
  selected,
  onSelect,
}: {
  model: ModelInfo
  selected: boolean
  onSelect: () => void
}) {
  return (
    <button
      type="button"
      onClick={onSelect}
      aria-pressed={selected}
      className={`glass w-full cursor-pointer rounded-2xl p-3.5 text-left transition-colors ${
        selected ? 'ring-2 ring-brand' : 'hover:border-brand/40'
      }`}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="truncate text-sm font-bold">{model.name}</p>
          <p className="mt-0.5 truncate text-[11px] text-foreground-muted">{model.id}</p>
        </div>
        <div className="flex shrink-0 items-center gap-1">
          {model.recommended && (
            <span className="rounded-full bg-brand-2/15 px-2 py-0.5 text-[10px] font-bold text-brand-2">
              PICK
            </span>
          )}
          {model.free && (
            <span className="rounded-full bg-success/15 px-2 py-0.5 text-[10px] font-bold text-success">
              FREE
            </span>
          )}
          {selected && <Check className="size-4 text-brand" aria-hidden="true" />}
        </div>
      </div>
      <div className="mt-2.5 flex flex-wrap items-center gap-x-3 gap-y-1.5">
        <AccuracyMeter tier={model.accuracy} />
        <span className="text-[11px] font-medium text-foreground-muted">
          {SPEED_LABEL[model.speed]}
        </span>
        <span className="text-[11px] font-medium text-foreground-muted">{model.context} ctx</span>
        <span className="text-[11px] font-medium text-foreground-muted">{model.cost}</span>
      </div>
      {model.notes && <p className="mt-2 text-[11px] leading-snug text-foreground-muted">{model.notes}</p>}
    </button>
  )
}

type Props = {
  provider: ProviderInfo
  selectedModel: string
  onSelectModel: (m: ModelInfo) => void
  customModel: string
  onCustomModel: (value: string) => void
}

/** Chat-model grid for the selected provider + the OpenRouter custom-model-id
 * escape hatch (spec Req 4). */
export function ModelPicker({ provider, selectedModel, onSelectModel, customModel, onCustomModel }: Props) {
  return (
    <div>
      <p className="mb-2 text-xs font-bold uppercase tracking-wide text-foreground-muted">
        Choose a model
      </p>
      <div className="grid gap-2.5 sm:grid-cols-2">
        {provider.models.map((m) => (
          <ModelCard key={m.id} model={m} selected={selectedModel === m.id} onSelect={() => onSelectModel(m)} />
        ))}
      </div>
      {provider.allows_custom_model && (
        <div className="mt-2.5">
          <label htmlFor="custom-model" className="mb-1 block text-[11px] font-semibold text-foreground-muted">
            Or paste any {provider.name} model ID
          </label>
          <input
            id="custom-model"
            value={customModel}
            onChange={(e) => onCustomModel(e.target.value)}
            placeholder="e.g. deepseek/deepseek-chat-v3.1"
            spellCheck={false}
            className="min-h-[44px] w-full rounded-xl border border-border bg-surface px-3.5 text-sm focus-visible:outline-none"
          />
        </div>
      )}
    </div>
  )
}
