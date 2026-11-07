import { defineConfig, devices } from '@playwright/test'

// Separate output/server and explicit test match: never collects hosted suites.
export default defineConfig({
  testDir: './e2e', testMatch: 'account-navigation.spec.ts', workers: 1,
  outputDir: 'test-results/account-navigation-local', reporter: 'list',
  use: { baseURL: 'http://127.0.0.1:5187', trace: 'off', screenshot: 'off', video: 'off', serviceWorkers: 'block' },
  projects: [{ name: 'edge-local', use: { ...devices['Desktop Edge'], channel: 'msedge' } }],
  webServer: {
    command: 'node node_modules/vite/bin/vite.js --host 127.0.0.1 --port 5187 --strictPort',
    url: 'http://127.0.0.1:5187', reuseExistingServer: false,
    env: { VITE_SUPABASE_URL: 'https://watermarklab-fixture.invalid',
      VITE_SUPABASE_PUBLISHABLE_KEY: 'sb_publishable_local_fixture_only',
      VITE_API_BASE_URL: 'http://127.0.0.1:8766', WATERMARKLAB_LIVE_TESTS: '0' },
  },
})
