import type { NextRequest } from 'next/server'
import { proxyToBackend } from '@/lib/server-proxy'

export async function POST(request: NextRequest, { params }: { params: { id: string } }) {
  return proxyToBackend(request, `/conversations/${params.id}/claim`)
}
