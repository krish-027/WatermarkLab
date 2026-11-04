import { test, expect } from '@playwright/test'
import { existsSync, writeFileSync } from 'node:fs'

test('transformation route requires an authenticated session',async({page})=>{
  await page.goto('/transform')
  await expect(page.getByRole('heading',{name:'Welcome back'})).toBeVisible()
})

test('real Gemini transformation with consent, native usage, privacy and responsive layout',async({page})=>{
  test.skip(process.env.WATERMARKLAB_LIVE_TESTS!=='1'||process.env.WATERMARKLAB_GEMINI_LIVE_TESTS!=='1','Requires explicit hosted-auth AND paid Gemini opt-ins')
  test.setTimeout(120000)
  if(existsSync('../backend/.env.integration'))process.loadEnvFile('../backend/.env.integration')
  const email=process.env.TEST_USER_A_EMAIL,password=process.env.TEST_USER_A_PASSWORD
  test.skip(!email||!password,'Confirmed account A required')
  await page.goto('/access')
  await page.getByLabel('Email',{exact:true}).fill(email!)
  await page.getByLabel('Password',{exact:true}).fill(password!)
  await page.getByRole('button',{name:'Sign in',exact:true}).click()
  await expect(page.getByRole('heading',{name:'Your research overview.'})).toBeVisible()
  await page.getByRole('link',{name:'Gemini transformations',exact:true}).click()
  const run=page.getByRole('button',{name:'Send to Gemini'})
  await expect(run).toBeEnabled()
  await page.getByLabel('Source text').fill('A researcher watered two seedlings daily and measured their growth for one week.')
  await run.click()
  await expect(page.getByRole('alert')).toContainText('Confirm')
  await page.getByText('Inspect prompt and settings before sending').click()
  await expect(page.getByText('Prompt version: gemini-transform-v1')).toBeVisible()
  await page.getByRole('checkbox').check()
  // Exactly one deliberate generation. No retries and no credential-bearing trace.
  const pending=page.waitForResponse(r=>r.url().endsWith('/api/v1/transform')&&r.request().method()==='POST')
  await run.click()
  const response=await pending
  const status=response.status()
  if(status!==200){
    let code='UNAVAILABLE'
    try{const body=await response.json();if(typeof body.detail?.code==='string'&&/^[A-Z_]+$/.test(body.detail.code))code=body.detail.code}catch{/* No provider details */}
    writeFileSync('test-results/gemini-live-usage.json',JSON.stringify({attempts:1,status:'failed',http_status:status,safe_error_code:code,usage:'Unknown'},null,2))
  }
  expect(status).toBe(200)
  const data=await response.json()
  // Only allowlisted metadata retained, never submitted/generated text or tokens.
  writeFileSync('test-results/gemini-live-usage.json',JSON.stringify({attempts:1,status:'passed',model:data.model,model_version:data.model_version,source_characters:data.source_characters,output_characters:data.output_characters,execution_ms:data.execution_ms,usage:data.usage},null,2))
  await expect(page.getByRole('heading',{name:'Transformation returned'})).toBeVisible()
  expect((await page.getByLabel('Generated text').inputValue()).trim().length).toBeGreaterThan(0)
  await expect(page.getByText(/Watermark provenance: UNKNOWN/)).toBeVisible()
  await expect(page.getByText(/Total: \d+/)).toBeVisible()
  await expect(page.getByRole('checkbox')).not.toBeChecked()
  expect(response.headers()['cache-control']).toBe('no-store')
  for(const width of [375,768,1440]){
    await page.setViewportSize({width,height:1000})
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true)
  }
  await page.setViewportSize({width:1440,height:1000})
  // Public synthetic research example only, no account identity or credentials.
  await page.getByRole('heading',{name:'Explore a different phrasing.'}).click()
  await page.screenshot({path:'test-results/gemini-transform.png',fullPage:true})
  await page.getByRole('button',{name:'Clear source and result'}).click()
  await expect(page.getByLabel('Source text')).toHaveValue('')
  await expect(page.getByLabel('Generated text')).toHaveCount(0)
  await page.getByRole('link',{name:'Research overview'}).click()
  await page.getByRole('button',{name:'Sign out',exact:true}).click()
})
