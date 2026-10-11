import { test, expect } from '@playwright/test'
import AxeBuilder from '@axe-core/playwright'

for (const width of [1920, 1440, 1024, 768, 390])
  for (const theme of ['dark', 'light']) {
    test(`Projects ${width}px ${theme}: create edit tabs refresh keyboard accessibility`, async ({
      page,
    }, testInfo) => {
      await page.setViewportSize({ width, height: 960 })
      await page.addInitScript((value) => {
        localStorage.setItem('aryn.shell.theme', value)
        localStorage.setItem('aryn.shell.language', 'id-ID')
      }, theme)
      await page.goto('/projects')
      await expect(page.getByRole('heading', { name: 'Proyek', exact: true })).toBeVisible()
      await expect(page.getByRole('link', { name: /Validasi Proyek/ })).toBeVisible()
      await page.screenshot({ path: testInfo.outputPath(`projects-list-${width}-${theme}.png`) })
      await page.getByRole('button', { name: 'Proyek Baru', exact: true }).click()
      const name = `Validasi ${width} ${theme}`
      await page.getByLabel('Nama proyek').fill(name)
      await page.getByLabel(/Tujuan proyek/).fill('Metadata proyek tersimpan melalui Core')
      await page.getByRole('button', { name: 'Buat Proyek', exact: true }).click()
      await expect(page).toHaveURL(/\/projects\/proj_[a-f0-9]+$/)
      await expect(page.getByRole('heading', { name, exact: true })).toBeVisible()
      await expect(page.getByText('Proyek siap digunakan', { exact: true })).toBeVisible()
      await page.screenshot({
        path: testInfo.outputPath(`projects-workspace-${width}-${theme}.png`),
      })
      for (const label of ['Pekerjaan', 'Tim & Agen', 'Hasil', 'Aktivitas', 'Ringkasan']) {
        await page
          .getByRole('navigation', { name: 'Subhalaman proyek' })
          .getByRole('link', { name: label, exact: true })
          .click()
        await expect(
          page
            .getByRole('navigation', { name: 'Subhalaman proyek' })
            .getByRole('link', { name: label, exact: true }),
        ).toHaveAttribute('aria-current', 'page')
        await expect(page.locator('.project-tabs [aria-current="page"]')).toHaveCount(1)
        await page.reload()
        await expect(page.getByRole('heading', { name, exact: true })).toBeVisible()
        const overflow = await page.evaluate(
          () => document.documentElement.scrollWidth > window.innerWidth,
        )
        expect(overflow).toBe(false)
      }
      await page.getByRole('button', { name: 'Pengaturan proyek' }).click()
      await page.getByRole('menuitem', { name: 'Ubah Proyek' }).click()
      await page.getByLabel('Nama proyek').fill(name + ' Diperbarui')
      await page.getByRole('button', { name: 'Simpan Perubahan' }).click()
      await expect(
        page.getByRole('heading', { name: name + ' Diperbarui', exact: true }),
      ).toBeVisible()
      await page.reload()
      await expect(
        page.getByRole('heading', { name: name + ' Diperbarui', exact: true }),
      ).toBeVisible()
      await page
        .getByRole('navigation', { name: 'Subhalaman proyek' })
        .getByRole('link', { name: 'Aktivitas' })
        .click()
      await page.getByRole('button', { name: /Informasi proyek diperbarui/ }).click()
      await expect(page.getByRole('dialog')).toBeVisible()
      await expect(
        page.getByRole('heading', { name: 'Informasi proyek diperbarui', exact: true }),
      ).toBeVisible()
      await page.screenshot({ path: testInfo.outputPath(`projects-detail-${width}-${theme}.png`) })
      await page.keyboard.press('Escape')
      await expect(page.getByRole('dialog')).not.toBeVisible()
      const violations = await new AxeBuilder({ page }).include('#main-content').analyze()
      expect(violations.violations).toEqual([])
    })
  }

test('project deep link and topbar selection stay synchronized', async ({ page }) => {
  await page.goto('/projects')
  await page.getByRole('link', { name: /Validasi Proyek/ }).click()
  await expect(page.getByRole('heading', { name: 'Validasi Proyek', exact: true })).toBeVisible()
  await page.reload()
  await expect(page.getByRole('heading', { name: 'Validasi Proyek', exact: true })).toBeVisible()
  await page
    .getByRole('navigation', { name: 'Subhalaman proyek' })
    .getByRole('link', { name: 'Pekerjaan', exact: true })
    .click()
  await page.getByRole('button', { name: 'Ganti workspace' }).click()
  await page.getByRole('menuitemradio', { name: 'Laboratorium Riset', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Laboratorium Riset', exact: true })).toBeVisible()
  await expect(page).toHaveURL(/\/projects\/[^/]+\/work$/)
})

test('populated five-page visual matrix and safe output details', async ({ page }, testInfo) => {
  test.setTimeout(120_000)
  await page.goto('/projects')
  await page.getByRole('link', { name: /Laboratorium Riset/ }).click()
  const projectUrl = page.url()
  for (const width of [1920, 1440, 1024, 768, 390])
    for (const theme of ['dark', 'light']) {
      await page.setViewportSize({ width, height: 960 })
      await page.evaluate((value) => localStorage.setItem('aryn.shell.theme', value), theme)
      await page.reload()
      for (const [label, suffix] of [
        ['Ringkasan', 'overview'],
        ['Pekerjaan', 'work'],
        ['Tim & Agen', 'team'],
        ['Hasil', 'results'],
        ['Aktivitas', 'activity'],
      ]) {
        await page
          .getByRole('navigation', { name: 'Subhalaman proyek' })
          .getByRole('link', { name: label, exact: true })
          .click()
        await expect(page.locator('.project-skeleton')).toHaveCount(0)
        await expect(page.locator('.project-tabs [aria-current="page"]')).toHaveCount(1)
        await expect(
          page.locator('.project-resource-row, .project-activity-list button').first(),
        ).toBeVisible()
        if (suffix === 'overview') {
          await expect(page.locator('.project-attention-row')).toContainText('Peninjauan hasil')
          await expect(
            page.locator('.project-resource-row').filter({ hasText: 'Agent riset tes' }),
          ).toContainText('Penugasan agen')
        }
        expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(
          false,
        )
        await page.screenshot({
          path: testInfo.outputPath(`populated-${suffix}-${width}-${theme}.png`),
        })
        const accessibility = await new AxeBuilder({ page }).include('#main-content').analyze()
        expect(accessibility.violations).toEqual([])
      }
    }
  await page.goto(projectUrl + '/results')
  await page.getByRole('button', { name: 'Website', exact: true }).click()
  await page.locator('.project-resource-row').first().click()
  await expect(page.getByText(/Viewer untuk format ini belum tersedia/)).toBeVisible()
  await expect(page.getByText('Bukti terverifikasi', { exact: true })).toBeVisible()
  const detailUrl = page.url()
  await page.setViewportSize({ width: 1440, height: 960 })
  await page.evaluate(() => localStorage.setItem('aryn.shell.theme', 'dark'))
  await page.reload()
  await expect(page.getByRole('dialog')).toBeVisible()
  await expect(page.getByText(/Viewer untuk format ini belum tersedia/)).toBeVisible()
  await page.screenshot({ path: testInfo.outputPath('result-detail-desktop-dark.png') })
  const drawerAccessibility = await new AxeBuilder({ page })
    .include('.project-detail-drawer')
    .analyze()
  expect(drawerAccessibility.violations).toEqual([])
  await page.setViewportSize({ width: 390, height: 960 })
  await page.evaluate(() => localStorage.setItem('aryn.shell.theme', 'light'))
  await page.reload()
  await expect(page.getByRole('dialog')).toBeVisible()
  await expect(page.getByText(/Viewer untuk format ini belum tersedia/)).toBeVisible()
  expect(page.url()).toBe(detailUrl)
  await page.screenshot({ path: testInfo.outputPath('result-detail-mobile-light.png') })
  await page.keyboard.press('Escape')
  await expect(page.locator('#main-content')).toBeFocused()
  const violations = await new AxeBuilder({ page }).include('#main-content').analyze()
  expect(violations.violations).toEqual([])
})
