import { defineConfig } from '@playwright/test'
import { resolve } from 'node:path'
const python =
  process.env.ARYN_TEST_PYTHON ??
  resolve(
    process.platform === 'win32' ? '../../.venv/Scripts/python.exe' : '../../.venv/bin/python',
  )
export default defineConfig({
  testDir: './e2e',
  testMatch: '**/workflows.spec.ts',
  outputDir: 'test-results/workflows',
  workers: 1,
  timeout: 60_000,
  reporter: [['list'], ['html', { outputFolder: 'playwright-report/workflows', open: 'never' }]],
  use: {
    baseURL: 'http://127.0.0.1:8876',
    browserName: 'chromium',
    trace: 'retain-on-failure',
    actionTimeout: 15_000,
  },
  webServer: {
    command: `"${python}" -m tests.workflow_browser_server`,
    cwd: '../..',
    url: 'http://127.0.0.1:8876',
    timeout: 60_000,
    reuseExistingServer: false,
  },
})
