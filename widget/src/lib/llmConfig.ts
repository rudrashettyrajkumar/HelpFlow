// BYOK model configuration — read-only here (E8's Model Studio is the writer).
// Demo mode (no config) sends no BYOK headers at all; the backend then serves
// its own env-configured models under the daily demo budget (ARCHITECTURE
// §4.3/§4.4).
//
// DESIGN CHOICE (flagged, spec E8 Req 4 "config persists in localStorage
// under the key shared with the widget"): that sharing can't be literal
// `localStorage` — the portal (Vercel) and this widget (Cloudflare Pages) are
// different origins, and the wizard's live preview is exactly the widget
// running in an iframe on the PORTAL's page. The portal instead passes its
// current config as a `?llmConfig=` base64url JSON query param when building
// the preview iframe's src; `loadLLMConfig()` prefers that over its own
// localStorage when present. External third-party embeds never carry this
// param, so they're unaffected — same "BYOK only in the owner's own browser"
// truth (§4.4). A `storage` event listener still lets the TierChip re-render
// live for same-origin cases (e.g. this widget opened directly, standalone).

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

function decodeBase64Url(value: string): string {
  const padded = value.replace(/-/g, '+').replace(/_/g, '/')
  return atob(padded)
}

let queryConfigChecked = false
let queryConfigCache: LLMConfig | null = null

/** The portal preview's `?llmConfig=` handoff, decoded once and cached for
 * the lifetime of this iframe document. */
function queryParamConfig(): LLMConfig | null {
  if (queryConfigChecked) return queryConfigCache
  queryConfigChecked = true
  try {
    const raw = new URLSearchParams(window.location.search).get('llmConfig')
    if (!raw) return null
    const parsed = JSON.parse(decodeBase64Url(raw)) as Partial<LLMConfig>
    if (parsed.mode !== 'byok' || !parsed.provider || !parsed.apiKey) return null
    queryConfigCache = { ...DEMO_CONFIG, ...parsed, mode: 'byok' }
  } catch {
    queryConfigCache = null
  }
  return queryConfigCache
}

export function loadLLMConfig(): LLMConfig {
  const fromPortalPreview = queryParamConfig()
  if (fromPortalPreview) return fromPortalPreview

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
