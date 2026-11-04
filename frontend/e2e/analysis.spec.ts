import { test, expect } from '@playwright/test'
import { existsSync } from 'node:fs'

test('analysis route requires an authenticated session', async ({ page }) => {
  await page.goto('/analysis')
  await expect(page.getByRole('heading',{name:'Welcome back'})).toBeVisible()
})

test('real hosted login and local KGW positive/control analysis, guards, upload and responsive UI', async ({ page }) => {
  test.skip(process.env.WATERMARKLAB_LIVE_TESTS !== '1','Requires explicit live opt-in and confirmed account')
  test.setTimeout(120000)
  if(existsSync('../backend/.env.integration')) process.loadEnvFile('../backend/.env.integration')
  const email=process.env.TEST_USER_A_EMAIL, password=process.env.TEST_USER_A_PASSWORD
  test.skip(!email || !password,'Integration account not configured')
  await page.goto('/access')
  await page.getByLabel('Email',{exact:true}).fill(email!)
  await page.getByLabel('Password',{exact:true}).fill(password!)
  await page.getByRole('button',{name:'Sign in',exact:true}).click()
  await expect(page.getByRole('heading',{name:'Your research overview.'})).toBeVisible()
  await page.getByRole('link',{name:'New analysis'}).click()
  await expect(page.getByRole('button',{name:'Analyze KGW'})).toBeEnabled({timeout:60000})
  for(const [sample,verdict,score] of [['kgw-pilot-1-wm','DETECTED','9.2863'],['kgw-pilot-1-control','NOT DETECTED','-1.0633']]) {
    await page.getByLabel('Load a known sample').selectOption(sample)
    await page.getByRole('button',{name:'Analyze KGW'}).click()
    await expect(page.getByRole('heading',{name:verdict,exact:true})).toBeVisible()
    await expect(page.getByText(score,{exact:true})).toBeVisible()
  }
  await page.getByLabel('KGW profile').selectOption('')
  await page.getByRole('button',{name:'Analyze KGW'}).click()
  await expect(page.getByRole('heading',{name:'INCONCLUSIVE',exact:true})).toBeVisible()
  await page.getByLabel(/Upload UTF-8/).setInputFiles({name:'short.md',mimeType:'text/markdown',buffer:Buffer.from('A short research sentence.')})
  await expect(page.getByLabel('Text to analyze')).toHaveValue('A short research sentence.')
  await page.getByLabel('KGW profile').selectOption('kgw-gpt2-cpu-v1')
  await page.getByRole('checkbox').check()
  await page.getByRole('button',{name:'Analyze KGW'}).click()
  await expect(page.getByRole('heading',{name:'INCONCLUSIVE',exact:true})).toBeVisible()
  await expect(page.getByText(/Too short for the local/)).toBeVisible()
  for(const width of [375,768,1440]) {
    await page.setViewportSize({width,height:1000})
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  }
  // Synthetic research text only; no credentials, account email or tokens in image.
  await page.getByLabel('Load a known sample').selectOption('kgw-pilot-1-wm')
  await page.getByRole('button',{name:'Analyze KGW'}).click()
  await expect(page.getByRole('heading',{name:'DETECTED',exact:true})).toBeVisible()
  await page.getByRole('heading',{name:'Examine the signal.'}).click()
  await page.evaluate(() => scrollTo(0, 0))
  await page.screenshot({path:'test-results/kgw-analysis.png',fullPage:true})
  await page.getByRole('button',{name:'Clear text'}).click()
  await expect(page.getByLabel('Text to analyze')).toHaveValue('')
  await expect(page.getByRole('heading',{name:'DETECTED',exact:true})).toHaveCount(0)
  await page.getByRole('link',{name:'Research overview'}).click()
  await page.getByRole('button',{name:'Sign out',exact:true}).click()
})
