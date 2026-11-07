import { useEffect, useId, useRef, useState } from 'react'
import type { KeyboardEvent } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { ChevronDown, LayoutDashboard, LogOut, UserRound } from 'lucide-react'
import { useAuth } from '../auth/AuthProvider'
import { accountIdentity } from '../auth/accountIdentity'

export function AccountNavigation() {
  const { session, loading } = useAuth()
  if (loading) return <span className="account-loading" role="status">Restoring session…</span>
  if (!session) return <Link className="sign-in" to="/access">Sign In</Link>
  return <AccountMenu key={session.user.id} />
}

function AccountMenu() {
  const { session, profile, signOut } = useAuth()
  const identity = accountIdentity(session!.user, profile)
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const root = useRef<HTMLDivElement>(null)
  const trigger = useRef<HTMLButtonElement>(null)
  const menuId = useId()
  const location = useLocation()
  useEffect(() => { setOpen(false); setError('') }, [location])
  useEffect(() => {
    if (!open) return
    const outside = (event: PointerEvent) => { if (!root.current?.contains(event.target as Node)) setOpen(false) }
    document.addEventListener('pointerdown', outside)
    return () => document.removeEventListener('pointerdown', outside)
  }, [open])
  function keys(event: KeyboardEvent<HTMLDivElement>) {
    if (event.key === 'Escape' && open) { event.preventDefault(); event.stopPropagation(); setOpen(false); trigger.current?.focus() }
    if (event.key === 'ArrowDown' && event.target === trigger.current) {
      event.preventDefault(); setOpen(true)
      requestAnimationFrame(() => root.current?.querySelector<HTMLAnchorElement>('nav a')?.focus())
    }
  }
  async function logout() {
    setBusy(true); setError('')
    try { await signOut() }
    catch { setError('Sign out failed. Check your connection and try again.') }
    finally { setBusy(false) }
  }
  return <div className="account-menu" ref={root} onKeyDown={keys} onBlur={event => {
    if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setOpen(false)
  }}>
    <button className="account-trigger" ref={trigger} type="button" aria-label={`Account menu for ${identity.label}`} aria-expanded={open} aria-controls={menuId} onClick={() => setOpen(!open)}>
      <span className="account-avatar" aria-hidden="true">{identity.initials}</span><span className="account-name">{identity.label}</span><ChevronDown size={14} aria-hidden="true" />
    </button>
    {open && <nav id={menuId} className="account-dropdown" aria-label="Account navigation">
      <p className="account-menu-name">{identity.label}</p>
      <Link to="/dashboard"><LayoutDashboard size={16} aria-hidden="true" />Dashboard</Link>
      <Link to="/settings"><UserRound size={16} aria-hidden="true" />Profile &amp; Settings</Link>
      <button type="button" disabled={busy} onClick={() => void logout()}><LogOut size={16} aria-hidden="true" />{busy ? 'Signing out…' : 'Sign out'}</button>
      {error && <p role="alert">{error}</p>}
    </nav>}
  </div>
}
