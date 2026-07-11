import { createClient, type SupabaseClient } from '@supabase/supabase-js'
import { SUPABASE_ANON_KEY, SUPABASE_URL } from './config'

// The ONE Supabase client the console uses — anon key, masked RLS views only
// (spec E9 Req 1, ARCHITECTURE §5.5). No auth session of its own; every query
// below is tenant-scoped explicitly by `tenant_id` in application code (RLS
// on the base tables denies anon regardless, but the view read is still
// filtered here so a workspace only ever fetches its own rows).
//
// Lazily constructed: building this at module load crashes Next.js's static
// prerender pass for any page that imports it when `NEXT_PUBLIC_SUPABASE_URL`
// isn't set at build time (createClient throws synchronously on an empty
// URL) — a real deploy always has it via Vercel env config, but a local
// build without `.env.local` shouldn't hard-fail the whole `next build`.
let _client: SupabaseClient | null = null
function client(): SupabaseClient {
  if (!_client) {
    _client = createClient(SUPABASE_URL, SUPABASE_ANON_KEY, { auth: { persistSession: false } })
  }
  return _client
}

export type VConversation = {
  id: string
  tenant_id: string
  channel: string
  status: 'ai_handling' | 'needs_human' | 'human_assigned' | 'resolved' | 'abandoned'
  assigned_agent: string | null
  customer_email: string | null
  last_message_preview: string | null
  escalation_reason: string | null
  last_activity_at: string
  created_at: string
}

export type VFunnel = {
  tenant_id: string
  total: number
  ai_resolved: number
  escalated: number
  human_resolved: number
  deflection_rate: number | null
}

export type VGap = {
  tenant_id: string
  conversation_id: string
  created_at: string
  question: string | null
}

export type VEvent = {
  tenant_id: string
  conversation_id: string
  type: string
  detail: Record<string, unknown> | null
  created_at: string
}

export type VGapCluster = {
  tenant_id: string
  theme: string
  frequency: number
  example_questions: string[]
  computed_at: string
}

export async function fetchConversations(tenantId: string): Promise<VConversation[]> {
  const { data, error } = await client()
    .from('v_conversations')
    .select('*')
    .eq('tenant_id', tenantId)
    .order('last_activity_at', { ascending: false })
  if (error) throw error
  return data as VConversation[]
}

export async function fetchFunnel(tenantId: string): Promise<VFunnel | null> {
  const { data, error } = await client()
    .from('v_funnel')
    .select('*')
    .eq('tenant_id', tenantId)
    .maybeSingle()
  if (error) throw error
  return data as VFunnel | null
}

export async function fetchEvents(tenantId: string, sinceIso?: string): Promise<VEvent[]> {
  let query = client()
    .from('v_events')
    .select('*')
    .eq('tenant_id', tenantId)
    .order('created_at', { ascending: false })
    .limit(200)
  if (sinceIso) query = query.gt('created_at', sinceIso)
  const { data, error } = await query
  if (error) throw error
  return data as VEvent[]
}

export async function fetchGapClusters(tenantId: string): Promise<VGapCluster[]> {
  const { data, error } = await client()
    .from('v_gap_clusters')
    .select('*')
    .eq('tenant_id', tenantId)
    .order('frequency', { ascending: false })
  if (error) throw error
  return data as VGapCluster[]
}
