// Shapes bound to the REAL backend contracts (read from backend/api/auth.py,
// workspaces.py, models.py, premium.py, admin_sources.py — never guessed).

export type AuthUser = {
  id: string
  email: string
  trials_used: number
  created_at: string | null
}

export type AuthResponse = { token: string; user: AuthUser }
export type MeResponse = { user: AuthUser; trials_used: number; workspaces: WorkspaceSummary[] }

export type WorkspaceSummary = {
  id: string
  name: string
  website_url: string | null
  plan: string
  created_at: string | null
}

export type Workspace = WorkspaceSummary & {
  status: 'ready' | 'crawling' | 'empty'
  sources_ready: number
  sources_total: number
}

export type CreateWorkspaceResponse = {
  tenant: { id: string; name: string; website_url: string; plan: string }
  widget_key: string
}

export type GatePayload = {
  code: 'trial_limit'
  message: string
  contact: { linkedin: string | null; whatsapp: string | null; email: string | null }
  form: boolean
}

export class ApiError extends Error {
  status: number
  gate: GatePayload | null
  constructor(message: string, status: number, gate: GatePayload | null = null) {
    super(message)
    this.status = status
    this.gate = gate
  }
}

// --- BYOK catalog (backend/llm/catalog.py) ---

export type ModelInfo = {
  id: string
  name: string
  accuracy: number
  speed: 'blazing' | 'fast' | 'balanced' | 'deliberate'
  cost: string
  context: string
  free: boolean
  recommended: boolean
  notes: string
}

export type ProviderInfo = {
  id: string
  name: string
  tagline: string
  kind: 'free' | 'freemium' | 'paid'
  key_url: string
  key_steps: string[]
  models: ModelInfo[]
  embedding_models: ModelInfo[]
  allows_custom_model: boolean
}

export type ModelsCatalog = { providers: ProviderInfo[]; embed_providers: string[] }

export type ValidateResult = { ok: boolean; latency_ms?: number; error_code?: string }

export type DemoBudget = {
  chat: { remaining: number; cap: number }
  embed: { remaining: number; cap: number }
  resets_at: string
}

// --- Crawl SSE (backend/ingestion/ingest_service.py stage vocabulary) ---

export type CrawlProgressEvent =
  | { stage: 'discovering' }
  | { stage: 'fetching'; done: number; total: number }
  | { stage: 'embedding'; pct: number }
  | { stage: 'ready'; pages: number; chunks: number }
  | { stage: 'error'; detail: string }
  | { stage: 'info'; note: string }
