import { test, expect } from '@playwright/test'
import { existsSync } from 'node:fs'

test('protected route redirects and registration validates without a fake session', async ({ page }) => {
  await page.goto('/dashboard')
  await expect(page.getByRole('heading',{name:'Welcome back'})).toBeVisible()
  await page.getByRole('button',{name:'Create an account',exact:true}).click()
  await page.getByLabel('Email', {exact:true}).fill('invalid')
  await page.getByLabel('Password', {exact:true}).fill('short')
  await page.getByRole('button',{name:'Register',exact:true}).click()
  await expect(page.getByText('Use at least 8 characters.')).toBeVisible()
  await page.screenshot({path:'test-results/auth-preview.png'})
})

test('invalid recovery link does not offer password update without a session', async ({ page }) => {
  await page.goto('/auth/reset-password')
  await expect(page.getByText(/This link could not restore a session/)).toBeVisible()
  await expect(page.getByLabel('New password')).toHaveCount(0)
})

for (const account of ['A','B']) test(`live confirmed account ${account}: login, profile API, persistence and logout`, async ({ page }) => {
  test.skip(process.env.WATERMARKLAB_LIVE_TESTS !== '1','Hosted integration pending; explicit opt-in required')
  const env='../backend/.env.integration'
  if (existsSync(env)) process.loadEnvFile(env)
  const email=process.env[`TEST_USER_${account}_EMAIL`]
  const password=process.env[`TEST_USER_${account}_PASSWORD`]
  test.skip(!email || !password,'Confirmed integration account not configured locally')
  await page.goto('/access')
  await page.getByLabel('Email',{exact:true}).fill(email!)
  await page.getByLabel('Password',{exact:true}).fill(password!)
  const profileResponse=page.waitForResponse(response => response.url().endsWith('/api/v1/profile') && response.request().method()==='GET')
  await page.getByRole('button',{name:'Sign in',exact:true}).click()
  await expect(page.getByRole('heading',{name:'Your research overview.'})).toBeVisible()
  expect((await profileResponse).status()).toBe(200)
  await page.reload()
  await expect(page.getByRole('heading',{name:'Your research overview.'})).toBeVisible()
  await page.getByRole('button',{name:'Sign out',exact:true}).click()
  await page.goto('/dashboard')
  await expect(page.getByRole('heading',{name:'Welcome back'})).toBeVisible()
})
