import { useCallback, useEffect, useState } from 'react'
import type { AuthStatus } from '../types'

const apiRoot = () => (import.meta.env.VITE_API_URL || 'https://app-production-cc16.up.railway.app').replace(/\/$/, '')

export function useAuth() {
  const [status, setStatus] = useState<AuthStatus>()
  const [loading, setLoading] = useState(true)

  const refresh = useCallback(async () => {
    try {
      const response = await fetch(`${apiRoot()}/v1/auth/status`, { credentials: 'include' })
      if (!response.ok) throw new Error('Could not load authentication status')
      setStatus(await response.json() as AuthStatus)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { void refresh() }, [refresh])

  const login = useCallback(() => { window.location.assign(`${apiRoot()}/v1/auth/github/login`) }, [])
  const logout = useCallback(async () => {
    await fetch(`${apiRoot()}/v1/auth/logout`, { method: 'POST', credentials: 'include' })
    await refresh()
  }, [refresh])

  return { status, loading, login, logout, refresh }
}
