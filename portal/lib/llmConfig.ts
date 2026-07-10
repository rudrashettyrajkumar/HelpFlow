// BYOK model configuration — the portal (Model Studio) is the WRITER; the
// widget (widget/src/lib/llmConfig.ts) is the reader. Same shape, same
// STORAGE_KEY name (though not the same literal storage — see
// `previewQueryParam` below and the design note in the widget's copy of this
// file: portal and widget are different origins, so the "shared" contract is
// this identical TYPE + a query-param handoff, not shared `localStorage`).

const STORAGE_KEY = 'hf_llm_config_v1'
const CHANGE_EVENT = 'hf-llm-config-changed'

export type LLMConfig = {
  mode: 'demo' | 'byok'
  provider: string
  model: string
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
  if (typeof window === 'undefined') return DEMO_CONFIG
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

export function saveLLMConfig(config: LLMConfig): void {
  if (config.mode === 'demo') {
    localStorage.removeItem(STORAGE_KEY)
  } else {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(config))
  }
  window.dispatchEvent(new Event(CHANGE_EVENT))
}

export function onLLMConfigChange(listener: () => void): () => void {
  window.addEventListener(CHANGE_EVENT, listener)
  return () => window.removeEventListener(CHANGE_EVENT, listener)
}

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

function encodeBase64Url(value: string): string {
  return btoa(value).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
}

/** The `?llmConfig=` value to append to a preview widget iframe's src, so it
 * can read the CURRENT config across the portal/widget origin boundary
 * (widget's `lib/llmConfig.ts` decodes this — see its matching design note).
 * `null` in demo mode: the widget's own default is already demo mode, no
 * param needed. */
export function previewQueryParam(config: LLMConfig = loadLLMConfig()): string | null {
  if (config.mode !== 'byok' || !config.apiKey) return null
  return encodeBase64Url(JSON.stringify(config))
}
