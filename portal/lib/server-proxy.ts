import { NextRequest, NextResponse } from 'next/server'
import { API_URL } from './config'

/** Forwards an agent-action request to FastAPI's `/conversations/{id}/*`
 * (spec E9 Req 1: "Agent actions go through Next.js route handlers that
 * attach the token server-side"). The route handler files under
 * `app/api/conversations/[id]/*` are thin — this is the one place the
 * forwarding logic lives, so `grep .next` for anything server-only has one
 * source to audit. */
export async function proxyToBackend(
  request: NextRequest,
  path: string,
  { method = 'POST' }: { method?: string } = {},
): Promise<NextResponse> {
  const authorization = request.headers.get('authorization')
  const tenantId = request.headers.get('x-tenant-id')
  if (!authorization || !tenantId) {
    return NextResponse.json({ detail: 'Missing authorization or workspace.' }, { status: 401 })
  }

  const body = method === 'POST' ? await request.text() : undefined

  const res = await fetch(`${API_URL}${path}`, {
    method,
    headers: {
      Authorization: authorization,
      'X-Tenant-Id': tenantId,
      'Content-Type': 'application/json',
    },
    body: body || undefined,
  })

  const text = await res.text()
  return new NextResponse(text, {
    status: res.status,
    headers: { 'Content-Type': res.headers.get('content-type') ?? 'application/json' },
  })
}
