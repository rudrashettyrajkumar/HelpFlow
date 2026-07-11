'use client'

import { AlertTriangle, Loader2 } from 'lucide-react'
import { DemoBudgetCard } from './DemoBudgetCard'
import { KeyTester } from './KeyTester'
import { ModelPicker } from './ModelPicker'
import { ProviderCard } from './ProviderCard'
import type { useModelStudio } from '@/lib/useModelStudio'

type Props = ReturnType<typeof useModelStudio>

/** The Model Studio's core UI — provider grid, demo-mode card, and the
 * selected provider's key test + model picker. Shared by the full
 * `/app/studio` page and the wizard's inline, skippable step 3 (spec Req 4). */
export function ModelStudioBody({
  catalog,
  catalogError,
  draft,
  provider,
  customModel,
  pickProvider,
  pickDemo,
  pickModel,
  applyCustomModel,
  setApiKey,
  toggleByokEmbeddings,
  setEmbedModel,
}: Props) {
  if (catalogError) {
    return (
      <p className="flex items-center gap-2 rounded-2xl bg-destructive/10 px-4 py-3 text-sm font-medium text-destructive">
        <AlertTriangle className="size-4 shrink-0" aria-hidden="true" />
        {catalogError}
      </p>
    )
  }

  if (!catalog) {
    return (
      <div className="flex items-center justify-center gap-2 py-16 text-sm text-foreground-muted">
        <Loader2 className="size-4 animate-spin" aria-hidden="true" /> Loading models…
      </div>
    )
  }

  return (
    <div className="space-y-5">
      <DemoBudgetCard selected={draft.mode === 'demo'} onSelect={pickDemo} />

      <div>
        <p className="mb-2 text-xs font-bold uppercase tracking-wide text-foreground-muted">
          Or connect a provider
        </p>
        <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-5">
          {catalog.providers.map((p) => (
            <ProviderCard
              key={p.id}
              provider={p}
              selected={draft.mode === 'byok' && draft.provider === p.id}
              onSelect={() => pickProvider(p)}
            />
          ))}
        </div>
      </div>

      {provider && draft.mode === 'byok' && (
        <div className="space-y-4">
          <KeyTester provider={provider} model={draft.model} apiKey={draft.apiKey} onApiKeyChange={setApiKey} />

          <ModelPicker
            provider={provider}
            selectedModel={draft.model}
            onSelectModel={pickModel}
            customModel={customModel}
            onCustomModel={applyCustomModel}
          />

          {provider.embedding_models.length === 0 && (
            <p className="rounded-2xl border border-border px-3.5 py-3 text-xs text-foreground-muted">
              {provider.name} doesn&apos;t offer an embedding model — pair this key with a
              free OpenRouter key for embeddings, or stick with HelpFlow&apos;s default.
            </p>
          )}

          {provider.embedding_models.length > 0 && (
            <div className="rounded-2xl border border-border p-3.5">
              <label className="flex cursor-pointer items-center justify-between gap-3">
                <span>
                  <span className="block text-sm font-bold">Use my key for embeddings too</span>
                  <span className="mt-0.5 block text-xs text-foreground-muted">
                    Off = your crawl indexes with HelpFlow&apos;s default embedder.
                  </span>
                </span>
                <input
                  type="checkbox"
                  checked={draft.byokEmbeddings}
                  onChange={(e) => toggleByokEmbeddings(e.target.checked)}
                  className="size-5 shrink-0 cursor-pointer accent-[rgb(var(--brand))]"
                />
              </label>
              {draft.byokEmbeddings && (
                <div className="mt-3 space-y-2">
                  {provider.embedding_models.map((m) => (
                    <label
                      key={m.id}
                      className="flex min-h-[44px] cursor-pointer items-center gap-2.5 rounded-xl border border-border px-3 py-2 text-sm has-[:checked]:border-brand"
                    >
                      <input
                        type="radio"
                        name="embed-model"
                        checked={draft.embedModel === m.id}
                        onChange={() => setEmbedModel(m.id)}
                        className="cursor-pointer accent-[rgb(var(--brand))]"
                      />
                      <span className="font-semibold">{m.name}</span>
                      <span className="text-xs text-foreground-muted">{m.cost}</span>
                      {m.recommended && (
                        <span className="rounded-full bg-brand-2/15 px-2 py-0.5 text-[10px] font-bold text-brand-2">
                          PICK
                        </span>
                      )}
                    </label>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
