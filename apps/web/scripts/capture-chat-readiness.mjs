// Actual local API screenshots. This helper never substitutes API/model responses.
import { chromium, expect } from '@playwright/test'
import AxeBuilder from '@axe-core/playwright'
import { mkdir, writeFile } from 'node:fs/promises'
import { resolve } from 'node:path'
const evidence = resolve('../../.local/chat-finalization')
const url = process.argv[2] ?? 'http://127.0.0.1:8710/'
const chat = new URL(url).pathname.startsWith('/chat/')
const surface = chat ? 'chat' : 'home'
await mkdir(evidence, { recursive: true })
const browser = await chromium.launch()
const context = await browser.newContext()
const report = []
try {
  for (const width of [1920, 1440, 1024, 768, 390])
    for (const theme of ['dark', 'light']) {
      const page = await context.newPage()
      await page.setViewportSize({ width, height: 900 })
      const errors = []
      page.on('pageerror', (error) => errors.push(error.message))
      await page.addInitScript((value) => localStorage.setItem('aryn.shell.theme', value), theme)
      await page.goto(url)
      await page.waitForLoadState('networkidle')
      if (chat) await page.locator('.chat-message-assistant').first().waitFor({ state: 'visible' })
      await page.evaluate(() => document.fonts.ready)
      const state = await page.evaluate(() => ({
        condition: document.querySelector('[data-home-state]')?.getAttribute('data-home-state'),
        overflow: document.documentElement.scrollWidth > innerWidth,
        workspaceOverflow: (() => {
          const node = document.querySelector('main')
          return !node || node.scrollWidth > node.clientWidth
        })(),
        assistant: document.querySelector('.composer-reason p')?.textContent,
        sendEnabled: !document.querySelector('.home-composer button[type="submit"]')?.disabled,
        assistantMessages: document.querySelectorAll('.chat-message-assistant').length,
      }))
      const axe = await new AxeBuilder({ page })
        .withTags(['wcag2a', 'wcag2aa', 'wcag21aa'])
        .analyze()
      if (chat) {
        const history = page.getByRole('button', {
          name: /Riwayat percakapan|Conversation history/,
          exact: true,
        })
        await history.click()
        await page.getByRole('dialog').waitFor({ state: 'visible' })
        await page.keyboard.press('Tab')
        await expect
          .poll(() =>
            page.getByRole('dialog').evaluate((node) => node.contains(document.activeElement)),
          )
          .toBe(true)
        await page.keyboard.press('Escape')
        await page.getByRole('dialog').waitFor({ state: 'hidden' })
        await expect(history).toBeFocused()
      }
      await page.screenshot({ path: resolve(evidence, `live-${surface}-${width}-${theme}.png`) })
      if (chat && [1440, 390].includes(width)) {
        await page.locator('.chat-scroll').evaluate((node) => {
          node.scrollTop = 0
        })
        await page.screenshot({
          path: resolve(evidence, `live-chat-${width}-${theme}-start.png`),
        })
      }
      report.push({
        width,
        theme,
        ...state,
        errors,
        accessibilityViolations: axe.violations.map((item) => item.id),
      })
      if (state.overflow || state.workspaceOverflow || errors.length || axe.violations.length)
        throw new Error(`Actual ${surface} validation failed at ${width} ${theme}`)
      await page.close()
    }
} finally {
  await writeFile(
    resolve(evidence, `live-${surface}-visual-review.json`),
    JSON.stringify(report, null, 2),
  )
  await context.close()
  await browser.close()
}
