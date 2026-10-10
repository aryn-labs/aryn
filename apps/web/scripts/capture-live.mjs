import { chromium } from '@playwright/test'
import { mkdir, writeFile } from 'node:fs/promises'
import { resolve } from 'node:path'
const evidence = resolve('../../.local/studio-shell-v1')
const baseUrl = process.argv[2] ?? 'http://127.0.0.1:5173/'
const prefix = new URL(baseUrl).port === '8710' ? 'production' : 'live'
await mkdir(evidence, { recursive: true })
const browser = await chromium.launch()
const report = []
try {
  for (const width of [1440, 768, 390]) {
    const page = await browser.newPage({ viewport: { width, height: 900 } })
    const errors = []
    page.on('pageerror', (error) => errors.push(error.message))
    await page.goto(baseUrl)
    await page.waitForLoadState('networkidle')
    await page.evaluate(() => document.fonts.ready)
    await page.screenshot({ path: resolve(evidence, `${prefix}-${width}-dark.png`) })
    const state = await page.evaluate(() => {
      const main = document.querySelector('.main-workspace')
      const topbar = document.querySelector('.app-topbar')
      const brand = document.querySelector('.topbar-brand')?.getBoundingClientRect()
      const sidebar = document.querySelector('.app-sidebar')?.getBoundingClientRect()
      return {
        title: document.title,
        overflow: document.documentElement.scrollWidth > innerWidth,
        mainOverflow: !!main && main.scrollWidth > main.clientWidth,
        topbarOverflow: !!topbar && topbar.scrollWidth > topbar.clientWidth,
        brandDivider: brand?.right,
        sidebarDivider: sidebar?.width ? sidebar.right : null,
        dividerAligned: sidebar?.width ? brand?.right === sidebar.right : null,
        contextRemoved: !document.querySelector('.context-inspector, [data-inspector-toggle]'),
        breadcrumbRemoved: !document.querySelector('.workspace-breadcrumb'),
        workspaceSwitcherCount: document.querySelectorAll('[aria-label="Switch workspace"]').length,
        runtimeIndicatorsRemoved: !topbar?.querySelector(
          '[aria-label="Environment information"], [aria-label="Model information"]',
        ),
        footer: document.querySelector('.workspace-footer')?.textContent,
      }
    })
    if (
      errors.length ||
      state.overflow ||
      state.mainOverflow ||
      state.topbarOverflow ||
      state.dividerAligned === false ||
      !state.contextRemoved ||
      !state.breadcrumbRemoved ||
      !state.runtimeIndicatorsRemoved ||
      state.workspaceSwitcherCount !== 1
    )
      process.exitCode = 1
    if (width === 1440 || width === 390) {
      await page.getByRole('button', { name: 'Switch workspace' }).click()
      await page.getByRole('menu', { name: 'Switch workspace' }).waitFor()
      await page.screenshot({ path: resolve(evidence, `${prefix}-workspace-${width}-dark.png`) })
      await page.keyboard.press('Escape')
      await page.goto(new URL('/settings', baseUrl).href)
      await page.waitForLoadState('networkidle')
      await page.screenshot({ path: resolve(evidence, `${prefix}-settings-${width}-dark.png`) })
      if (await page.locator('.main-workspace').evaluate((el) => el.scrollWidth > el.clientWidth))
        process.exitCode = 1
    }
    if (errors.length) process.exitCode = 1
    report.push({ width, ...state, errors })
    await page.close()
  }
  await writeFile(resolve(evidence, `${prefix}-browser.json`), JSON.stringify(report, null, 2))
  console.log(JSON.stringify(report, null, 2))
} finally {
  await browser.close()
}
