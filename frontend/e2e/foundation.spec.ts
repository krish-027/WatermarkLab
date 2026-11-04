import { test, expect } from '@playwright/test'

test('desktop landing connects to actual API and public routes work', async ({ page }) => {
  const errors: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  await page.goto('/')
  await expect(page.getByRole('heading', { level: 1 })).toContainText('Hidden Signals')
  await expect(page.getByText('Connected to local backend')).toBeVisible()
  await page.screenshot({ path: 'test-results/desktop-preview.png' })
  await page.getByRole('link', { name: 'Explore Watermark Analysis', exact: true }).click()
  await expect(page.getByText('KGW and SynthID research analysis are available.')).toBeVisible()
  await page.getByRole('link', { name: 'Sign In', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Welcome back' })).toBeVisible()
  await page.getByRole('link', { name: 'Documentation', exact: true }).first().click()
  await expect(page.getByRole('heading', { name: 'Run the local foundation' })).toBeVisible()
  expect(errors).toEqual([])
})

test('mobile and tablet navigation fit and the research anchor resolves', async ({ page }) => {
  for (const width of [375, 768]) {
    await page.setViewportSize({ width, height: 900 })
    await page.goto('/')
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
    await page.getByRole('button', { name: 'Open navigation' }).click()
    await page.keyboard.press('Escape')
    await expect(page.getByRole('button', { name: 'Open navigation' })).toBeFocused()
    await page.getByRole('button', { name: 'Open navigation' }).click()
    await page.getByRole('navigation', { name: 'Mobile navigation' }).getByRole('link', { name: 'Research Methods', exact: true }).click()
    await expect(page.getByRole('navigation', { name: 'Mobile navigation' })).toHaveCount(0)
    await expect(page.locator('#research-methods')).toBeInViewport()
    await page.screenshot({ path: `test-results/home-${width}.png`, fullPage: true })
  }
})

test('offline health state reports failure and recovers after retry', async ({ page }) => {
  await page.route('**/health', route => route.abort())
  await page.goto('/')
  await expect(page.getByText('API unavailable')).toBeVisible()
  await page.unroute('**/health')
  await page.getByRole('button', { name: 'Check connection' }).click()
  await expect(page.getByText('Connected to local backend')).toBeVisible()
})

test('Swagger and API health are available on their real endpoints', async ({ request }) => {
  const health = await request.get('http://localhost:8000/health')
  expect(health.ok()).toBe(true)
  expect(await health.json()).toEqual({ status: 'ok', service: 'watermarklab-api', version: '0.2.0' })
  expect((await request.get('http://localhost:8000/docs')).status()).toBe(200)
})
