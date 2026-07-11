'use client'

import { createContext, useCallback, useContext, useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import * as api from './api'
import { clearToken, getToken, setToken, setUnauthorizedHandler } from './auth-token'
import type { AuthUser } from './types'

type AuthState = {
  user: AuthUser | null
  trialsUsed: number
  /** True until the initial token check resolves — gate the app on this so a
   * logged-in refresh doesn't flash the landing/login page. */
  initializing: boolean
  login: (email: string, password: string) => Promise<void>
  register: (email: string, password: string) => Promise<void>
  logout: () => void
  refresh: () => Promise<void>
}

const Ctx = createContext<AuthState | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null)
  const [trialsUsed, setTrialsUsed] = useState(0)
  const [initializing, setInitializing] = useState(true)

  const logout = useCallback(() => {
    clearToken()
    setUser(null)
  }, [])

  useEffect(() => {
    setUnauthorizedHandler(() => setUser(null))
  }, [])

  const refresh = useCallback(async () => {
    const me = await api.fetchMe()
    setUser(me.user)
    setTrialsUsed(me.trials_used)
  }, [])

  useEffect(() => {
    if (!getToken()) {
      setInitializing(false)
      return
    }
    refresh()
      .catch(() => clearToken())
      .finally(() => setInitializing(false))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const login = useCallback(async (email: string, password: string) => {
    const res = await api.login(email, password)
    setToken(res.token)
    setUser(res.user)
    setTrialsUsed(res.user.trials_used)
  }, [])

  const register = useCallback(async (email: string, password: string) => {
    const res = await api.register(email, password)
    setToken(res.token)
    setUser(res.user)
    setTrialsUsed(res.user.trials_used)
  }, [])

  return (
    <Ctx.Provider value={{ user, trialsUsed, initializing, login, register, logout, refresh }}>
      {children}
    </Ctx.Provider>
  )
}

export function useAuth(): AuthState {
  const ctx = useContext(Ctx)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}
