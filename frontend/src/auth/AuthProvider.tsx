import { createContext, useContext, useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import type { Session } from '@supabase/supabase-js'
import { Navigate } from 'react-router-dom'
import { supabase } from './client'

const AuthContext = createContext<{ session: Session | null; loading: boolean }>({ session: null, loading: true })
export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(null)
  const [loading, setLoading] = useState(true)
  useEffect(() => {
    if (!supabase) { setLoading(false); return }
    let active = true
    const { data: { subscription } } = supabase.auth.onAuthStateChange((_event, next) => {
      if (active) { setSession(next); setLoading(false) }
    })
    supabase.auth.getSession().then(({ data, error }) => {
      if (active) { setSession(error ? null : data.session); setLoading(false) }
    }).catch(() => { if (active) setLoading(false) })
    return () => { active = false; subscription.unsubscribe() }
  }, [])
  return <AuthContext.Provider value={{ session, loading }}>{children}</AuthContext.Provider>
}
export const useAuth = () => useContext(AuthContext)
export function Protected({ children }: { children: ReactNode }) {
  const { session, loading } = useAuth()
  if (loading) return <div className="container page-shell" role="status">Restoring your session…</div>
  if (!session) return <Navigate to="/access" replace />
  return children
}
