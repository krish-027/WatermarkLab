import { Route, Routes } from 'react-router-dom'
import { Layout } from './components/Layout'
import { Home } from './pages/Home'
import { Documentation, Explore, NotFound } from './pages/Guide'
import { AuthProvider, Protected } from './auth/AuthProvider'
import { lazy, Suspense } from 'react'
const AuthPage = lazy(() => import('./pages/Auth').then(m => ({ default: m.AuthPage })))
const AuthCallback = lazy(() => import('./pages/Auth').then(m => ({ default: m.AuthCallback })))
const Dashboard = lazy(() => import('./pages/Auth').then(m => ({ default: m.Dashboard })))
const Profile = lazy(() => import('./pages/Profile'))
const Analysis = lazy(() => import('./pages/Analysis'))
const Transform = lazy(() => import('./pages/Transform'))
const Robustness = lazy(() => import('./pages/Robustness'))

export function App() {
  return <AuthProvider><Suspense fallback={<div className="container page-shell" role="status">Loading page…</div>}><Routes><Route element={<Layout />}><Route index element={<Home />} /><Route path="explore" element={<Explore />} /><Route path="access" element={<AuthPage />} /><Route path="auth/callback" element={<AuthCallback />} /><Route path="auth/reset-password" element={<AuthCallback reset />} /><Route path="dashboard" element={<Protected><Dashboard /></Protected>} /><Route path="settings" element={<Protected><Profile /></Protected>} /><Route path="analysis" element={<Protected><Analysis /></Protected>} /><Route path="robustness" element={<Protected><Robustness /></Protected>} /><Route path="transform" element={<Protected><Transform /></Protected>} /><Route path="documentation" element={<Documentation />} /><Route path="*" element={<NotFound />} /></Route></Routes></Suspense></AuthProvider>
}
