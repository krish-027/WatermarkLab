import {test,expect} from '@playwright/test'
import {existsSync,writeFileSync} from 'node:fs'

test('real authenticated robustness pairs and manual review without paid requests',async({page})=>{
 test.skip(process.env.WATERMARKLAB_LIVE_TESTS!=='1','Explicit live authentication opt-in required')
 test.setTimeout(120000)
 if(existsSync('../backend/.env.integration'))process.loadEnvFile('../backend/.env.integration')
 const email=process.env.TEST_USER_A_EMAIL,password=process.env.TEST_USER_A_PASSWORD
 test.skip(!email||!password,'Configured account required')
 writeFileSync('test-results/robustness-stage.txt','login');await page.goto('/access');await page.getByLabel('Email',{exact:true}).fill(email!);await page.getByLabel('Password',{exact:true}).fill(password!)
 await page.getByRole('button',{name:'Sign in',exact:true}).click()
 await expect(page.getByRole('heading',{name:'Your research overview.'})).toBeVisible()
 writeFileSync('test-results/robustness-stage.txt','open robustness');await page.goto('/robustness')
 for(const [method,sample] of [['KGW','kgw-pilot-1-wm'],['SYNTHID','synthid-pilot-1-wm']]){
  writeFileSync('test-results/robustness-stage.txt',method+' select method');await page.getByLabel('Detector',{exact:true}).selectOption(method)
  writeFileSync('test-results/robustness-stage.txt',method+' load samples');await page.getByRole('button',{name:'Load controlled samples'}).click()
  await expect(page.getByRole('option',{name:sample,exact:true})).toBeAttached()
  await page.getByLabel('Controlled sample',{exact:true}).selectOption(sample)
  const pending=page.waitForResponse(r=>r.url().endsWith('/api/v1/compare')&&r.request().method()==='POST')
  writeFileSync('test-results/robustness-stage.txt',method+' compare');await page.getByRole('button',{name:'Run paired comparison'}).click()
  const response=await pending;expect(response.status()).toBe(200)
  const data=await response.json()
  expect(data.original.detection.verdict).toBe('DETECTED')
  expect(data.child.parent_sample_id).toBe(data.original.id)
  expect(data.child.detection.provenance).toBe('UNKNOWN')
  expect(data.child.detection[method==='KGW'?'z_score':'p_value']).not.toBeNull()
  await expect(page.getByRole('heading',{name:'Observed change'})).toBeVisible()
  writeFileSync('test-results/robustness-stage.txt',method+' manual review');await page.getByLabel('Meaning preserved',{exact:true}).selectOption('uncertain')
  await page.getByLabel('Omissions present',{exact:true}).selectOption('no')
  await page.getByLabel('Factual changes present',{exact:true}).selectOption('uncertain')
  for(const width of [375,768,1440]){
   await page.setViewportSize({width,height:1000})
   expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true)
  }
  await page.getByRole('button',{name:'Clear experiment'}).click()
  await expect(page.getByLabel('Original text',{exact:true})).toHaveValue('')
 }
 await page.getByRole('link',{name:'Research overview',exact:true}).click()
 await page.getByRole('button',{name:'Sign out',exact:true}).click()
})
