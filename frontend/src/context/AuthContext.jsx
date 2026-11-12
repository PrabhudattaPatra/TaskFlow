import { createContext, useCallback, useContext, useEffect, useState } from 'react'
import { api, refreshSession, setAccessToken, setAuthLostHandler } from '../api/client'

const AuthContext = createContext(null)
export const useAuth = () => useContext(AuthContext)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setAuthLostHandler(() => setUser(null))
    // On page load, try to restore the session from the refresh cookie.
    refreshSession().then((d) => setUser(d.user)).catch(() => setUser(null)).finally(() => setLoading(false))
  }, [])

  const authenticate = useCallback(async (path, body) => {
    const d = await api(path, { method: 'POST', body })
    setAccessToken(d.access_token)
    setUser(d.user)
  }, [])

  const login = (email, password) => authenticate('/auth/login', { email, password })
  const signup = (name, email, password) => authenticate('/auth/signup', { name, email, password })
  const logout = async () => {
    try { await api('/auth/logout', { method: 'POST' }) } catch { /* ignore */ }
    setAccessToken(null)
    setUser(null)
  }

  return <AuthContext.Provider value={{ user, loading, login, signup, logout }}>{children}</AuthContext.Provider>
}
