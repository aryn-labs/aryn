import { defineConfig } from '@playwright/test'
import { resolve } from 'node:path'
const python =
  process.env.ARYN_TEST_PYTHON ??
  resolve(
    process.platform === 'win32' ? '../../.venv/Scripts/python.exe' : '../../.venv/bin/python',
  )
export default defineConfig({
  testDir: './e2e',
  testMatch: '**/intelligence.spec.ts',
  workers: 1,
  timeout: 60000,
  outputDir: 'test-results/intelligence',
  reporter: [
    ['list'],
    ['html', { outputFolder: 'playwright-report/intelligence', open: 'never' }],
    ['junit', { outputFile: '../../.local/intelligence-evidence/browser.xml' }],
  ],
  use: {
    baseURL: 'http://127.0.0.1:8879',
    browserName: 'chromium',
    viewport: { width: 1440, height: 1000 },
    trace: 'retain-on-failure',
    actionTimeout: 15000,
  },
  webServer: {
    command: '"' + python + '" -m tests.intelligence_browser_server',
    cwd: '../..',
    url: 'http://127.0.0.1:8879',
    reuseExistingServer: false,
    timeout: 90000,
  },
})
