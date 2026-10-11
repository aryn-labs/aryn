import { test, expect } from '@playwright/test'
import AxeBuilder from '@axe-core/playwright'

test('real Studio/Core project persistence and bilingual visual validation', async ({
  page,
}, testInfo) => {
  test.setTimeout(120_000)
  await page.goto('/settings')
  await expect(page.locator('#studio-language')).toBeEnabled()
  await page.locator('#studio-language').selectOption('id-ID')
  await expect(page.locator('#studio-language')).toHaveValue('id-ID')
  await page.goto('/projects')
  await page.getByRole('link', { name: /Validasi Projects Tersimpan/ }).click()
  const base = page.url()
  for (const width of [1920, 1440, 1024, 768, 390])
    for (const theme of ['dark', 'light']) {
      await page.setViewportSize({ width, height: 960 })
      await page.evaluate((value) => localStorage.setItem('aryn.shell.theme', value), theme)
      await page.goto('/projects')
      await page.reload()
      await expect(page.getByRole('link', { name: /Validasi Projects Tersimpan/ })).toBeVisible()
      await page.screenshot({ path: testInfo.outputPath(`live-list-${width}-${theme}.png`) })
      await page.goto(base)
      await expect(page.getByText('Proyek siap digunakan', { exact: true })).toBeVisible()
      await page.screenshot({ path: testInfo.outputPath(`live-overview-${width}-${theme}.png`) })
      expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(
        false,
      )
    }
  await page.goto(base + '/activity')
  await expect(page.getByRole('button', { name: /Informasi proyek diperbarui/ })).toBeVisible()
  await page.getByRole('button', { name: /Informasi proyek diperbarui/ }).click()
  await expect(
    page.getByRole('heading', { name: 'Informasi proyek diperbarui', exact: true }),
  ).toBeVisible()
  await page.screenshot({ path: testInfo.outputPath('live-detail-390-light.png') })
  await page.keyboard.press('Escape')
  expect(
    await page
      .getByRole('button', { name: /Informasi proyek diperbarui/ })
      .evaluate((element) => element === document.activeElement),
  ).toBe(true)
  await page.goto('/settings')
  await expect(page.locator('#studio-language')).toBeEnabled()
  await page.locator('#studio-language').selectOption('en-US')
  await expect(page.locator('#studio-language')).toBeEnabled()
  await page.goto(base)
  await page.reload()
  await expect(page.getByRole('navigation', { name: 'Project pages' })).toBeVisible()
  await page.screenshot({ path: testInfo.outputPath('live-overview-390-english-light.png') })
  const violations = await new AxeBuilder({ page }).include('#main-content').analyze()
  expect(violations.violations).toEqual([])
  await page.goto('/settings')
  await expect(page.locator('#studio-language')).toBeEnabled()
  await page.locator('#studio-language').selectOption('id-ID')
  await expect(page.locator('#studio-language')).toHaveValue('id-ID')
})
