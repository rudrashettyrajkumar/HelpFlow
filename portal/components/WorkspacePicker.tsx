import { Store } from 'lucide-react'
import type { Workspace } from '@/lib/types'

type Props = {
  workspaces: Workspace[]
  activeId: string | null
  onChange: (id: string) => void
}

export function WorkspacePicker({ workspaces, activeId, onChange }: Props) {
  if (workspaces.length <= 1) return null
  return (
    <label className="flex items-center gap-2 text-sm font-medium">
      <Store className="size-4 text-foreground-muted" aria-hidden="true" />
      <select
        value={activeId ?? ''}
        onChange={(e) => onChange(e.target.value)}
        className="min-h-[40px] rounded-xl border border-border bg-surface px-3 text-sm focus-visible:outline-none"
      >
        {workspaces.map((w) => (
          <option key={w.id} value={w.id}>
            {w.name}
          </option>
        ))}
      </select>
    </label>
  )
}
