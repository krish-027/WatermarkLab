import type { Reporter, TestCase, TestResult, FullResult } from '@playwright/test/reporter'

export default class SafeReporter implements Reporter {
  onTestEnd(test: TestCase, result: TestResult) {
    console.log(JSON.stringify({ test: test.title, status: result.status }))
  }
  onError() { console.log('Browser runner error; raw details suppressed to protect credentials.') }
  onEnd(result: FullResult) { console.log(JSON.stringify({ suite: result.status })) }
}
