import { chromium } from '@playwright/test'
import AxeBuilder from '@axe-core/playwright'
import { mkdir, writeFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import { pathToFileURL } from 'node:url'
const evidence = resolve('../../.local/home-v1')
const baseUrl = process.argv[2] ?? 'http://127.0.0.1:8710/'
const reference = process.argv[3] ?? 'C:/Users/User/Downloads/ARYN_Home_Interactive_Concept.html'
await mkdir(evidence, { recursive: true })
const browser = await chromium.launch()
// Reuse one cookie session across views; each capture must not create a new API session.
const context = await browser.newContext()
const report = []
try {
  for (const width of [1440, 768, 390]) {
    const concept = await browser.newPage({ viewport: { width, height: 900 } })
    await concept.goto(pathToFileURL(reference).href)
    for (const scenario of ['new', 'active', 'attention']) {
      await concept
        .getByRole('combobox', { name: 'Pilih kondisi contoh workspace' })
        .selectOption(scenario)
      await concept.screenshot({
        path: resolve(evidence, `reference-${scenario}-${width}-dark.png`),
      })
    }
    await concept.close()
    for (const theme of ['dark', 'light']) {
      const page = await context.newPage()
      await page.setViewportSize({ width, height: 900 })
      const errors = [],
        requests = []
      page.on('pageerror', (error) => errors.push(error.message))
      page.on('response', (response) => {
        if (response.url().includes('/api/projects/'))
          requests.push({ path: new URL(response.url()).pathname, status: response.status() })
      })
      await page.addInitScript((value) => localStorage.setItem('aryn.shell.theme', value), theme)
      await page.goto(baseUrl)
      await page.waitForLoadState('networkidle')
      await page.evaluate(() => document.fonts.ready)
      await page.screenshot({ path: resolve(evidence, `production-home-${width}-${theme}.png`) })
      const state = await page.evaluate(() => ({
        condition: document.querySelector('[data-home-state]')?.getAttribute('data-home-state'),
        overflow: document.documentElement.scrollWidth > innerWidth,
        workspaceOverflow: (() => {
          const main = document.querySelector('.main-workspace')
          return main && main.scrollWidth > main.clientWidth
        })(),
        title: document.title,
        headings: [...document.querySelectorAll('main h1, main h2, main h3')].map(
          (element) => element.textContent,
        ),
        unavailableServices: [...document.querySelectorAll('.home-service-status li > span')].map(
          (element) => element.textContent,
        ),
      }))
      const axe = await new AxeBuilder({ page })
        .withTags(['wcag2a', 'wcag2aa', 'wcag21aa'])
        .analyze()
      report.push({
        width,
        theme,
        ...state,
        requests,
        errors,
        accessibilityViolations: axe.violations.map((item) => item.id),
      })
      if (
        state.overflow ||
        state.workspaceOverflow ||
        errors.length ||
        axe.violations.length ||
        !['new', 'active', 'issues'].includes(state.condition) ||
        requests.some(
          (item) =>
            item.status >= 400 &&
            (['summary', 'blueprints'].includes(item.path.split('/').at(-1)) ||
              !state.unavailableServices.length),
        )
      )
        process.exitCode = 1
      await page.close()
    }
  }
  await writeFile(
    resolve(evidence, 'production-home-browser.json'),
    JSON.stringify(report, null, 2),
  )
  console.log(JSON.stringify(report, null, 2))
} finally {
  await browser.close()
}
