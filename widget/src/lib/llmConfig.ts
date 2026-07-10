// BYOK model configuration — read-only here (E8's Model Studio, same shared
// localStorage key, is the only writer). Demo mode (no config saved) sends no
// BYOK headers at all; the backend then serves its own env-configured models
// under the daily demo budget (ARCHITECTURE §4.3/§4.4).
//
// A `storage` event listener lets the TierChip re-render live if the owner has
// the portal's Model Studio open in another tab/frame while previewing this
// same widget (E8's wizard preview embeds this widget directly).

const STORAGE_KEY = 'hf_llm_config_v1'

export type LLMConfig = {
  mode: 'demo' | 'byok'
  provider: string
  model: string
  /** Display name of the model, denormalized for the TierChip. */
  modelName: string
  apiKey: string
  byokEmbeddings: boolean
  embedProvider: string
  embedModel: string
  embedApiKey: string
}

export const DEMO_CONFIG: LLMConfig = {
  mode: 'demo',
  provider: '',
  model: '',
  modelName: 'Free demo',
  apiKey: '',
  byokEmbeddings: false,
  embedProvider: '',
  embedModel: '',
  embedApiKey: '',
}

export function loadLLMConfig(): LLMConfig {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return DEMO_CONFIG
    const parsed = JSON.parse(raw) as Partial<LLMConfig>
    if (parsed.mode !== 'byok' || !parsed.provider || !parsed.apiKey) return DEMO_CONFIG
    return { ...DEMO_CONFIG, ...parsed, mode: 'byok' }
  } catch {
    return DEMO_CONFIG
  }
}

export function onLLMConfigChange(listener: () => void): () => void {
  const handler = (e: StorageEvent) => {
    if (e.key === null || e.key === STORAGE_KEY) listener()
  }
  window.addEventListener('storage', handler)
  return () => window.removeEventListener('storage', handler)
}

/** The BYOK request headers for the current config ({} in demo mode). */
export function byokHeaders(): Record<string, string> {
  const config = loadLLMConfig()
  if (config.mode !== 'byok' || !config.apiKey) return {}
  const headers: Record<string, string> = {
    'X-LLM-Provider': config.provider,
    'X-LLM-Model': config.model,
    'X-LLM-Key': config.apiKey,
  }
  if (config.byokEmbeddings && config.embedProvider && config.embedApiKey) {
    headers['X-Embed-Provider'] = config.embedProvider
    headers['X-Embed-Model'] = config.embedModel
    headers['X-Embed-Key'] = config.embedApiKey
  }
  return headers
}

/** Deep-link back into the portal's Model Studio (hidden on external embeds —
 * only rendered when the widget detects it's running inside the portal preview
 * iframe, spec Req 3). */
export const MODEL_STUDIO_PATH = '/model-studio'
