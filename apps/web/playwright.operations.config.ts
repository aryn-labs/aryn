import { defineConfig } from '@playwright/test'
import { resolve } from 'node:path'
const python =
  process.env.ARYN_TEST_PYTHON ??
  resolve(
    process.platform === 'win32' ? '../../.venv/Scripts/python.exe' : '../../.venv/bin/python',
  )
export default defineConfig({
  testDir: './e2e',
  testMatch: '**/operations.spec.ts',
  workers: 1,
  timeout: 60_000,
  outputDir: 'test-results/operations',
  reporter: [['list'], ['html', { outputFolder: 'playwright-report/operations', open: 'never' }]],
  use: {
    baseURL: 'http://127.0.0.1:8878',
    browserName: 'chromium',
    trace: 'retain-on-failure',
    actionTimeout: 15_000,
  },
  webServer: {
    command: '"' + python + '" -m tests.operations_browser_server',
    cwd: '../..',
    url: 'http://127.0.0.1:8878',
    reuseExistingServer: false,
    timeout: 60_000,
  },
})
