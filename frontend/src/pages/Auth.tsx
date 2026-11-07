import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { supabase } from '../auth/client'
import { useAuth } from '../auth/AuthProvider'
import { accountIdentity } from '../auth/accountIdentity'

const schema = z.object({ email: z.email(), password: z.string().min(8, 'Use at least 8 characters.').max(128) })
type Credentials = z.infer<typeof schema>
export function AuthPage() {
  const [mode, setMode] = useState<'login' | 'register' | 'recover'>('login')
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)
  const { session, loading } = useAuth()
  const navigate = useNavigate()
  const form = useForm<Credentials>({ resolver: zodResolver(schema) })
  useEffect(() => {
    if (!loading && session && mode !== 'recover') navigate('/dashboard', { replace: true })
  }, [session, loading, mode, navigate])
  if (loading) return <div className="container page-shell" role="status">Restoring your session…</div>
  if (!supabase) return <div className="container page-shell"><h1>Setup required</h1><p>Configure the public Supabase values in frontend/.env and restart Vite. Public research pages remain available.</p></div>
  const client = supabase
  async function submit(values: Credentials) {
    if (mode === 'recover') return
    setBusy(true); setMessage('')
    try {
      const result = mode === 'login' ? await client.auth.signInWithPassword(values) : await client.auth.signUp({ ...values, options: { emailRedirectTo: `${window.location.origin}/auth/callback` } })
      if (result.error) setMessage(result.error.message)
      else if (result.data.session) navigate('/dashboard', { replace: true })
      else setMessage('Check your email to confirm your account, then sign in. An existing account may not receive another confirmation.')
    } catch { setMessage('Unable to reach authentication service. Please retry.') }
    finally { setBusy(false) }
  }
  async function emailAction(action: 'recover' | 'resend') {
    if (busy) return
    const email = form.getValues('email')
    if (!z.email().safeParse(email).success) { setMessage('Enter a valid email address first.'); return }
    setBusy(true)
    try {
      const { error } = action === 'recover' ? await client.auth.resetPasswordForEmail(email, { redirectTo: `${window.location.origin}/auth/reset-password` }) : await client.auth.resend({ type: 'signup', email, options: { emailRedirectTo: `${window.location.origin}/auth/callback` } })
      setMessage(error ? error.message : 'If eligible, an email has been sent. Check your inbox and spam folder.')
    } catch { setMessage('Unable to reach authentication service.') }
    finally { setBusy(false) }
  }
  return <div className="container page-shell auth-grid"><aside><p className="eyebrow">YOUR RESEARCH SPACE</p><h1>Keep your<br /><span>evidence connected.</span></h1><p className="page-intro">Use your WatermarkLab account to access private experiment metadata. Raw text is never saved by default.</p></aside><section className="auth-card"><h2>{mode === 'login' ? 'Welcome back' : mode === 'register' ? 'Create an account' : 'Reset your password'}</h2>{session && <p><Link to="/dashboard">Open your dashboard →</Link></p>}<form onSubmit={mode === 'recover' ? event => { event.preventDefault(); void emailAction('recover') } : form.handleSubmit(submit)} noValidate><label>Email<input type="email" autoComplete="email" {...form.register('email')} /></label><p className="field-error">{form.formState.errors.email?.message}</p>{mode !== 'recover' && <><label>Password<input type="password" autoComplete={mode === 'login' ? 'current-password' : 'new-password'} {...form.register('password')} /></label><p className="field-error">{form.formState.errors.password?.message}</p><button className="button button-primary" disabled={busy}>{busy ? 'Please wait…' : mode === 'login' ? 'Sign in' : 'Register'}</button></>}{mode === 'recover' && <button className="button button-primary" disabled={busy} type="submit">Send recovery email</button>}</form><p role="status">{message}</p><div className="auth-links"><button className="text-button" onClick={() => { setMode(mode === 'register' ? 'login' : 'register'); setMessage('') }}>{mode === 'register' ? 'Already registered? Sign in' : 'Create an account'}</button><button className="text-button" onClick={() => { setMode(mode === 'recover' ? 'login' : 'recover'); setMessage('') }}>{mode === 'recover' ? 'Back to sign in' : 'Forgot password?'}</button><button className="text-button" disabled={busy} onClick={() => void emailAction('resend')}>Resend confirmation</button></div></section></div>
}

export function AuthCallback({ reset = false }: { reset?: boolean }) {
  const { session, loading } = useAuth()
  const [password, setPassword] = useState('')
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)
  // The singleton SDK processes PKCE once through detectSessionInUrl.
  useEffect(() => { if (!loading) window.history.replaceState(null, '', window.location.pathname) }, [loading])
  async function update() {
    if (password.length < 8 || password.length > 128) { setMessage('Use 8–128 characters.'); return }
    setBusy(true)
    try {
      const result = await supabase!.auth.updateUser({ password })
      setMessage(result.error ? result.error.message : 'Password updated. You can return to your dashboard.')
      if (!result.error) setPassword('')
    } catch { setMessage('Password update failed. Try again.') }
    finally { setBusy(false) }
  }
  return <div className="container page-shell compact-page"><h1>{reset ? 'Choose a new password.' : 'Email confirmation'}</h1>{loading ? <p role="status">Checking your session…</p> : session ? <>{reset ? <div className="auth-card"><label>New password<input type="password" autoComplete="new-password" value={password} onChange={e => setPassword(e.target.value)} /></label><button className="button button-primary" disabled={busy} onClick={() => void update()}>Update password</button></div> : <p>You are signed in. Your confirmation link was processed by Supabase.</p>}<Link className="inline-link" to="/dashboard">Open dashboard →</Link></> : <p>This link could not restore a session. It may be expired, used, or opened in a different browser from the one that requested it. <Link to="/access">Sign in or request another email.</Link></p>}<p role="status">{message}</p></div>
}

export function Dashboard() {
  const { session, profile, signOut } = useAuth()
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const identity = accountIdentity(session!.user, profile)
  async function logout() {
    setBusy(true); setMessage('')
    try { await signOut() }
    catch { setMessage('Sign out failed. Check your connection and try again.') }
    finally { setBusy(false) }
  }
  return <div className="container page-shell"><p className="eyebrow">PRIVATE WORKSPACE</p><h1>Your research overview.</h1><p className="page-intro">Welcome, {identity.label}. Continue your analysis or compare a controlled transformation under the same detector profile.</p><div className="workspace-actions"><Link className="button button-primary" to="/analysis">New analysis</Link><Link className="button button-secondary" to="/robustness">Robustness Lab (development)</Link><Link className="button button-secondary" to="/transform">Gemini transformations</Link><Link className="button button-secondary" to="/settings">Profile &amp; Settings</Link><button className="button button-secondary" type="button" disabled={busy} onClick={() => void logout()}>{busy ? 'Signing out…' : 'Sign out'}</button></div>{message && <p role="alert">{message}</p>}</div>
}
