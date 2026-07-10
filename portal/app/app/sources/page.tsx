'use client'

import { AlertTriangle, Loader2 } from 'lucide-react'
import { Glass } from '@/components/Glass'
import { SourceManager } from '@/components/SourceManager'
import { WorkspacePicker } from '@/components/WorkspacePicker'
import { useActiveWorkspace } from '@/lib/useActiveWorkspace'

export default function SourcesPage() {
  const { workspaces, active, activeId, setActiveId, error } = useActiveWorkspace()

  if (error) {
    return (
      <Glass className="flex items-center gap-2 rounded-2xl px-4 py-3 text-sm text-destructive">
        <AlertTriangle className="size-4 shrink-0" aria-hidden="true" /> {error}
      </Glass>
    )
  }

  if (!workspaces) {
    return (
      <div className="flex items-center justify-center gap-2 py-24 text-sm text-foreground-muted">
        <Loader2 className="size-4 animate-spin" aria-hidden="true" /> Loading…
      </div>
    )
  }

  if (workspaces.length === 0) {
    return (
      <Glass className="rounded-3xl px-6 py-16 text-center text-sm text-foreground-muted">
        No workspaces yet — create one first.
      </Glass>
    )
  }

  return (
    <div className="mx-auto max-w-3xl">
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-2xl font-extrabold tracking-tight">Sources</h1>
        <WorkspacePicker workspaces={workspaces} activeId={activeId} onChange={setActiveId} />
      </div>
      {active && <SourceManager tenantId={active.id} />}
    </div>
  )
}
