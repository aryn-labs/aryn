import { test, expect, type Page } from '@playwright/test'
import AxeBuilder from '@axe-core/playwright'
import { writeFile } from 'node:fs/promises'

async function create(page: Page, name: string) {
  await page.goto('/agents')
  await page.getByRole('button', { name: 'Buat Agen', exact: true }).click()
  await page.getByLabel('Nama agen').fill(name)
  await page
    .getByLabel('Tujuan', { exact: true })
    .fill('Analisis berbasis bukti untuk pengujian terisolasi.')
  await page.getByRole('dialog').getByRole('button', { name: 'Buat Agen', exact: true }).click()
  await expect(page.getByTestId('node-agent')).toBeVisible()
  await expect(page.getByRole('heading', { name, exact: true })).toBeVisible()
}
test.beforeEach(async ({ context }) => {
  await context.addInitScript(() => {
    if (!localStorage.getItem('aryn.shell.theme')) localStorage.setItem('aryn.shell.theme', 'dark')
    if (!localStorage.getItem('aryn.shell.language'))
      localStorage.setItem('aryn.shell.language', 'id-ID')
  })
})

test('scratch, node registry, ports, history, persistence and Core event animation', async ({
  page,
  request,
}, testInfo) => {
  await page.setViewportSize({ width: 1600, height: 1000 })
  await create(page, 'Agen Kanvas Terisolasi')
  await expect(page.getByTestId('node-input')).toBeVisible()
  await expect(page.getByTestId('node-output')).toBeVisible()
  await page.getByRole('button', { name: 'Tambah node', exact: true }).first().click()
  await page.getByPlaceholder('Cari node…').fill('Budget')
  await page.locator('.af-library-node').filter({ hasText: 'Budget' }).click()
  await expect(page.getByTestId('node-budget')).toBeVisible()
  await page.getByRole('button', { name: 'Hubungkan budget policy out' }).click()
  await page.getByRole('button', { name: 'Hubungkan agent input in' }).click()
  await expect(page.getByText('Jenis atau arah port tidak cocok.', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Hubungkan budget policy out' }).click()
  await page.getByRole('button', { name: 'Hubungkan agent policy in' }).click()
  await expect(page.getByTestId('edge-budget-agent')).toHaveCount(1)
  await page.getByRole('button', { name: 'Urungkan', exact: true }).click()
  await expect(page.getByTestId('edge-budget-agent')).toHaveCount(0)
  await page.getByRole('button', { name: 'Ulangi', exact: true }).click()
  await expect(page.getByTestId('edge-budget-agent')).toHaveCount(1)
  await page.getByRole('button', { name: 'Pilih Budget', exact: true }).press('ArrowRight')
  await page.getByRole('button', { name: 'Simpan Draf', exact: true }).click()
  await expect(page.getByText('Tersimpan', { exact: true }).first()).toBeVisible()
  await page.reload()
  await expect(page.getByTestId('node-budget')).toBeVisible()
  await expect(page.getByTestId('edge-budget-agent')).toHaveCount(1)
  await page.getByRole('button', { name: 'Pusatkan canvas' }).click()
  await page.getByRole('button', { name: 'Tambah node', exact: true }).first().click()
  await page.screenshot({ path: testInfo.outputPath('canvas-library-dark.png'), fullPage: true })
  await page.locator('.af-library').getByRole('button', { name: 'Tutup', exact: true }).click()
  await page.getByRole('button', { name: 'Uji Agen', exact: true }).click()
  await page.getByLabel('Input pengujian').fill('Jelaskan likuiditas secara singkat.')
  await page.getByRole('checkbox', { name: /Saya mengizinkan input/ }).check()
  await request.post('/__test__/runtime-gate', { data: { hold: true } })
  await page.getByRole('button', { name: 'Mulai pengujian', exact: true }).click()
  await expect(page.getByTestId('node-agent')).toHaveAttribute('data-state', 'running')
  await expect(page.getByTestId('node-budget')).toHaveAttribute('data-state', 'idle')
  await expect(page.getByTestId('node-output')).toHaveAttribute('data-state', 'idle')
  await expect(page.getByTestId('edge-input-agent')).toHaveAttribute('data-state', 'running')
  await expect(page.getByTestId('edge-budget-agent')).toHaveAttribute('data-state', 'idle')
  await page.screenshot({ path: testInfo.outputPath('canvas-core-dispatched.png'), fullPage: true })
  await request.post('/__test__/runtime-gate', { data: { hold: false } })
  await expect(page.getByTestId('node-output')).toHaveAttribute('data-state', 'completed')
  await expect(page.getByLabel('Output', { exact: true })).toHaveValue(/PENGUJIAN TERISOLASI/)
  await expect(page.locator('.af-output')).toContainText('Output')
  await expect(page.getByText('Core memverifikasi hasil dan mencatat output')).toBeVisible()
  const runId = await page.evaluate(() => {
    const key = Object.keys(sessionStorage).find((value) => value.startsWith('aryn-preview:'))
    return key ? sessionStorage.getItem(key) : null
  })
  const [, , project, blueprint] = new URL(page.url()).pathname.split('/')
  const persisted = await (
    await page.request.get(`/api/projects/${project}/blueprints/${blueprint}/preview-runs/${runId}`)
  ).json()
  expect(persisted.events.map((event: { type: string }) => event.type)).toEqual([
    'input.accepted',
    'agent.dispatched',
    'run.completed',
  ])
  expect(persisted.result.execution_claim_verified).toBe(true)
  await writeFile(
    testInfo.outputPath('core-events.json'),
    JSON.stringify(
      {
        environment: 'Core/API/SQLite real; inference explicitly isolated test runtime',
        run_id: runId,
        definition_hash: persisted.definition_hash,
        working_copy_generation: persisted.working_copy_generation,
        events: persisted.events,
        actual_model: persisted.result.actual_model,
        status: persisted.result.status,
        usage: persisted.result.usage,
        execution_claim_verified: persisted.result.execution_claim_verified,
      },
      null,
      2,
    ),
  )
  await page.locator('.af-output').scrollIntoViewIfNeeded()
  await page.screenshot({ path: testInfo.outputPath('canvas-core-completed.png'), fullPage: true })
  await page.reload()
  await page.getByRole('button', { name: 'Uji Agen', exact: true }).click()
  await expect(page.getByTestId('node-output')).toHaveAttribute('data-state', 'completed')
  const accessibility = await new AxeBuilder({ page }).include('#main-content').analyze()
  expect(accessibility.violations).toEqual([])
})

test('working copy and layout conflicts preserve local changes', async ({ page, context }) => {
  await create(page, 'Konflik Generasi')
  const other = await context.newPage()
  await other.addInitScript(() => localStorage.setItem('aryn.shell.language', 'id-ID'))
  await other.goto(page.url())
  await expect(other.getByTestId('node-agent')).toBeVisible()
  await page.getByLabel('Tujuan', { exact: true }).fill('Perubahan sesi pertama tersimpan.')
  await page.getByRole('button', { name: 'Simpan Draf', exact: true }).click()
  await expect(page.getByText('Tersimpan', { exact: true }).first()).toBeVisible()
  await other
    .getByLabel('Tujuan', { exact: true })
    .fill('Perubahan sesi kedua tetap aman di editor.')
  await other.getByRole('button', { name: 'Simpan Draf', exact: true }).click()
  await expect(other.getByText(/Draf atau layout berubah di sesi lain/)).toBeVisible()
  await expect(other.getByLabel('Tujuan', { exact: true })).toHaveValue(
    'Perubahan sesi kedua tetap aman di editor.',
  )
  await other.getByRole('button', { name: 'Muat versi server', exact: true }).click()
  await expect(other.getByLabel('Tujuan', { exact: true })).toHaveValue(
    'Perubahan sesi pertama tersimpan.',
  )
  await page.getByRole('button', { name: 'Pilih Agent', exact: true }).press('ArrowRight')
  await page.getByRole('button', { name: 'Simpan Draf', exact: true }).click()
  await expect(page.getByText('Tersimpan', { exact: true }).first()).toBeVisible()
  await other.getByRole('button', { name: 'Pilih Agent', exact: true }).press('ArrowDown')
  const localLayout = await other.getByTestId('node-agent').getAttribute('style')
  await other.getByRole('button', { name: 'Simpan Draf', exact: true }).click()
  await expect(other.getByText(/Draf atau layout berubah di sesi lain/)).toBeVisible()
  await expect(other.getByTestId('node-agent')).toHaveAttribute('style', localLayout!)
  await other.close()
})

test('candidate, Bench, baseline, hash approval, publication and assignment keep published configuration immutable', async ({
  page,
}, testInfo) => {
  test.setTimeout(120_000)
  await page.setViewportSize({ width: 1600, height: 1000 })
  await create(page, 'Lifecycle Kanvas')
  await page.getByRole('button', { name: 'Versi & evaluasi', exact: true }).click()
  await page.getByRole('button', { name: 'Buat versi kandidat', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Setujui versi', exact: true })).toBeDisabled()
  await expect(page.getByRole('button', { name: 'Terbitkan versi', exact: true })).toBeDisabled()
  await page.getByRole('button', { name: 'Jalankan Bench', exact: true }).click()
  await expect(
    page.getByRole('dialog').getByRole('button', { name: 'Lanjutkan', exact: true }),
  ).toBeDisabled()
  await page.getByRole('checkbox', { name: /Saya mengizinkan input/ }).check()
  await page.getByRole('dialog').getByRole('button', { name: 'Lanjutkan', exact: true }).click()
  await expect(page.getByRole('dialog')).toHaveCount(0)
  await page.getByRole('button', { name: 'Terima baseline', exact: true }).click()
  await page
    .getByLabel('Alasan / catatan', { exact: true })
    .fill('Baseline terisolasi disetujui untuk pengujian browser.')
  await page.getByRole('dialog').getByRole('button', { name: 'Lanjutkan', exact: true }).click()
  await expect(page.getByRole('dialog')).toHaveCount(0)
  await page.getByRole('button', { name: 'Setujui versi', exact: true }).click()
  await page
    .getByLabel('Alasan / catatan', { exact: true })
    .fill('Hash dan hasil Bench sudah diperiksa dalam pengujian.')
  await page.getByRole('dialog').getByRole('button', { name: 'Lanjutkan', exact: true }).click()
  await expect(page.getByRole('dialog')).toHaveCount(0)
  await page.getByRole('button', { name: 'Terbitkan versi', exact: true }).click()
  await page.getByRole('dialog').getByRole('button', { name: 'Lanjutkan', exact: true }).click()
  await expect(page.getByRole('dialog')).toHaveCount(0)
  await expect(page.locator('.af-version-detail .af-state')).toHaveText('Published')
  await expect(page.locator('.studio-published')).toContainText('Diterbitkan')
  const hash = await page.locator('.af-version-detail > code').textContent()
  await page.getByRole('button', { name: 'Buat assignment', exact: true }).click()
  await page.getByLabel('Peran assignment').fill('Auditor kanvas')
  await page.getByRole('dialog').getByRole('button', { name: 'Lanjutkan', exact: true }).click()
  await expect(page.getByRole('dialog')).toHaveCount(0)
  await expect(page.locator('.af-assignment-list')).toContainText('Auditor kanvas')
  await page.screenshot({ path: testInfo.outputPath('canvas-lifecycle.png'), fullPage: true })
  await page.getByRole('button', { name: 'Salin ke Working Copy', exact: true }).click()
  await page
    .getByLabel('Tujuan', { exact: true })
    .fill('Working Copy berikutnya tidak mengubah versi published.')
  await expect(page.getByLabel('Nomor versi kandidat')).toHaveValue('1.0.1')
  await page.getByRole('button', { name: 'Simpan Draf', exact: true }).click()
  await expect(page.getByText('Tersimpan', { exact: true }).first()).toBeVisible()
  await page.getByRole('button', { name: 'Versi & evaluasi', exact: true }).click()
  await expect(page.locator('.af-version-detail .af-state')).toHaveText('Published')
  await expect(page.locator('.af-version-detail > code')).toHaveText(hash!)
})

test('pointer dragging, library drag-and-drop and node deletion restore safely', async ({
  page,
}) => {
  await page.setViewportSize({ width: 1600, height: 1000 })
  await create(page, 'Drag Kanvas')
  const node = page.getByRole('button', { name: 'Pilih Agent', exact: true })
  const before = await page.getByTestId('node-agent').getAttribute('style')
  const bounds = (await node.boundingBox())!
  await page.mouse.move(bounds.x + 50, bounds.y + 20)
  await page.mouse.down()
  await page.mouse.move(bounds.x + 130, bounds.y - 40, { steps: 8 })
  await page.mouse.up()
  await expect(page.getByTestId('node-agent')).not.toHaveAttribute('style', before!)
  await page.getByRole('button', { name: 'Urungkan', exact: true }).click()
  await expect(page.getByTestId('node-agent')).toHaveAttribute('style', before!)
  await page.getByRole('button', { name: 'Tambah node', exact: true }).first().click()
  await page
    .locator('.af-library-node')
    .filter({ hasText: 'Budget' })
    .dragTo(page.locator('.af-board'), { targetPosition: { x: 300, y: 90 } })
  await expect(page.getByTestId('node-budget')).toBeVisible()
  await page.getByRole('button', { name: 'Pilih Budget', exact: true }).press('Delete')
  await expect(page.getByTestId('node-budget')).toHaveCount(0)
  await page.getByRole('button', { name: 'Urungkan', exact: true }).click()
  await expect(page.getByTestId('node-budget')).toBeVisible()
})

test('project switching isolates catalogs and English remains usable', async ({
  page,
}, testInfo) => {
  await page.setViewportSize({ width: 1600, height: 1000 })
  await create(page, 'Agen Khusus Riset')
  const original = page.url()
  await page.getByRole('link', { name: 'Kembali ke katalog Agen' }).click()
  await page.getByRole('button', { name: 'Ganti workspace' }).click()
  await page.getByRole('menuitemradio', { name: 'Validasi Kanvas', exact: true }).click()
  await expect(page).toHaveURL(/\/agents$/)
  await expect(
    page.locator('.af-catalog-card').filter({ hasText: 'Agen Khusus Riset' }),
  ).toHaveCount(0)
  await page.getByLabel('Proyek tujuan').selectOption({ label: 'Laboratorium Riset' })
  await expect(
    page.locator('.af-catalog-card').filter({ hasText: 'Agen Khusus Riset' }),
  ).toBeVisible()
  await page.goto('/settings')
  await page.getByLabel('Bahasa', { exact: true }).selectOption('en-US')
  await expect(page.getByLabel('Language', { exact: true })).toHaveValue('en-US')
  await page.goto(original)
  await expect(page.getByRole('button', { name: 'Save Draft', exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Test Agent', exact: true })).toBeVisible()
  await expect(page.getByLabel('Objective', { exact: true })).toBeVisible()
  await page.screenshot({ path: testInfo.outputPath('canvas-english.png'), fullPage: true })
  await page.goto('/settings')
  await page.getByLabel('Language', { exact: true }).selectOption('id-ID')
  await expect(page.getByLabel('Bahasa', { exact: true })).toHaveValue('id-ID')
})

for (const width of [1440, 768, 390])
  for (const theme of ['dark', 'light']) {
    test(`responsive accessibility ${width} ${theme}`, async ({ page }, testInfo) => {
      await page.setViewportSize({ width, height: 1000 })
      await page.addInitScript((value) => localStorage.setItem('aryn.shell.theme', value), theme)
      await create(page, `Canvas ${width} ${theme}`)
      await page.getByRole('button', { name: 'Pusatkan canvas' }).click()
      await page.screenshot({
        path: testInfo.outputPath(`canvas-${width}-${theme}.png`),
        fullPage: true,
      })
      expect(
        await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth),
      ).toBe(false)
      expect(
        (await new AxeBuilder({ page }).include('#main-content').analyze()).violations,
      ).toEqual([])
      await page.emulateMedia({ reducedMotion: 'reduce' })
      await expect(page.locator('.af-spin').first()).toHaveCount(0)
      if (width <= 900) {
        await page.getByRole('button', { name: 'Buka inspector', exact: true }).click()
        await expect(page.getByRole('dialog', { name: 'Konfigurasi', exact: true })).toBeVisible()
        await page.screenshot({ path: testInfo.outputPath(`studio-drawer-${width}-${theme}.png`) })
        expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([])
        await page.locator('#studio-inspector').press('Escape')
        await expect(page.locator('#studio-inspector')).toBeHidden()
      }
    })
  }

test('dedicated shell, floating library, retained inspector form and guarded dashboard navigation', async ({
  page,
}, testInfo) => {
  await page.setViewportSize({ width: 1600, height: 1000 })
  await create(page, 'Studio Agen Riset')
  const deepLink = page.url()
  await expect(page.locator('.app-sidebar, .app-topbar, .workspace-footer')).toHaveCount(0)
  await expect(page.getByRole('navigation', { name: 'Navigasi Studio' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Ganti workspace' })).toHaveCount(0)
  const board = page.locator('.af-board')
  const area = (await board.boundingBox())!
  await writeFile(
    testInfo.outputPath('studio-layout-metrics.json'),
    JSON.stringify(
      {
        viewport: { width: 1600, height: 1000 },
        canvas: area,
        header: await page.locator('.studio-header').boundingBox(),
        navigation: await page.locator('.studio-navigation').boundingBox(),
        inspector: await page.locator('#studio-inspector').boundingBox(),
      },
      null,
      2,
    ),
  )
  expect(area.width).toBeGreaterThan(1100)
  expect(area.height).toBeGreaterThan(850)
  expect((await page.locator('.studio-header').boundingBox())!.height).toBeLessThan(80)
  await page.getByRole('button', { name: 'Pusatkan canvas' }).click()
  await page.screenshot({ path: testInfo.outputPath('studio-desktop.png') })
  await page.getByRole('button', { name: 'Node Library', exact: true }).click()
  const search = page.getByPlaceholder('Cari node…')
  await expect(search).toBeFocused()
  expect((await board.boundingBox())!.width).toBe(area.width)
  await search.fill('tidak ditemukan')
  await expect(page.getByText('Tidak ada node yang cocok.')).toBeVisible()
  await search.press('Escape')
  await expect(page.locator('.studio-library')).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Node Library', exact: true })).toBeFocused()
  await page.getByRole('button', { name: 'Node Library', exact: true }).click()
  await board.click({ position: { x: 700, y: 120 } })
  await expect(page.locator('.studio-library')).toHaveCount(0)
  await page.getByRole('button', { name: 'Tambah node', exact: true }).click()
  await page.screenshot({ path: testInfo.outputPath('studio-floating-library.png') })
  await page.locator('.af-library-node').filter({ hasText: 'Budget' }).click()
  await expect(page.locator('.studio-library')).toHaveCount(0)
  await expect(board).toBeFocused()
  await page.getByRole('button', { name: 'Pilih Agent', exact: true }).click()
  await page
    .locator('.af-inspector-sections')
    .getByRole('button', { name: 'Output', exact: true })
    .click()
  await page.getByLabel('Format output', { exact: true }).selectOption('json')
  await page.getByLabel('JSON Schema (opsional)', { exact: true }).fill('{belum valid')
  await page
    .locator('#studio-inspector')
    .getByRole('button', { name: 'Tutup inspector', exact: true })
    .click()
  await expect(page.locator('#studio-inspector')).toBeHidden()
  expect((await board.boundingBox())!.width).toBeGreaterThan(area.width)
  await page.getByRole('button', { name: 'Buka inspector', exact: true }).click()
  await expect(page.getByLabel('JSON Schema (opsional)', { exact: true })).toHaveValue(
    '{belum valid',
  )
  await expect(page.getByLabel('JSON Schema (opsional)', { exact: true })).toHaveAttribute(
    'aria-invalid',
    'true',
  )
  await page.getByRole('link', { name: 'Kembali ke katalog Agen' }).click()
  await expect(page.getByRole('dialog', { name: 'Ada perubahan belum disimpan' })).toBeVisible()
  await page.getByRole('button', { name: 'Tetap di editor', exact: true }).click()
  await expect(page).toHaveURL(deepLink)
  await expect(page.getByLabel('JSON Schema (opsional)', { exact: true })).toHaveValue(
    '{belum valid',
  )
  await page.getByLabel('JSON Schema (opsional)', { exact: true }).fill('{"type":"object"}')
  await page.getByRole('button', { name: 'Simpan Draf', exact: true }).click()
  await expect(page.locator('.studio-save-state')).toHaveText('Tersimpan')
  await page.getByRole('button', { name: 'Gunakan mode terang', exact: true }).click()
  await page.getByRole('link', { name: 'Kembali ke katalog Agen' }).click()
  await expect(page.locator('.app-sidebar')).toBeVisible()
  await expect(page.getByRole('main')).toBeFocused()
  await expect(page.locator('.studio-shell')).toHaveCount(0)
  await expect(page.locator('html')).not.toHaveClass(/dark/)
  await page.goto(deepLink)
  await expect(page.getByTestId('node-budget')).toBeVisible()
  await expect(page.locator('.app-sidebar')).toHaveCount(0)
  await expect(page.locator('.studio-identity')).toContainText('Laboratorium Riset')
  await page
    .locator('.af-inspector-sections')
    .getByRole('button', { name: 'Output', exact: true })
    .click()
  expect(
    JSON.parse(await page.getByLabel('JSON Schema (opsional)', { exact: true }).inputValue()),
  ).toEqual({ type: 'object' })
  // Invalid local text alone must block leaving even when the persisted draft is unchanged.
  await page.getByLabel('JSON Schema (opsional)', { exact: true }).fill('{masih lokal')
  await page.getByRole('link', { name: 'Kembali ke katalog Agen' }).click()
  await expect(page.getByRole('dialog', { name: 'Ada perubahan belum disimpan' })).toBeVisible()
  await page.getByRole('button', { name: 'Tetap di editor', exact: true }).click()
  await page.getByLabel('JSON Schema (opsional)', { exact: true }).fill('{"type":"object"}')
  await expect(page.locator('.studio-save-state')).toHaveText('Tersimpan')
  await page
    .locator('.af-inspector-sections')
    .getByRole('button', { name: 'Agent', exact: true })
    .click()
  await page
    .getByLabel('Tujuan', { exact: true })
    .fill('Perubahan lokal yang ditinggalkan secara eksplisit.')
  await page.getByRole('link', { name: 'Kembali ke katalog Agen' }).click()
  await page
    .getByRole('dialog')
    .getByRole('button', { name: 'Tinggalkan perubahan lokal', exact: true })
    .click()
  await expect(page).toHaveURL(/\/agents$/)
  await page.goto(deepLink)
  await expect(page.getByLabel('Tujuan', { exact: true })).toHaveValue(
    'Analisis berbasis bukti untuk pengujian terisolasi.',
  )
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([])
})

test('Studio rejects mismatched API blueprint ownership before changing shared project context', async ({
  page,
}) => {
  await page.setViewportSize({ width: 1440, height: 1000 })
  await create(page, 'Scope Studio')
  const deepLink = page.url()
  await page.getByRole('link', { name: 'Kembali ke katalog Agen' }).click()
  await page.getByRole('button', { name: 'Ganti workspace' }).click()
  await page.getByRole('menuitemradio', { name: 'Validasi Kanvas', exact: true }).click()
  await page.route('**/lifecycle?*', async (route) => {
    const response = await route.fetch()
    const body = await response.json()
    body.blueprints = body.blueprints.map((blueprint: Record<string, unknown>) => ({
      ...blueprint,
      project_id: 'different-project',
    }))
    await route.fulfill({ response, json: body })
  })
  await page.goto(deepLink)
  await expect(page.getByRole('alert')).toBeVisible()
  await expect(page.getByTestId('node-agent')).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Simpan Draf', exact: true })).toHaveCount(0)
  await page.getByRole('link', { name: 'Kembali ke katalog Agen' }).click()
  await expect(page.getByRole('button', { name: 'Ganti workspace' })).toContainText(
    'Validasi Kanvas',
  )
  await page.unroute('**/lifecycle?*')
  await page.goto(deepLink)
  await expect(page.getByTestId('node-agent')).toBeVisible()
  await expect(page.locator('.studio-identity')).toContainText('Laboratorium Riset')
  await page.getByRole('link', { name: 'Kembali ke katalog Agen' }).click()
  await expect(page.getByRole('button', { name: 'Ganti workspace' })).toContainText(
    'Laboratorium Riset',
  )
})

test('mobile Studio drawer focus, Escape, library overlay, pan and zoom', async ({
  page,
}, testInfo) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await create(page, 'Studio Mobile')
  await expect(page.locator('#studio-inspector')).toBeHidden()
  await page.getByRole('button', { name: 'Pusatkan canvas' }).click()
  const board = page.locator('.af-board')
  await board.focus()
  const before = await page.locator('.af-stage').getAttribute('style')
  await board.press('ArrowLeft')
  await expect(page.locator('.af-stage')).not.toHaveAttribute('style', before!)
  const zoom = await page.locator('.af-zoom-tools output').textContent()
  await page.getByRole('button', { name: 'Perbesar', exact: true }).click()
  await expect(page.locator('.af-zoom-tools output')).not.toHaveText(zoom!)
  await page.getByRole('button', { name: 'Buka inspector', exact: true }).click()
  await expect(page.locator('#studio-inspector')).toBeFocused()
  await page.locator('#studio-inspector').press('Shift+Tab')
  expect(
    await page.evaluate(() => document.activeElement?.closest('#studio-inspector') !== null),
  ).toBe(true)
  await page
    .getByLabel('Tujuan', { exact: true })
    .fill('Konfigurasi mobile tetap tersimpan dalam Working Copy.')
  await page.screenshot({ path: testInfo.outputPath('studio-mobile-inspector.png') })
  await page.getByLabel('Tujuan', { exact: true }).press('Escape')
  await expect(page.locator('#studio-inspector')).toBeHidden()
  await page.getByRole('button', { name: 'Node Library', exact: true }).click()
  await page.screenshot({ path: testInfo.outputPath('studio-mobile-library.png') })
  await page.locator('.af-library-node').filter({ hasText: 'Budget' }).click()
  await expect(page.locator('.studio-library')).toHaveCount(0)
  await expect(board).toBeFocused()
  await page.getByRole('button', { name: 'Simpan Draf', exact: true }).click()
  await expect(page.locator('.studio-save-state')).toHaveText('Tersimpan')
  await page.reload()
  await page.getByRole('button', { name: 'Buka inspector', exact: true }).click()
  await expect(page.getByLabel('Tujuan', { exact: true })).toHaveValue(
    'Konfigurasi mobile tetap tersimpan dalam Working Copy.',
  )
  await page.getByLabel('Tujuan', { exact: true }).press('Escape')
  await page.getByRole('button', { name: 'Pusatkan canvas' }).click()
  await page.getByRole('button', { name: 'Perbesar', exact: true }).click()
  await page.getByRole('button', { name: 'Perbesar', exact: true }).click()
  await page.screenshot({ path: testInfo.outputPath('studio-mobile.png') })
  expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false)
})
