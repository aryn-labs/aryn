import { defineConfig } from '@playwright/test'
import { resolve } from 'node:path'
const python =
  process.env.ARYN_TEST_PYTHON ??
  resolve(
    process.platform === 'win32' ? '../../.venv/Scripts/python.exe' : '../../.venv/bin/python',
  )
export default defineConfig({
  testDir: './e2e',
  testMatch: '**/projects.spec.ts',
  outputDir: 'test-results/projects',
  workers: 1,
  timeout: 45_000,
  reporter: [['list'], ['html', { outputFolder: 'playwright-report/projects', open: 'never' }]],
  use: { baseURL: 'http://127.0.0.1:8873', browserName: 'chromium', trace: 'retain-on-failure' },
  webServer: [
    {
      command: `"${python}" -m tests.projects_browser_server`,
      cwd: '../..',
      url: 'http://127.0.0.1:8873',
      reuseExistingServer: false,
      timeout: 60_000,
    },
    ...(['admin', 'viewer'] as const).map((role, index) => ({
      command: `"${python}" -m tests.projects_browser_server --empty-role ${role} --port ${8875 + index}`,
      cwd: '../..',
      url: `http://127.0.0.1:${8875 + index}`,
      reuseExistingServer: false,
      timeout: 60_000,
    })),
  ],
})
