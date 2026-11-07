import { act, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, expect, test, vi } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { Session } from '@supabase/supabase-js'
import { App } from '../App'
import { accountIdentity } from '../auth/accountIdentity'

const sdk = vi.hoisted(() => ({
  auth: { getSession: vi.fn(), onAuthStateChange: vi.fn(), signOut: vi.fn(),
    signInWithPassword: vi.fn(), signUp: vi.fn(), resetPasswordForEmail: vi.fn(), resend: vi.fn() },
  changed: null as null | ((event: string, session: Session | null) => void), unsubscribe: vi.fn(),
}))
vi.mock('../auth/client', () => ({ supabase: { auth: sdk.auth } }))

function session(id = 'A', email: string | undefined = 'alice@example.test', metadata: object = { display_name: 'Alice Chen' }): Session {
  return { access_token: 'fixture-token-' + id, user: { id, email, user_metadata: metadata } } as Session
}
const health = { status: 'ok', service: 'watermarklab-api', version: '0.2.0' }
beforeEach(() => {
  vi.clearAllMocks()
  sdk.auth.getSession.mockResolvedValue({ data: { session: null }, error: null })
  sdk.auth.onAuthStateChange.mockImplementation(callback => {
    sdk.changed = callback
    return { data: { subscription: { unsubscribe: sdk.unsubscribe } } }
  })
  sdk.auth.signOut.mockResolvedValue({ error: null })
  sdk.auth.signInWithPassword.mockImplementation(async () => {
    const next = session(); sdk.changed?.('SIGNED_IN', next)
    return { data: { session: next }, error: null }
  })
  vi.stubGlobal('fetch', vi.fn(async (url: string) => ({ ok: true, json: async () => url.endsWith('/health') ? health : null })))
})
function show(path = '/') {
  return render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })}><MemoryRouter initialEntries={[path]}><App /></MemoryRouter></QueryClientProvider>)
}
async function emit(next: Session | null, event = next ? 'SIGNED_IN' : 'SIGNED_OUT') {
  await act(async () => { sdk.changed?.(event, next) })
}

test('logged out header offers Sign In and no account menu', async () => {
  show()
  expect(await screen.findByRole('link', { name: 'Sign In' })).toHaveAttribute('href', '/access')
  expect(screen.queryByRole('button', { name: /Account menu/ })).toBeNull()
})

test('initial restoration does not flash Sign In for an authenticated refresh', async () => {
  let resolve!: (value: unknown) => void
  sdk.auth.getSession.mockImplementation(() => new Promise(done => { resolve = done }))
  show()
  expect(screen.getByText('Restoring session…')).toBeVisible()
  expect(screen.queryByRole('link', { name: 'Sign In' })).toBeNull()
  await act(async () => { resolve({ data: { session: session() }, error: null }) })
  expect(await screen.findByRole('button', { name: 'Account menu for Alice Chen' })).toBeVisible()
})

test('login reaches dashboard without asking for display name or writing profile', async () => {
  show('/access')
  await screen.findByRole('heading', { name: 'Welcome back' })
  const user = userEvent.setup()
  await user.type(screen.getByLabelText('Email'), 'alice@example.test')
  await user.type(screen.getByLabelText('Password'), 'synthetic-password')
  await user.click(screen.getByRole('button', { name: 'Sign in' }))
  expect(await screen.findByRole('heading', { name: 'Your research overview.' })).toBeVisible()
  expect(screen.queryByLabelText('Display name')).toBeNull()
  expect(sdk.auth.signInWithPassword).toHaveBeenCalledTimes(1)
  expect(vi.mocked(fetch).mock.calls.every(([, options]) => !options || !('method' in options) || options.method === 'GET')).toBe(true)
  expect(sdk.auth.signUp).not.toHaveBeenCalled()
})

test('existing session visiting sign in redirects to dashboard', async () => {
  sdk.auth.getSession.mockResolvedValue({ data: { session: session() }, error: null })
  show('/access')
  expect(await screen.findByRole('heading', { name: 'Your research overview.' })).toBeVisible()
  expect(screen.queryByLabelText('Password')).toBeNull()
})

test('an older getSession result cannot overwrite a newer sign-in event', async () => {
  let resolve!: (value: unknown) => void
  sdk.auth.getSession.mockImplementation(() => new Promise(done => { resolve = done }))
  show()
  await emit(session())
  await act(async () => { resolve({ data: { session: null }, error: null }) })
  expect(screen.getByRole('button', { name: 'Account menu for Alice Chen' })).toBeVisible()
})

test('saved profile name takes precedence over existing auth metadata', async () => {
  vi.mocked(fetch).mockResolvedValue({ ok: true, json: async () => ({ id: 'A', display_name: 'Dr Alice Chen' }) } as Response)
  sdk.auth.getSession.mockResolvedValue({ data: { session: session() }, error: null })
  show('/settings')
  expect(await screen.findByRole('button', { name: 'Account menu for Dr Alice Chen' })).toBeVisible()
  expect(screen.getByRole('heading', { name: 'Profile & Settings' })).toBeVisible()
  expect(screen.getByText('alice@example.test')).toBeVisible()
  expect(screen.queryByRole('textbox')).toBeNull()
  expect(screen.queryByRole('checkbox')).toBeNull()
})

test('profile errors show available account information without a write', async () => {
  vi.mocked(fetch).mockRejectedValue(new Error('synthetic-offline'))
  sdk.auth.getSession.mockResolvedValue({ data: { session: session() }, error: null })
  show('/settings')
  expect(await screen.findByText(/Your saved profile is unavailable/)).toBeVisible()
  expect(screen.getByRole('button', { name: 'Account menu for Alice Chen' })).toBeVisible()
})

test('switching accounts discards and ignores an older profile response', async () => {
  let old!: (value: unknown) => void
  vi.stubGlobal('fetch', vi.fn((_url, options) => options.headers.Authorization === 'Bearer fixture-token-A'
    ? new Promise(done => { old = done })
    : Promise.resolve({ ok: true, json: async () => ({ id: 'B', display_name: 'Bob Rao' }) })))
  sdk.auth.getSession.mockResolvedValue({ data: { session: session() }, error: null })
  show('/settings')
  await screen.findByText('alice@example.test')
  await emit(session('B', 'bob@example.test', { full_name: 'Bob' }))
  expect(await screen.findByRole('button', { name: 'Account menu for Bob Rao' })).toBeVisible()
  await act(async () => { old({ ok: true, json: async () => ({ id: 'A', display_name: 'Old Alice' }) }) })
  expect(screen.queryByText('alice@example.test')).toBeNull()
  expect(screen.queryByText('Old Alice')).toBeNull()
  expect(screen.getByText('bob@example.test')).toBeVisible()
})

test('wrong-owner profile response is rejected', async () => {
  vi.mocked(fetch).mockResolvedValue({ ok: true, json: async () => ({ id: 'B', display_name: 'Other Person' }) } as Response)
  sdk.auth.getSession.mockResolvedValue({ data: { session: session() }, error: null })
  show('/settings')
  expect(await screen.findByText(/Your saved profile is unavailable/)).toBeVisible()
  expect(screen.queryByText('Other Person')).toBeNull()
})

test('dropdown opens by keyboard, navigates, closes on Escape and restores focus', async () => {
  sdk.auth.getSession.mockResolvedValue({ data: { session: session() }, error: null })
  show()
  const user = userEvent.setup()
  const button = await screen.findByRole('button', { name: 'Account menu for Alice Chen' })
  button.focus(); await user.keyboard('{ArrowDown}')
  expect(within(screen.getByRole('navigation', { name: 'Account navigation' })).getByRole('link', { name: 'Dashboard' })).toHaveFocus()
  await user.keyboard('{Escape}')
  expect(button).toHaveFocus()
  expect(screen.queryByRole('navigation', { name: 'Account navigation' })).toBeNull()
  await user.click(button)
  await user.click(screen.getByRole('link', { name: 'Profile & Settings' }))
  expect(await screen.findByRole('heading', { name: 'Profile & Settings' })).toBeVisible()
  expect(button).toHaveAttribute('aria-expanded', 'false')
})

test('dropdown closes on outside click and when tabbing away', async () => {
  sdk.auth.getSession.mockResolvedValue({ data: { session: session() }, error: null })
  show()
  const user = userEvent.setup(); const button = await screen.findByRole('button', { name: /Account menu/ })
  await user.click(button); await user.click(screen.getByRole('heading', { level: 1 }))
  expect(button).toHaveAttribute('aria-expanded', 'false')
  await user.click(button); await user.tab(); await user.tab(); await user.tab(); await user.tab()
  expect(button).toHaveAttribute('aria-expanded', 'false')
})

test('sign out immediately updates header and protected page', async () => {
  sdk.auth.getSession.mockResolvedValue({ data: { session: session() }, error: null })
  show('/dashboard')
  const user = userEvent.setup()
  await user.click(await screen.findByRole('button', { name: /Account menu/ }))
  await user.click(within(screen.getByRole('navigation', { name: 'Account navigation' })).getByRole('button', { name: 'Sign out' }))
  expect(sdk.auth.signOut).toHaveBeenCalledWith({ scope: 'local' })
  expect(await screen.findByRole('heading', { name: 'Welcome back' })).toBeVisible()
  expect(screen.getByRole('link', { name: 'Sign In' })).toBeVisible()
})

test('logout failure remains visible and does not pretend the session ended', async () => {
  sdk.auth.signOut.mockResolvedValue({ error: new Error('synthetic-failure') })
  sdk.auth.getSession.mockResolvedValue({ data: { session: session() }, error: null })
  show('/dashboard'); const user = userEvent.setup()
  await user.click(await screen.findByRole('button', { name: /Account menu/ }))
  await user.click(within(screen.getByRole('navigation', { name: 'Account navigation' })).getByRole('button', { name: 'Sign out' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Sign out failed')
  expect(screen.getByRole('heading', { name: 'Your research overview.' })).toBeVisible()
})

test('session expiration clears profile and protects the settings route', async () => {
  sdk.auth.getSession.mockResolvedValue({ data: { session: session() }, error: null })
  show('/settings'); await screen.findByText('alice@example.test')
  await emit(null)
  expect(await screen.findByRole('heading', { name: 'Welcome back' })).toBeVisible()
  expect(screen.queryByText('alice@example.test')).toBeNull()
})

test('existing dashboard sign-out action still uses the shared auth session', async () => {
  sdk.auth.getSession.mockResolvedValue({ data: { session: session() }, error: null })
  show('/dashboard')
  await userEvent.click(await screen.findByRole('button', { name: 'Sign out' }))
  expect(await screen.findByRole('heading', { name: 'Welcome back' })).toBeVisible()
  expect(sdk.auth.signOut).toHaveBeenCalledTimes(1)
})

test('account switch closes the previous account dropdown', async () => {
  sdk.auth.getSession.mockResolvedValue({ data: { session: session() }, error: null })
  show(); const user = userEvent.setup()
  await user.click(await screen.findByRole('button', { name: /Account menu/ }))
  await emit(session('B', 'bob@example.test', { name: 'Bob Rao' }))
  expect(screen.getByRole('button', { name: 'Account menu for Bob Rao' })).toHaveAttribute('aria-expanded', 'false')
  expect(screen.queryByRole('navigation', { name: 'Account navigation' })).toBeNull()
})

test('USER_UPDATED refreshes metadata even when the SDK reuses a session object', async () => {
  const next = session()
  sdk.auth.getSession.mockResolvedValue({ data: { session: next }, error: null })
  show('/settings')
  await screen.findByText('alice@example.test')
  next.user.user_metadata.display_name = 'Alice Researcher'
  await emit(next, 'USER_UPDATED')
  expect(screen.getByRole('button', { name: 'Account menu for Alice Researcher' })).toBeVisible()
})

test.each(['/dashboard', '/settings', '/analysis', '/robustness', '/transform'])('protects logged-out route %s', async path => {
  show(path)
  expect(await screen.findByRole('heading', { name: 'Welcome back' })).toBeVisible()
})

test('missing metadata and email use a nonempty accessible fallback', async () => {
  const next = session('A', undefined, {})
  delete next.user.email
  sdk.auth.getSession.mockResolvedValue({ data: { session: next }, error: null })
  show('/settings')
  expect(await screen.findByRole('button', { name: 'Account menu for Researcher' })).toBeVisible()
  expect(screen.getAllByText('Not provided')).toHaveLength(2)
  expect(screen.getAllByText('WL')).toHaveLength(2)
})

test.each([
  [{ display_name: ' Alice   Chen ' }, 'Alice Chen', 'AC'],
  [{ display_name: 123, full_name: 'Bob Rao' }, 'Bob Rao', 'BR'],
  [{}, 'alice', 'AL'],
])('safe name and initials fallback %#', (metadata, label, initials) => {
  expect(accountIdentity(session('A', 'alice@example.test', metadata).user)).toMatchObject({ label, initials })
})

test('auth subscription is removed on unmount', async () => {
  const view = show(); await screen.findByRole('link', { name: 'Sign In' })
  view.unmount(); await waitFor(() => expect(sdk.unsubscribe).toHaveBeenCalledTimes(1))
})
