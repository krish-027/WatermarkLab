import { createContext, useContext, useEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import type { Session } from '@supabase/supabase-js'
import { Navigate } from 'react-router-dom'
import { supabase } from './client'
import { apiBaseUrl } from '../lib/api'
import type { Profile } from './accountIdentity'

type AuthState = { session: Session | null; loading: boolean; profile: Profile | null; profileLoading: boolean; profileError: boolean; signOut: () => Promise<void> }
const AuthContext = createContext<AuthState>({ session: null, loading: true, profile: null, profileLoading: false, profileError: false, signOut: async () => { throw new Error('Authentication unavailable.') } })
export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(null)
  const [loading, setLoading] = useState(true)
  const [profileState, setProfileState] = useState<{ owner: string | null; profile: Profile | null; loading: boolean; error: boolean }>({ owner: null, profile: null, loading: false, error: false })
  const revision = useRef(0)
  const currentSession = useRef<Session | null>(null)
  useEffect(() => {
    if (!supabase) { setLoading(false); return }
    let active = true
    const initialRevision = revision.current
    const { data: { subscription } } = supabase.auth.onAuthStateChange((_event, next) => {
      if (active) {
        // USER_UPDATED may reuse the SDK's session object. Publish a fresh snapshot.
        const snapshot = next ? { ...next, user: { ...next.user } } : null
        revision.current++; currentSession.current = snapshot; setSession(snapshot); setLoading(false)
      }
    })
    supabase.auth.getSession().then(({ data, error }) => {
      if (active && revision.current === initialRevision) {
        currentSession.current = error ? null : data.session
        setSession(currentSession.current); setLoading(false)
      }
    }).catch(() => { if (active && revision.current === initialRevision) setLoading(false) })
    return () => { active = false; subscription.unsubscribe() }
  }, [])
  const owner = session?.user.id
  const token = session?.access_token
  useEffect(() => {
    if (!owner || !token) { setProfileState({ owner: null, profile: null, loading: false, error: false }); return }
    const accountId = owner
    let active = true
    const controller = new AbortController()
    setProfileState({ owner, profile: null, loading: true, error: false })
    async function readProfile() {
      try {
        const response = await fetch(`${apiBaseUrl()}/api/v1/profile`, { headers: { Authorization: `Bearer ${token}` }, signal: controller.signal })
        if (!response.ok) throw new Error()
        const row: unknown = await response.json()
        if (row !== null && (typeof row !== 'object' || !('id' in row) || row.id !== accountId || !('display_name' in row) || typeof row.display_name !== 'string')) throw new Error()
        if (active) setProfileState({ owner: accountId, profile: row as Profile | null, loading: false, error: false })
      } catch { if (active) setProfileState({ owner: accountId, profile: null, loading: false, error: true }) }
    }
    void readProfile()
    return () => { active = false; controller.abort() }
  }, [owner, token])
  async function signOut() {
    if (!supabase) throw new Error('Authentication unavailable.')
    const previous = currentSession.current
    const { error } = await supabase.auth.signOut({ scope: 'local' })
    if (error) throw new Error('Sign out failed. Check your connection and try again.')
    if (currentSession.current?.access_token === previous?.access_token) {
      revision.current++; currentSession.current = null; setSession(null); setLoading(false)
    }
  }
  const ownProfile = profileState.owner === owner
  return <AuthContext.Provider value={{ session, loading, signOut,
    profile: ownProfile ? profileState.profile : null,
    profileLoading: !!owner && (!ownProfile || profileState.loading),
    profileError: ownProfile && profileState.error }}>{children}</AuthContext.Provider>
}
export const useAuth = () => useContext(AuthContext)
export function Protected({ children }: { children: ReactNode }) {
  const { session, loading } = useAuth()
  if (loading) return <div className="container page-shell" role="status">Restoring your session…</div>
  if (!session) return <Navigate to="/access" replace />
  return children
}
