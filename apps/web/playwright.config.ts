import { defineConfig } from '@playwright/test'
export default defineConfig({
  testDir: './e2e',
  outputDir: 'test-results/shell-home',
  fullyParallel: true,
  workers: 2,
  timeout: 30_000,
  expect: { timeout: 7_000 },
  reporter: [['list'], ['html', { outputFolder: 'playwright-report/shell-home', open: 'never' }]],
  use: { baseURL: 'http://127.0.0.1:5175', browserName: 'chromium', trace: 'retain-on-failure' },
  webServer: {
    command: 'npm run preview -- --port 5175 --strictPort',
    url: 'http://127.0.0.1:5175',
    reuseExistingServer: false,
  },
})
