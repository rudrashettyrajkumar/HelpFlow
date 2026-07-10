'use client'

import { useEffect, useState } from 'react'
import { listWorkspaces } from './api'
import type { Workspace } from './types'

const STORAGE_KEY = 'hf_active_workspace'

/** Shared "which workspace am I looking at" state for Inbox/Sources/Analytics
 * — the console pages all need exactly one active tenant_id. Persists the
 * choice so switching pages doesn't reset it. */
export function useActiveWorkspace() {
  const [workspaces, setWorkspaces] = useState<Workspace[] | null>(null)
  const [activeId, setActiveIdState] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    listWorkspaces()
      .then((ws) => {
        setWorkspaces(ws)
        const stored = localStorage.getItem(STORAGE_KEY)
        const initial = ws.find((w) => w.id === stored)?.id ?? ws[0]?.id ?? null
        setActiveIdState(initial)
      })
      .catch(() => setError("Couldn't load your workspaces. Refresh to try again."))
  }, [])

  const setActiveId = (id: string) => {
    setActiveIdState(id)
    localStorage.setItem(STORAGE_KEY, id)
  }

  const active = workspaces?.find((w) => w.id === activeId) ?? null

  return { workspaces, active, activeId, setActiveId, error }
}
