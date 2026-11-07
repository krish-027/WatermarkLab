import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { vi, test, expect } from 'vitest'
import { App } from '../App'
import { ApiStatus } from '../components/ApiStatus'
import { getHealth } from '../lib/api'

const health = { status: 'ok', service: 'watermarklab-api', version: '0.2.0' }
function mockHealth() {
  return vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => health }))
}
function show(ui: React.ReactNode, path = '/') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })
  return render(<QueryClientProvider client={client}><MemoryRouter initialEntries={[path]}>{ui}</MemoryRouter></QueryClientProvider>)
}

test('landing explains limitations and labels illustrative evidence', async () => {
  mockHealth()
  show(<App />)
  expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Hidden Signals')
  expect(screen.getByText('Conceptual illustration · no analysis performed')).toBeInTheDocument()
  expect(screen.getByText(/negative result does not establish human authorship/)).toBeInTheDocument()
  expect(await screen.findByText('Connected to local backend')).toBeInTheDocument()
})

test('mobile navigation opens, closes with Escape and returns focus', async () => {
  mockHealth()
  show(<App />)
  const user = userEvent.setup()
  const toggle = screen.getByRole('button', { name: 'Open navigation' })
  expect(toggle).toHaveAttribute('aria-expanded', 'false')
  await user.click(toggle)
  expect(screen.getByRole('navigation', { name: 'Mobile navigation' })).toBeInTheDocument()
  await user.keyboard('{Escape}')
  expect(screen.queryByRole('navigation', { name: 'Mobile navigation' })).not.toBeInTheDocument()
  expect(toggle).toHaveFocus()
})

test('CTA navigates to a truthful public guide without submitting text', async () => {
  mockHealth()
  show(<App />)
  await userEvent.setup().click(screen.getByRole('link', { name: 'Explore Watermark Analysis' }))
  expect(screen.getByText('KGW and SynthID research analysis are available.')).toBeInTheDocument()
  expect(screen.queryByRole('textbox')).not.toBeInTheDocument()
})

test('sign-in displays either real auth form or setup-needed state', async () => {
  show(<App />, '/access')
  expect(await screen.findByRole('heading', { level: 1 })).toBeInTheDocument()
})

test('protected dashboard sends an unauthenticated visitor to sign in', async () => {
  show(<App />, '/dashboard')
  expect(await screen.findByRole('heading', { name: 'Welcome back' })).toBeInTheDocument()
})

test('registration validates email and password before contacting Supabase', async () => {
  show(<App />, '/access')
  const user = userEvent.setup()
  await user.click(await screen.findByRole('button', { name: 'Create an account' }))
  await user.type(screen.getByLabelText('Email'), 'invalid')
  await user.type(screen.getByLabelText('Password'), 'short')
  await user.click(screen.getByRole('button', { name: 'Register' }))
  expect(await screen.findByText('Use at least 8 characters.')).toBeInTheDocument()
})

test('recovery requires a valid email locally', async () => {
  show(<App />, '/access')
  const user=userEvent.setup()
  await user.click(await screen.findByRole('button',{name:'Forgot password?'}))
  await user.click(screen.getByRole('button',{name:'Send recovery email'}))
  expect(screen.getByRole('status')).toHaveTextContent('Enter a valid email address first.')
})

test('unknown routes show a working home recovery link', async () => {
  mockHealth()
  show(<App />, '/missing')
  expect(screen.getByText('404 / PAGE NOT FOUND')).toBeInTheDocument()
  await userEvent.setup().click(screen.getByRole('link', { name: 'Back to home' }))
  expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Hidden Signals')
})

test('health loading then genuine success', async () => {
  let resolve!: (value: unknown) => void
  vi.stubGlobal('fetch', vi.fn(() => new Promise(done => { resolve = done })))
  show(<ApiStatus />)
  expect(screen.getByRole('status')).toHaveTextContent('Checking connection')
  resolve({ ok: true, json: async () => health })
  expect(await screen.findByText('Connected to local backend')).toBeInTheDocument()
})

test('failed health check gives an actionable retry and recovers', async () => {
  vi.stubGlobal('fetch', vi.fn().mockRejectedValueOnce(new Error('offline')).mockResolvedValueOnce({ ok: true, json: async () => health }))
  show(<ApiStatus />)
  expect(await screen.findByText('API unavailable')).toBeInTheDocument()
  expect(screen.getByText(/Start the backend on port 8000/)).toBeInTheDocument()
  await userEvent.setup().click(screen.getByRole('button', { name: 'Check connection' }))
  expect(await screen.findByText('Connected to local backend')).toBeInTheDocument()
})

test.each([{ status: 'ok' }, { ...health, service: 'some-other-service' }])('rejects malformed or unrelated health payload %j', async body => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => body }))
  await expect(getHealth()).rejects.toThrow('Unexpected API health response')
})

test('rejects HTTP errors', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false }))
  await expect(getHealth()).rejects.toThrow('API health request failed')
})

test('rejects unsafe API configuration before making a request', async () => {
  vi.stubEnv('VITE_API_BASE_URL', 'https://user:secret@example.com')
  const fetch = vi.fn()
  vi.stubGlobal('fetch', fetch)
  await expect(getHealth()).rejects.toThrow('Invalid API URL configuration')
  expect(fetch).not.toHaveBeenCalled()
})
