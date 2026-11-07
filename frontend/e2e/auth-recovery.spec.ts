import { test, expect } from '@playwright/test'
import type { Page } from '@playwright/test'

async function setup(page: Page, failure = false) {
  const calls: string[] = [], unexpected: string[] = []
  await page.route('**/*', async route => {
    const request = route.request(), url = new URL(request.url())
    if (url.origin === 'http://127.0.0.1:5187') return route.continue()
    calls.push(request.method() + ' ' + url.pathname)
    if (url.origin === 'https://watermarklab-fixture.invalid' && url.pathname === '/auth/v1/recover' && request.method() === 'POST') {
      expect(request.postDataJSON().email).toBe('qa@example.test')
      expect(url.searchParams.get('redirect_to')).toBe('http://127.0.0.1:5187/auth/reset-password')
      return route.fulfill({ status: failure ? 429 : 200, contentType: 'application/json',
        body: JSON.stringify(failure ? { code: 'over_request_rate_limit', message: 'Synthetic recovery rejected' } : {}) })
    }
    unexpected.push(request.method() + ' ' + url.pathname)
    return route.abort()
  })
  await page.goto('/access')
  await page.getByRole('button', { name: 'Forgot password?' }).click()
  return { calls, unexpected }
}

async function send(page: Page, action: string) {
  if (action === 'Enter') await page.getByLabel('Email', { exact: true }).press('Enter')
  else await page.getByRole('button', { name: 'Send recovery email' }).click()
}

for (const action of ['Enter', 'button']) {
  test(`recovery ${action} sends one email-only request with no login or signup`, async ({ page }) => {
    const network = await setup(page)
    await expect(page.getByLabel('Password', { exact: true })).toHaveCount(0)
    await page.getByLabel('Email', { exact: true }).fill('qa@example.test')
    await send(page, action)
    await expect(page.getByRole('status')).toContainText('If eligible, an email has been sent.')
    expect(network.calls).toEqual(['POST /auth/v1/recover'])
    expect(network.unexpected).toEqual([])
  })

  test(`invalid email via ${action} stays local`, async ({ page }) => {
    const network = await setup(page)
    await page.getByLabel('Email', { exact: true }).fill('invalid')
    await send(page, action)
    await expect(page.getByRole('status')).toHaveText('Enter a valid email address first.')
    expect(network.calls).toEqual([])
    expect(network.unexpected).toEqual([])
  })

  test(`recovery error via ${action} preserves messaging and re-enables submission`, async ({ page }) => {
    const network = await setup(page, true)
    await page.getByLabel('Email', { exact: true }).fill('qa@example.test')
    await send(page, action)
    await expect(page.getByRole('status')).toHaveText('Synthetic recovery rejected')
    await expect(page.getByRole('button', { name: 'Send recovery email' })).toBeEnabled()
    expect(network.calls).toEqual(['POST /auth/v1/recover'])
    expect(network.unexpected).toEqual([])
  })
}
