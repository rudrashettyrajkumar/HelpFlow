'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import { fetchModelCatalog } from './api'
import { DEMO_CONFIG, loadLLMConfig, saveLLMConfig } from './llmConfig'
import type { LLMConfig } from './llmConfig'
import type { ModelInfo, ModelsCatalog, ProviderInfo } from './types'

/** Shared Model Studio state — used by both the wizard's inline step 3 and
 * the full `/app/studio` page, so provider/model selection logic exists in
 * exactly one place. */
export function useModelStudio() {
  const [catalog, setCatalog] = useState<ModelsCatalog | null>(null)
  const [catalogError, setCatalogError] = useState<string | null>(null)
  const [draft, setDraft] = useState<LLMConfig>(loadLLMConfig)
  const [customModel, setCustomModel] = useState('')

  useEffect(() => {
    fetchModelCatalog()
      .then((data) => {
        setCatalog(data)
        setCatalogError(null)
      })
      .catch(() => setCatalogError("Couldn't load the model catalog. Refresh to try again."))
  }, [])

  const provider = useMemo<ProviderInfo | null>(
    () => catalog?.providers.find((p) => p.id === draft.provider) ?? null,
    [catalog, draft.provider],
  )

  const pickProvider = useCallback((p: ProviderInfo) => {
    const recommended = p.models.find((m) => m.recommended) ?? p.models[0]
    const embed = p.embedding_models.find((m) => m.recommended) ?? p.embedding_models[0]
    setCustomModel('')
    setDraft((d) => ({
      ...d,
      mode: 'byok',
      provider: p.id,
      model: recommended?.id ?? '',
      modelName: recommended?.name ?? '',
      byokEmbeddings: d.byokEmbeddings && p.embedding_models.length > 0,
      embedProvider: p.embedding_models.length > 0 ? p.id : '',
      embedModel: embed?.id ?? '',
      apiKey: d.provider === p.id ? d.apiKey : '',
    }))
  }, [])

  const pickDemo = useCallback(() => setDraft(DEMO_CONFIG), [])

  const pickModel = useCallback((m: ModelInfo) => {
    setCustomModel('')
    setDraft((d) => ({ ...d, model: m.id, modelName: m.name }))
  }, [])

  const applyCustomModel = useCallback((value: string) => {
    setCustomModel(value)
    const id = value.trim()
    if (id) setDraft((d) => ({ ...d, model: id, modelName: id }))
  }, [])

  const setApiKey = useCallback((value: string) => {
    setDraft((d) => ({ ...d, apiKey: value, embedApiKey: d.byokEmbeddings ? value : d.embedApiKey }))
  }, [])

  const toggleByokEmbeddings = useCallback((checked: boolean) => {
    setDraft((d) => ({ ...d, byokEmbeddings: checked, embedApiKey: checked ? d.apiKey : '' }))
  }, [])

  const setEmbedModel = useCallback((id: string) => {
    setDraft((d) => ({ ...d, embedModel: id }))
  }, [])

  const canSaveByok =
    draft.provider !== '' && draft.apiKey.trim().length > 0 && draft.model.trim().length > 0

  const save = useCallback(() => {
    saveLLMConfig(draft.mode === 'demo' ? DEMO_CONFIG : { ...draft, mode: 'byok' })
  }, [draft])

  return {
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
    canSaveByok,
    save,
  }
}
