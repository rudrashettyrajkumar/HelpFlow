// One place for env — never `process.env.X` scattered through components
// (mirrors backend/utils/config.py's discipline). All `NEXT_PUBLIC_*` since
// this is a client-side app talking straight to the FastAPI backend.
export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'
export const WIDGET_URL = process.env.NEXT_PUBLIC_WIDGET_URL ?? 'http://localhost:5173'
export const DEMO_TENANT_WIDGET_KEY = process.env.NEXT_PUBLIC_DEMO_TENANT_WIDGET_KEY ?? ''

export const RAJ = {
  name: process.env.NEXT_PUBLIC_RAJ_NAME ?? 'Raj',
  linkedin: process.env.NEXT_PUBLIC_RAJ_LINKEDIN_URL ?? '',
  whatsapp: process.env.NEXT_PUBLIC_RAJ_WHATSAPP_URL ?? '',
  email: process.env.NEXT_PUBLIC_RAJ_EMAIL ?? '',
  github: process.env.NEXT_PUBLIC_RAJ_GITHUB_URL ?? '',
}
