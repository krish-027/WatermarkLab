import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  testDir: './e2e', fullyParallel: false, workers: 1,
  reporter: process.env.WATERMARKLAB_LIVE_TESTS === '1' ? './e2e/safe-reporter.ts' : 'list',
  use: { baseURL: 'http://localhost:5173', trace: process.env.WATERMARKLAB_LIVE_TESTS === '1' ? 'off' : 'retain-on-failure', screenshot: 'off', video: 'off' },
  projects: [{ name: 'edge', use: { ...devices['Desktop Edge'], channel: 'msedge' } }],
})
