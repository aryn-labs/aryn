import { defineConfig } from '@playwright/test'
import { resolve } from 'node:path'
const python =
  process.env.ARYN_TEST_PYTHON ??
  resolve(
    process.platform === 'win32' ? '../../.venv/Scripts/python.exe' : '../../.venv/bin/python',
  )
export default defineConfig({
  testDir: './e2e',
  testMatch: '**/agents.spec.ts',
  outputDir: 'test-results/agents',
  workers: 1,
  timeout: 60_000,
  reporter: [['list'], ['html', { outputFolder: 'playwright-report/agents', open: 'never' }]],
  use: { baseURL: 'http://127.0.0.1:8874', browserName: 'chromium', trace: 'retain-on-failure' },
  webServer: {
    command: `"${python}" -m tests.agent_canvas_browser_server`,
    cwd: '../..',
    url: 'http://127.0.0.1:8874',
    reuseExistingServer: process.env.ARYN_FACTORY_REUSE_SERVER === '1',
    timeout: 60_000,
  },
})
