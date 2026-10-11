import { test, expect } from '@playwright/test'
import AxeBuilder from '@axe-core/playwright'

for (const [role, port] of [
  ['admin', 8875],
  ['viewer', 8876],
] as const) {
  test(`real zero-project workspace respects ${role} permission`, async ({ page }, testInfo) => {
    for (const width of [1920, 1440, 1024, 768, 390])
      for (const theme of ['dark', 'light']) {
        await page.setViewportSize({ width, height: 960 })
        await page.goto(`http://127.0.0.1:${port}/projects`)
        await page.evaluate((value) => localStorage.setItem('aryn.shell.theme', value), theme)
        await page.reload()
        await expect(page.getByRole('heading', { name: 'Mulai proyek pertama Anda' })).toBeVisible()
        await expect(page.getByRole('button', { name: 'Buat Proyek', exact: true })).toHaveCount(
          role === 'admin' ? 1 : 0,
        )
        expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(
          false,
        )
        await page.screenshot({
          path: testInfo.outputPath(`live-empty-${role}-${width}-${theme}.png`),
        })
        const accessibility = await new AxeBuilder({ page }).include('#main-content').analyze()
        expect(accessibility.violations).toEqual([])
      }
  })
}
