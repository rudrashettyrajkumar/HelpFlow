import { API_URL } from './config'
import { getToken, handleUnauthorized } from './auth-token'
import { byokHeaders } from './llmConfig'
import { ApiError } from './types'
import type {
  AuthResponse,
  CreateWorkspaceResponse,
  CrawlProgressEvent,
  DemoBudget,
  GatePayload,
  MeResponse,
  ModelsCatalog,
  ValidateResult,
  Workspace,
} from './types'

function authHeaders(): HeadersInit {
  const token = getToken()
  return token ? { Authorization: `Bearer ${token}` } : {}
}

async function throwIfError(res: Response): Promise<void> {
  if (res.ok) return
  if (res.status === 401) handleUnauthorized()
  let detail = `Request failed (${res.status})`
  let gate: GatePayload | null = null
  try {
    const body = await res.json()
    if (res.status === 403 && body?.code === 'trial_limit') gate = body as GatePayload
    detail = body?.detail ?? body?.message ?? detail
  } catch {
    // non-JSON error body — keep the generic message
  }
  throw new ApiError(detail, res.status, gate)
}

async function parse<T>(res: Response): Promise<T> {
  await throwIfError(res)
  return res.json() as Promise<T>
}

// --- auth (backend/api/auth.py) ---

export function register(email: string, password: string): Promise<AuthResponse> {
  return fetch(`${API_URL}/api/auth/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  }).then((r) => parse<AuthResponse>(r))
}

export function login(email: string, password: string): Promise<AuthResponse> {
  return fetch(`${API_URL}/api/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  }).then((r) => parse<AuthResponse>(r))
}

export function fetchMe(): Promise<MeResponse> {
  return fetch(`${API_URL}/api/auth/me`, { headers: authHeaders() }).then((r) =>
    parse<MeResponse>(r),
  )
}

// --- workspaces (backend/api/workspaces.py) ---

export function listWorkspaces(): Promise<Workspace[]> {
  return fetch(`${API_URL}/api/workspaces`, { headers: authHeaders() }).then((r) =>
    parse<Workspace[]>(r),
  )
}

export function createWorkspace(
  name: string,
  websiteUrl: string,
): Promise<CreateWorkspaceResponse> {
  return fetch(`${API_URL}/api/workspaces`, {
    method: 'POST',
    headers: { ...authHeaders(), 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, website_url: websiteUrl }),
  }).then((r) => parse<CreateWorkspaceResponse>(r))
}

export function deleteWorkspace(tenantId: string): Promise<void> {
  return fetch(`${API_URL}/api/workspaces/${tenantId}`, {
    method: 'DELETE',
    headers: authHeaders(),
  }).then((r) => parse(r))
}

// --- BYOK catalog + demo budget (backend/api/models.py) ---

export function fetchModelCatalog(): Promise<ModelsCatalog> {
  return fetch(`${API_URL}/api/models`).then((r) => parse<ModelsCatalog>(r))
}

export function fetchDemoBudget(): Promise<DemoBudget> {
  return fetch(`${API_URL}/api/demo-budget`).then((r) => parse<DemoBudget>(r))
}

export function validateProviderKey(body: {
  provider: string
  model: string
  key: string
  kind: 'chat' | 'embed'
}): Promise<ValidateResult> {
  return fetch(`${API_URL}/api/models/validate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  }).then((r) => parse<ValidateResult>(r))
}

// --- premium contact (backend/api/premium.py) ---

export function premiumContact(body: {
  name: string
  email: string
  company?: string
  message: string
  source: 'gate' | 'landing'
}): Promise<{ id: string; status: string }> {
  return fetch(`${API_URL}/api/premium-contact`, {
    method: 'POST',
    headers: { ...authHeaders(), 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  }).then((r) => parse(r))
}

// --- crawl (backend/api/admin_sources.py) ---

/** Parses a `text/event-stream` body into `{event, data}` frames — same
 * parser shape as the widget's (`api/client.ts`), ported once more here
 * since Next.js/Vite bundles don't share code across these two apps. */
async function* parseSSE(
  body: ReadableStream<Uint8Array>,
): AsyncGenerator<{ event: string; data: unknown }> {
  const reader = body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) return
      buffer += decoder.decode(value, { stream: true })
      const frames = buffer.split('\n\n')
      buffer = frames.pop() ?? ''
      for (const frame of frames) {
        if (!frame || frame.startsWith(':')) continue
        let eventName = 'message'
        let data: unknown = null
        for (const line of frame.split('\n')) {
          if (line.startsWith('event: ')) eventName = line.slice(7)
          else if (line.startsWith('data: ')) data = JSON.parse(line.slice(6))
        }
        if (data !== null) yield { event: eventName, data }
      }
    }
  } finally {
    reader.releaseLock()
  }
}

/** `POST /admin/sources` (spec Req 3 step 2). DESIGN NOTE: the wizard's own
 * step order puts the crawl (step 2) BEFORE Model Studio (step 3), so this
 * always runs in demo-mode embeddings — no BYOK headers to thread yet. If the
 * owner later picks a different embed provider, the existing embed-mismatch
 * 409 dialog (spec Req 5) is the designed path to switch, via re-crawl. */
export async function* crawlSite(
  tenantId: string,
  url: string,
  maxPages?: number,
): AsyncGenerator<CrawlProgressEvent> {
  const res = await fetch(`${API_URL}/admin/sources`, {
    method: 'POST',
    headers: {
      ...authHeaders(),
      'X-Tenant-Id': tenantId,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ url, max_pages: maxPages }),
  })
  await throwIfError(res)
  if (!res.body) return
  for await (const frame of parseSSE(res.body)) {
    yield frame.data as CrawlProgressEvent
  }
}

/** BYOK headers for anything the portal itself calls with a model selection
 * (the validate probe uses its own explicit body, not these — this is for
 * future authenticated calls that need the owner's chosen chat/embed cfg). */
export { byokHeaders }
