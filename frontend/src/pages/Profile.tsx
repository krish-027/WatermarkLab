import { Link } from 'react-router-dom'
import { useAuth } from '../auth/AuthProvider'
import { accountIdentity } from '../auth/accountIdentity'

export default function ProfilePage() {
  const { session, profile, profileLoading, profileError } = useAuth()
  const identity = accountIdentity(session!.user, profile)
  return <div className="container page-shell compact-page">
    <p className="eyebrow">YOUR ACCOUNT</p><h1>Profile &amp; Settings</h1>
    <p className="page-intro">Your existing WatermarkLab account information.</p>
    <section className="auth-card profile-card" aria-label="Account information">
      <span className="account-avatar profile-avatar" aria-hidden="true">{identity.initials}</span>
      <dl><div><dt>Display name</dt><dd>{identity.name || 'Not provided'}</dd></div><div><dt>Email</dt><dd>{identity.email || 'Not provided'}</dd></div></dl>
      {profileLoading && <p role="status">Loading saved profile…</p>}
      {profileError && <p role="status">Your saved profile is unavailable. Available account information is shown.</p>}
    </section>
    <div className="workspace-actions"><Link className="button button-primary" to="/dashboard">Dashboard</Link><Link className="button button-secondary" to="/analysis">New analysis</Link></div>
  </div>
}
