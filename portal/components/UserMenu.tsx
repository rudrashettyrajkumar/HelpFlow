'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { ChevronDown, LogOut, User } from 'lucide-react'
import { useAuth } from '@/lib/auth-context'

export function UserMenu() {
  const { user, logout } = useAuth()
  const [open, setOpen] = useState(false)
  const router = useRouter()

  if (!user) return null

  return (
    <div className="relative">
      <button
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-haspopup="menu"
        className="flex cursor-pointer items-center gap-2 rounded-xl border border-border px-3 py-2 text-sm font-medium transition-colors hover:border-brand/40"
      >
        <span className="flex size-6 items-center justify-center rounded-full bg-brand-gradient text-white">
          <User className="size-3.5" aria-hidden="true" />
        </span>
        <span className="max-w-[140px] truncate">{user.email}</span>
        <ChevronDown className="size-3.5 text-foreground-muted" aria-hidden="true" />
      </button>
      {open && (
        <>
          <div className="fixed inset-0 z-10" onClick={() => setOpen(false)} aria-hidden="true" />
          <div
            role="menu"
            className="glass-strong absolute right-0 top-full z-20 mt-2 w-48 overflow-hidden rounded-2xl p-1"
          >
            <button
              role="menuitem"
              onClick={() => {
                setOpen(false)
                logout()
                router.push('/')
              }}
              className="flex w-full cursor-pointer items-center gap-2 rounded-xl px-3 py-2.5 text-left text-sm font-medium text-destructive hover:bg-destructive/10"
            >
              <LogOut className="size-4" aria-hidden="true" />
              Log out
            </button>
          </div>
        </>
      )}
    </div>
  )
}
