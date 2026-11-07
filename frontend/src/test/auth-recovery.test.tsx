import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, expect, test, vi } from 'vitest'
import { AuthPage } from '../pages/Auth'

const auth = vi.hoisted(() => ({ resetPasswordForEmail: vi.fn(), signInWithPassword: vi.fn(), signUp: vi.fn(), resend: vi.fn() }))
vi.mock('../auth/client', () => ({ supabase: { auth } }))
vi.mock('../auth/AuthProvider', () => ({ useAuth: () => ({ session: null, loading: false }) }))

beforeEach(() => {
  vi.resetAllMocks()
  auth.resetPasswordForEmail.mockResolvedValue({ error: null })
})
async function recovery(email = 'qa@example.test') {
  render(<MemoryRouter><AuthPage /></MemoryRouter>)
  const user = userEvent.setup()
  await user.click(screen.getByRole('button', { name: 'Forgot password?' }))
  const input = screen.getByLabelText('Email')
  if (email) await user.type(input, email)
  return { user, input }
}
async function send(action: string, state: Awaited<ReturnType<typeof recovery>>) {
  if (action === 'enter') { state.input.focus(); await state.user.keyboard('{Enter}') }
  else await state.user.click(screen.getByRole('button', { name: 'Send recovery email' }))
}
function noCredentialsSubmit() {
  expect(auth.signInWithPassword).not.toHaveBeenCalled()
  expect(auth.signUp).not.toHaveBeenCalled()
  expect(auth.resend).not.toHaveBeenCalled()
}

test.each(['enter', 'button'])('recovery %s submits only the validated email action', async action => {
  const state = await recovery()
  expect(screen.queryByLabelText('Password')).toBeNull()
  await send(action, state)
  expect(auth.resetPasswordForEmail).toHaveBeenCalledExactlyOnceWith('qa@example.test', { redirectTo: `${window.location.origin}/auth/reset-password` })
  expect(screen.getByRole('status')).toHaveTextContent('If eligible, an email has been sent. Check your inbox and spam folder.')
  noCredentialsSubmit()
})

test.each([
  ['enter', ''], ['button', ''], ['enter', 'invalid'], ['button', 'invalid'],
])('invalid recovery email via %s (%s) makes no SDK call', async (action, email) => {
  const state = await recovery(email)
  await send(action, state)
  expect(screen.getByRole('status')).toHaveTextContent('Enter a valid email address first.')
  expect(auth.resetPasswordForEmail).not.toHaveBeenCalled()
  noCredentialsSubmit()
})

test.each(['enter', 'button'])('SDK recovery error via %s preserves message and releases loading', async action => {
  auth.resetPasswordForEmail.mockResolvedValue({ error: { message: 'Synthetic recovery rejected' } })
  const state = await recovery()
  await send(action, state)
  expect(screen.getByRole('status')).toHaveTextContent('Synthetic recovery rejected')
  expect(screen.getByRole('button', { name: 'Send recovery email' })).toBeEnabled()
  expect(auth.resetPasswordForEmail).toHaveBeenCalledTimes(1)
  noCredentialsSubmit()
})

test.each(['enter', 'button'])('recovery transport rejection via %s uses existing safe error message', async action => {
  auth.resetPasswordForEmail.mockRejectedValue(new Error('synthetic-transport-detail'))
  const state = await recovery()
  await send(action, state)
  expect(screen.getByRole('status')).toHaveTextContent('Unable to reach authentication service.')
  expect(screen.queryByText('synthetic-transport-detail')).toBeNull()
  expect(screen.getByRole('button', { name: 'Send recovery email' })).toBeEnabled()
  noCredentialsSubmit()
})

test('pending recovery disables submission and does not duplicate on repeated Enter', async () => {
  let finish!: (value: unknown) => void
  auth.resetPasswordForEmail.mockImplementation(() => new Promise(resolve => { finish = resolve }))
  const state = await recovery()
  await send('enter', state)
  expect(screen.getByRole('button', { name: 'Send recovery email' })).toBeDisabled()
  await send('enter', state)
  expect(auth.resetPasswordForEmail).toHaveBeenCalledTimes(1)
  await act(async () => { finish({ error: null }) })
  expect(screen.getByRole('button', { name: 'Send recovery email' })).toBeEnabled()
  noCredentialsSubmit()
})

test.each(['login', 'register'])('%s still requires the existing minimum password length', async mode => {
  render(<MemoryRouter><AuthPage /></MemoryRouter>)
  const user = userEvent.setup()
  if (mode === 'register') await user.click(screen.getByRole('button', { name: 'Create an account' }))
  await user.type(screen.getByLabelText('Email'), 'qa@example.test')
  await user.type(screen.getByLabelText('Password'), 'short')
  await user.click(screen.getByRole('button', { name: mode === 'login' ? 'Sign in' : 'Register' }))
  expect(await screen.findByText('Use at least 8 characters.')).toBeVisible()
  expect(auth.resetPasswordForEmail).not.toHaveBeenCalled()
  noCredentialsSubmit()
})

test('recovery bypasses a previous login password-validation error', async () => {
  render(<MemoryRouter><AuthPage /></MemoryRouter>)
  const user = userEvent.setup()
  await user.type(screen.getByLabelText('Email'), 'qa@example.test')
  await user.type(screen.getByLabelText('Password'), 'short')
  await user.click(screen.getByRole('button', { name: 'Sign in' }))
  expect(await screen.findByText('Use at least 8 characters.')).toBeVisible()
  await user.click(screen.getByRole('button', { name: 'Forgot password?' }))
  screen.getByLabelText('Email').focus(); await user.keyboard('{Enter}')
  expect(auth.resetPasswordForEmail).toHaveBeenCalledTimes(1)
  noCredentialsSubmit()
})
