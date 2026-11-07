import { defineConfig } from '@playwright/test'
import localAccountConfig from './playwright.account.config'

// Separate exact spec/output preserves the previously reviewed UI artifacts.
export default defineConfig({
  ...localAccountConfig,
  testMatch: 'auth-recovery.spec.ts',
  outputDir: 'test-results/auth-recovery-local',
})
