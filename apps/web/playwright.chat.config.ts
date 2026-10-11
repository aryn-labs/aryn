import { defineConfig } from '@playwright/test'
import { resolve } from 'node:path'
const python =
  process.env.ARYN_TEST_PYTHON ??
  resolve(
    process.platform === 'win32' ? '../../.venv/Scripts/python.exe' : '../../.venv/bin/python',
  )
export default defineConfig({
  testDir: './e2e',
  testMatch: ['**/chat.spec.ts', '**/conversation-crud.spec.ts'],
  outputDir: 'test-results/chat',
  workers: 1,
  timeout: 45_000,
  reporter: [['list'], ['html', { outputFolder: 'playwright-report/chat', open: 'never' }]],
  use: { baseURL: 'http://127.0.0.1:8871', browserName: 'chromium', trace: 'retain-on-failure' },
  webServer: {
    command: `"${python}" -m tests.chat_browser_server`,
    cwd: '../..',
    url: 'http://127.0.0.1:8871',
    reuseExistingServer: false,
    timeout: 60_000,
  },
})
