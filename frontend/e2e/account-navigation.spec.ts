import { test, expect } from '@playwright/test'
import type { Page } from '@playwright/test'

const origin = 'https://watermarklab-fixture.invalid'
const storageKey = 'sb-watermarklab-fixture-auth-token'
function fixtureSession(name = 'Alice Chen', suffix = 1, expired = false) {
  const now = Math.floor(Date.now() / 1000)
  const id = `00000000-0000-4000-8000-00000000000${suffix}`
  const payload = Buffer.from(JSON.stringify({ sub: id, exp: expired ? now - 3600 : now + 3600, aud: 'authenticated', role: 'authenticated' })).toString('base64url')
  return { access_token: `eyJhbGciOiJIUzI1NiJ9.${payload}.synthetic-signature`, refresh_token: 'synthetic-refresh-only', token_type: 'bearer', expires_in: 3600,
    expires_at: expired ? now - 3600 : now + 3600,
    user: { id, aud: 'authenticated', email: suffix === 1 ? 'alice@example.test' : 'bob@example.test',
      app_metadata: { provider: 'email' }, user_metadata: { display_name: name }, created_at: '2026-11-07T00:00:00Z' } }
}

async function setup(page: Page, restored = false, expired = false) {
  const a = fixtureSession('Alice Chen', 1, expired)
  const calls: string[] = [], unexpected: string[] = []
  await page.addInitScript(({ key, value }) => { if (value) localStorage.setItem(key, JSON.stringify(value)) },
    { key: storageKey, value: restored ? a : null })
  await page.route('**/*', async route => {
    const request = route.request(), url = new URL(request.url())
    if (url.origin === 'http://127.0.0.1:5187') return route.continue()
    calls.push(request.method() + ' ' + url.pathname)
    const json = (body: unknown, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })
    if (url.origin === origin && url.pathname === '/auth/v1/token') {
      if (url.searchParams.get('grant_type') === 'refresh_token') return json({ code: 'refresh_token_not_found', message: 'Expired synthetic session' }, 400)
      return json(fixtureSession())
    }
    if (url.origin === origin && url.pathname === '/auth/v1/logout') return route.fulfill({ status: 204 })
    if (url.origin === origin && url.pathname === '/auth/v1/user') return json(a.user)
    if (url.origin === 'http://127.0.0.1:8766') {
      if (url.pathname === '/health') return json({ status: 'ok', service: 'watermarklab-api', version: '0.2.0' })
      if (url.pathname === '/api/v1/profile' && request.method() === 'GET') {
        const b = fixtureSession('Bob Rao', 2)
        const token = request.headers().authorization?.split(' ')[1]
        const sub = token ? JSON.parse(Buffer.from(token.split('.')[1], 'base64url').toString()).sub : null
        const user = sub === b.user.id ? b.user : a.user
        return json({ id: user.id, display_name: user.user_metadata.display_name, retain_text: false })
      }
      if (url.pathname === '/api/v1/compare' && request.method() === 'POST') return json({ status: 'not_run',
        baseline: { method: 'KGW', profile_id: null, verdict: 'INCONCLUSIVE', provenance: 'UNKNOWN', provenance_source: 'synthetic fixture', compatibility_basis: 'unknown', character_count: 12, token_count: null,
          scored_token_count: null, green_token_count: null, repeated_pair_count: null, raw_score: null, z_score: null, p_value: null, threshold: null, decision_rule: null, execution_ms: 1, warnings: [], native: null },
        message: 'Compatible profile required.' })
    }
    unexpected.push(request.method() + ' ' + url.pathname)
    return route.abort()
  })
  return { calls, unexpected }
}

test('logged out header, protected routes and login redirect without a repeated name form', async ({ page }) => {
  const network = await setup(page)
  await page.goto('/settings')
  await expect(page.getByRole('heading', { name: 'Welcome back' })).toBeVisible()
  await expect(page.getByRole('link', { name: 'Sign In', exact: true })).toBeVisible()
  await expect(page.getByLabel('Display name')).toHaveCount(0)
  await page.getByLabel('Email', { exact: true }).fill('alice@example.test')
  await page.getByLabel('Password', { exact: true }).fill('synthetic-password')
  await page.getByRole('button', { name: 'Sign in', exact: true }).click()
  await expect(page).toHaveURL(/\/dashboard$/)
  await expect(page.getByRole('heading', { name: 'Your research overview.' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Account menu for Alice Chen' })).toBeVisible()
  await expect(page.getByLabel('Display name')).toHaveCount(0)
  expect(network.calls.filter(x => x === 'POST /auth/v1/token')).toHaveLength(1)
  expect(network.calls.some(x => /^(POST|PUT|PATCH|DELETE) \/api/.test(x))).toBe(false)
  expect(network.unexpected).toEqual([])
})

test('authenticated refresh, keyboard dropdown, read-only profile and logout', async ({ page }, info) => {
  const network = await setup(page, true)
  await page.goto('/dashboard')
  await expect(page.getByRole('heading', { name: 'Your research overview.' })).toBeVisible()
  await page.reload()
  const trigger = page.getByRole('button', { name: 'Account menu for Alice Chen' })
  await expect(trigger).toBeVisible()
  await expect(page.getByRole('link', { name: 'Sign In', exact: true })).toHaveCount(0)
  await trigger.focus(); await page.keyboard.press('ArrowDown')
  const menu = page.getByRole('navigation', { name: 'Account navigation' })
  await expect(menu.getByRole('link', { name: 'Dashboard', exact: true })).toBeFocused()
  await page.keyboard.press('Escape'); await expect(trigger).toBeFocused()
  await trigger.click(); await menu.getByRole('link', { name: 'Profile & Settings' }).click()
  await expect(page.getByRole('heading', { name: 'Profile & Settings' })).toBeVisible()
  await expect(page.getByText('alice@example.test', { exact: true })).toBeVisible()
  await expect(page.getByRole('textbox')).toHaveCount(0)
  await page.setViewportSize({ width: 1440, height: 950 })
  await trigger.click()
  await page.screenshot({ path: info.outputPath('account-desktop.png'), fullPage: true })
  await menu.getByRole('button', { name: 'Sign out' }).click()
  await expect(page.getByRole('heading', { name: 'Welcome back' })).toBeVisible()
  await expect(page.getByRole('link', { name: 'Sign In', exact: true })).toBeVisible()
  expect(network.calls.filter(x => x === 'POST /auth/v1/logout')).toHaveLength(1)
  expect(network.unexpected).toEqual([])
})

test('mobile account menu, navigation and dashboard/compare smoke', async ({ page }, info) => {
  const network = await setup(page, true)
  await page.setViewportSize({ width: 375, height: 850 })
  await page.goto('/dashboard')
  const trigger = page.getByRole('button', { name: 'Account menu for Alice Chen' })
  for (const width of [320, 375, 768]) {
    await page.setViewportSize({ width, height: 850 })
    await expect(trigger).toBeVisible()
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  }
  await page.setViewportSize({ width: 375, height: 850 })
  await trigger.click()
  const menu = page.getByRole('navigation', { name: 'Account navigation' })
  await expect(menu.getByRole('link', { name: 'Profile & Settings' })).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await page.screenshot({ path: info.outputPath('account-mobile.png'), fullPage: true })
  await page.keyboard.press('Escape'); await expect(trigger).toBeFocused()
  await page.getByRole('button', { name: 'Open navigation' }).click()
  await expect(page.getByRole('navigation', { name: 'Mobile navigation' })).toBeVisible()
  await page.keyboard.press('Escape')
  await page.getByRole('link', { name: 'Robustness Lab (development)' }).click()
  await page.getByLabel('Original text', { exact: true }).fill('Synthetic browser acceptance text.')
  await page.getByRole('button', { name: 'Run paired comparison' }).click()
  await expect(page.getByRole('alert')).toContainText('INCONCLUSIVE')
  expect(network.calls.filter(x => x === 'POST /api/v1/compare')).toHaveLength(1)
  expect(network.unexpected).toEqual([])
})

test('SDK account-change event updates the header and profile without stale account data', async ({ page }) => {
  const network = await setup(page, true)
  await page.goto('/settings')
  await expect(page.getByText('alice@example.test', { exact: true })).toBeVisible()
  const b = fixtureSession('Bob Rao', 2)
  await page.evaluate(({ key, next }) => {
    localStorage.setItem(key, JSON.stringify(next))
    const channel = new BroadcastChannel(key)
    channel.postMessage({ event: 'SIGNED_IN', session: next }); channel.close()
  }, { key: storageKey, next: b })
  await expect(page.getByRole('button', { name: 'Account menu for Bob Rao' })).toBeVisible()
  await expect(page.getByText('bob@example.test', { exact: true })).toBeVisible()
  await expect(page.getByText('alice@example.test', { exact: true })).toHaveCount(0)
  expect(network.unexpected).toEqual([])
})

test('expired session with failed mock refresh returns to Sign In', async ({ page }) => {
  const network = await setup(page, true, true)
  await page.goto('/dashboard')
  await expect(page.getByRole('heading', { name: 'Welcome back' })).toBeVisible()
  await expect(page.getByRole('button', { name: /Account menu/ })).toHaveCount(0)
  expect(network.unexpected).toEqual([])
})
