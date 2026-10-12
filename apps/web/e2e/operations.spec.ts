import { test, expect, type Page } from '@playwright/test'
import AxeBuilder from '@axe-core/playwright'
import { mkdir } from 'node:fs/promises'
import { resolve } from 'node:path'
const evidence = resolve('../../.local/runs-automations-evidence')
test.beforeAll(async () => {
  await mkdir(evidence, { recursive: true })
})
test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    localStorage.setItem('aryn.shell.language', 'id-ID')
    localStorage.setItem('aryn.shell.theme', 'dark')
  })
  await page.goto('/runs')
  await page.evaluate(async () => {
    const session = await fetch('/api/session', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: '{}',
    }).then((r) => r.json())
    const workspace = await fetch('/api/workspace/context').then((r) => r.json())
    await fetch('/api/projects/' + workspace.projects[0].id + '/chat/preferences', {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': session.csrf },
      body: JSON.stringify({ locale: 'id-ID' }),
    })
  })
})
async function axe(page: Page) {
  const result = await new AxeBuilder({ page }).exclude('iframe').analyze()
  expect(result.violations).toEqual([])
}
async function create(
  page: Page,
  name: string,
  kind: 'cron' | 'daily' | 'weekly' | 'interval' = 'cron',
  targetKind: 'agent' | 'workflow' = 'agent',
) {
  await page.goto('/automations')
  await page.getByRole('link', { name: 'Buat Otomatisasi', exact: true }).click()
  await page.getByLabel('Nama otomatisasi', { exact: true }).fill(name)
  await page
    .locator('.op-choices button')
    .filter({ hasText: targetKind === 'agent' ? 'Agent' : 'Workflow' })
    .click()
  await page.getByLabel('Target', { exact: true }).selectOption({ index: 1 })
  await page
    .getByLabel('Input target', { exact: true })
    .fill('Permintaan automation terisolasi melalui Core.')
  await page.getByRole('button', { name: 'Lanjutkan', exact: true }).click()
  await page
    .locator('.op-choices button')
    .filter({
      hasText:
        kind === 'cron'
          ? 'Custom Cron'
          : kind === 'daily'
            ? 'Harian'
            : kind === 'weekly'
              ? 'Mingguan'
              : 'Interval',
    })
    .click()
  await page.getByRole('button', { name: 'Periksa jadwal', exact: true }).click()
  await expect(page.locator('.op-preview li')).toHaveCount(5)
  await page.getByRole('button', { name: 'Lanjutkan', exact: true }).click()
  await page.getByRole('button', { name: 'Lanjutkan', exact: true }).click()
  await page.getByRole('checkbox', { name: /Saya mengizinkan input diproses/ }).check()
  await page.getByRole('button', { name: 'Simpan sebagai Dijeda', exact: true }).click()
  await expect(page.getByRole('dialog').getByRole('heading', { name, exact: true })).toBeVisible()
}
async function approve(page: Page) {
  await page.getByRole('button', { name: 'Setujui hash ini', exact: true }).click()
  await page
    .getByLabel('Alasan', { exact: true })
    .fill('Konfigurasi dan hash diperiksa pada pengujian terisolasi.')
  await page.getByRole('button', { name: 'Konfirmasi', exact: true }).click()
  await expect(page.getByText('Configuration hash disetujui', { exact: true }).last()).toBeVisible()
}
test('Runs real persisted inventory, unknown, workflow read-only graph, artifact and cross-navigation', async ({
  page,
}) => {
  await page.setViewportSize({ width: 1600, height: 1000 })
  await page.goto('/runs')
  await expect(page.getByRole('heading', { name: 'Eksekusi', exact: true })).toBeVisible()
  await expect(page.locator('.op-table tbody tr')).toHaveCount(5)
  await page.screenshot({ path: resolve(evidence, 'runs-desktop-dark.png') })
  await page.getByLabel('Status', { exact: true }).selectOption('outcome_unknown')
  await page.locator('.op-name').first().click()
  await expect(page.getByText(/Outcome unknown: hasil belum dapat dipastikan/)).toBeVisible()
  await page.screenshot({ path: resolve(evidence, 'outcome-unknown.png') })
  await page.keyboard.press('Escape')
  await page.getByLabel('Status', { exact: true }).selectOption('completed')
  await page.locator('.op-name').first().click()
  await page.getByRole('button', { name: 'Evidence', exact: true }).click()
  await expect(page.getByText('test/model-a', { exact: true }).last()).toBeVisible()
  await page.screenshot({ path: resolve(evidence, 'agent-run-detail.png') })
  await page.getByRole('button', { name: 'Timeline', exact: true }).click()
  await expect(page.locator('.op-timeline li')).not.toHaveCount(0)
  await page.keyboard.press('Escape')
  await page.getByLabel('Status', { exact: true }).selectOption('')
  await page.getByLabel('Jenis', { exact: true }).selectOption('workflow')
  await page.locator('.op-name').click()
  await expect(page.getByRole('application', { name: /Graph versi yang dijalankan/ })).toBeVisible()
  await expect(page.getByTestId('node-review')).toHaveAttribute('data-state', 'waiting_review')
  await page.screenshot({ path: resolve(evidence, 'workflow-run-detail.png') })
  await page.getByRole('button', { name: 'Input & Output', exact: true }).click()
  await expect(page.getByRole('link', { name: 'Unduh artifact', exact: true })).toBeVisible()
  await page.screenshot({ path: resolve(evidence, 'run-artifact.png') })
  await axe(page)
  await page.reload()
  await expect(page.getByRole('dialog')).toBeVisible()
  await page.getByRole('button', { name: 'Hentikan eksekusi', exact: true }).click()
  await page.getByRole('button', { name: 'Konfirmasi', exact: true }).click()
  await expect(page.getByTestId('node-review')).toHaveAttribute('data-state', 'cancelled')
  await expect(
    page
      .locator('main .op-table tbody tr')
      .filter({ hasText: 'Workflow Observasi Terisolasi' })
      .locator('.op-status'),
  ).toHaveAttribute('data-state', 'cancelled')
  await expect(page.getByRole('button', { name: 'Hentikan eksekusi', exact: true })).toHaveCount(0)
  await page.screenshot({ path: resolve(evidence, 'workflow-cancelled.png') })
})
test('four-step Cron builder, explicit approval, activation, manual occurrence and exact Runs link', async ({
  page,
  request,
}) => {
  await page.setViewportSize({ width: 1600, height: 1000 })
  await page.goto('/automations')
  await page.screenshot({ path: resolve(evidence, 'automations-catalog.png') })
  await page.getByRole('link', { name: 'Buat Otomatisasi', exact: true }).click()
  await page.getByLabel('Nama otomatisasi', { exact: true }).fill('Cron Terisolasi')
  await page.getByLabel('Target', { exact: true }).selectOption({ index: 1 })
  await page
    .getByLabel('Input target', { exact: true })
    .fill('Input tetap untuk eksekusi terisolasi.')
  await page.screenshot({ path: resolve(evidence, 'wizard-target.png') })
  await page.getByRole('button', { name: 'Lanjutkan', exact: true }).click()
  await expect(page.locator('.op-choices button').filter({ hasText: 'MCP Event' })).toBeDisabled()
  await expect(
    page.locator('.op-choices button').filter({ hasText: 'Secure Webhook' }),
  ).toBeDisabled()
  await page.screenshot({ path: resolve(evidence, 'trigger-selection-webhook-unavailable.png') })
  await page.locator('.op-choices button').filter({ hasText: 'Custom Cron' }).click()
  await page.getByLabel('Cron expression', { exact: true }).fill('60 9 * * *')
  await page.getByRole('button', { name: 'Periksa jadwal', exact: true }).click()
  await expect(page.getByRole('alert')).toBeVisible()
  await page.getByLabel('Cron expression', { exact: true }).fill('0 9 * * 1-5')
  await page.getByRole('button', { name: 'Periksa jadwal', exact: true }).click()
  await expect(page.locator('.op-preview li')).toHaveCount(5)
  await page.screenshot({ path: resolve(evidence, 'custom-cron.png') })
  await page.getByRole('button', { name: 'Lanjutkan', exact: true }).click()
  await page.screenshot({ path: resolve(evidence, 'wizard-policy.png') })
  await page.getByRole('button', { name: 'Lanjutkan', exact: true }).click()
  await page.getByRole('checkbox', { name: /Saya mengizinkan input diproses/ }).check()
  await page.screenshot({ path: resolve(evidence, 'wizard-review.png') })
  await page
    .getByRole('heading', { name: 'Buat Otomatisasi', exact: true })
    .scrollIntoViewIfNeeded()
  await page.screenshot({ path: resolve(evidence, 'wizard-review-top.png') })
  await page.getByRole('button', { name: 'Simpan sebagai Dijeda', exact: true }).click()
  await expect(
    page.getByRole('dialog').getByText('Memerlukan approval exact hash', { exact: true }),
  ).toBeVisible()
  await expect(page.getByRole('button', { name: 'Aktifkan', exact: true })).toBeDisabled()
  await approve(page)
  await page.screenshot({ path: resolve(evidence, 'approval-exact-hash.png') })
  await page.getByRole('button', { name: 'Aktifkan', exact: true }).click()
  await page.getByRole('button', { name: 'Konfirmasi', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Jeda', exact: true })).toBeVisible()
  await expect(
    page
      .locator('main .op-table tbody tr')
      .filter({ hasText: 'Cron Terisolasi' })
      .locator('.op-status'),
  ).toHaveAttribute('data-state', 'enabled')
  await page.locator('.op-drawer-body').evaluate((el) => {
    el.scrollTop = 0
  })
  await page.screenshot({ path: resolve(evidence, 'automation-detail.png') })
  await page.getByRole('button', { name: 'Jalankan sekali', exact: true }).click()
  await page.getByRole('button', { name: 'Konfirmasi', exact: true }).click()
  await request.post('/__test__/tick')
  await expect(page.getByRole('dialog').getByRole('link', { name: /^run_/ }).first()).toBeVisible()
  await page.screenshot({ path: resolve(evidence, 'occurrence-history.png') })
  await page.getByRole('dialog').getByRole('link', { name: /^run_/ }).first().click()
  await expect(page.getByRole('link', { name: 'Otomatisasi asal', exact: true })).toBeVisible()
  await axe(page)
})
test('edit keeps owner project, CAS conflict retains values, unsaved exit is guarded', async ({
  page,
}) => {
  await create(page, 'Konfigurasi Revisi', 'daily')
  const original = page.url()
  await approve(page)
  await page.getByRole('link', { name: 'Ubah konfigurasi', exact: true }).click()
  await expect(page.getByRole('main').getByLabel('Proyek', { exact: true })).toBeDisabled()
  await page.getByLabel('Nama otomatisasi', { exact: true }).fill('Perubahan Lokal')
  await page.getByRole('link', { name: 'Kembali', exact: true }).click()
  await expect(
    page.getByRole('heading', { name: 'Ada perubahan belum disimpan', exact: true }),
  ).toBeVisible()
  await page.getByRole('button', { name: 'Tetap mengedit', exact: true }).click()
  await expect(page.getByLabel('Nama otomatisasi', { exact: true })).toHaveValue('Perubahan Lokal')
  const identity = new URL(original).searchParams
  const changed = await page.evaluate(
    async ({ project, id }) => {
      const root = '/api/projects/' + project + '/automations/' + id
      const definition = await fetch(root).then((r) => r.json()),
        session = await fetch('/api/session', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: '{}',
        }).then((r) => r.json())
      return fetch(root, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': session.csrf },
        body: JSON.stringify({
          ...definition.configuration,
          title: 'Revisi Server',
          expected_revision: definition.revision,
        }),
      }).then((r) => r.status)
    },
    { project: identity.get('project'), id: identity.get('automation') },
  )
  expect(changed).toBe(200)
  await page.getByRole('button', { name: 'Lanjutkan', exact: true }).click()
  await page.getByRole('button', { name: 'Periksa jadwal', exact: true }).click()
  await expect(page.locator('.op-preview li')).toHaveCount(5)
  await page.getByRole('button', { name: 'Lanjutkan', exact: true }).click()
  await page.getByRole('button', { name: 'Lanjutkan', exact: true }).click()
  await page.getByRole('button', { name: 'Simpan sebagai Dijeda', exact: true }).click()
  await expect(page.getByRole('alert')).toContainText('Revisi telah berubah')
  await page.getByRole('button', { name: /01 — Target/ }).click()
  await expect(page.getByLabel('Nama otomatisasi', { exact: true })).toHaveValue('Perubahan Lokal')
  await page.getByRole('button', { name: 'Segarkan', exact: true }).click()
  await page.getByRole('button', { name: 'Konfirmasi', exact: true }).click()
  await expect(page.getByLabel('Nama otomatisasi', { exact: true })).toHaveValue('Revisi Server')
  await page.getByRole('link', { name: 'Kembali', exact: true }).click()
  await page.goto(original)
  await expect(page.getByRole('heading', { name: 'Revisi Server', exact: true })).toBeVisible()
})
for (const width of [1440, 768, 390])
  for (const theme of ['dark', 'light'])
    test('Operations responsive ' + width + ' ' + theme, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 })
      await page.addInitScript((value) => localStorage.setItem('aryn.shell.theme', value), theme)
      await page.goto('/runs')
      await expect(page.locator('.op-table tbody tr').first()).toBeVisible()
      expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(
        false,
      )
      await page.screenshot({ path: resolve(evidence, 'runs-' + width + '-' + theme + '.png') })
      await axe(page)
      await page.locator('.op-name').first().click()
      await expect(page.getByRole('dialog')).toBeVisible()
      await page.keyboard.press('Escape')
      await page.goto('/automations/new')
      await expect(page.getByLabel('Nama otomatisasi', { exact: true })).toBeVisible()
      await expect(page.getByLabel('Target', { exact: true }).locator('option')).toHaveCount(2)
      await expect(
        page.getByText('Target belum tersedia dalam proyek ini.', { exact: true }),
      ).toHaveCount(0)
      await page.screenshot({ path: resolve(evidence, 'builder-' + width + '-' + theme + '.png') })
      expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(
        false,
      )
      await axe(page)
    })
test('unknown reconciliation releases only the occurrence hold and preserves Core unknown', async ({
  page,
}) => {
  await page.goto('/automations')
  await page.getByRole('button', { name: /Otomatisasi Observasi/ }).click()
  await page.getByRole('button', { name: 'Occurrence', exact: true }).click()
  const row = page.getByRole('dialog').locator('tbody tr').filter({ hasText: 'Hasil tidak pasti' })
  const run = await row.getByRole('link').getAttribute('href')
  await row.getByRole('button', { name: 'Acknowledgement tanpa retry', exact: true }).click()
  await page
    .getByLabel('Alasan', { exact: true })
    .fill('Acknowledgement only, no Core retry or outcome settlement.')
  await expect(page.getByRole('button', { name: 'Konfirmasi', exact: true })).toBeDisabled()
  await page.getByRole('checkbox').check()
  await page.getByRole('button', { name: 'Konfirmasi', exact: true }).click()
  await expect(page.locator('.op-status[data-state="reconciled"]')).toBeVisible()
  await page.screenshot({ path: resolve(evidence, 'unknown-reconciliation.png') })
  await page.goto(run!)
  await expect(
    page.getByRole('dialog').locator('.op-status[data-state="outcome_unknown"]'),
  ).toBeVisible()
})

for (const kind of ['weekly', 'interval'] as const)
  test(
    'real ' + kind + ' wizard creates paused and filtering stays project scoped',
    async ({ page }) => {
      await create(page, 'Jadwal ' + kind, kind)
      await expect(page.getByRole('button', { name: 'Aktifkan', exact: true })).toBeDisabled()
      await page.keyboard.press('Escape')
      await page.getByLabel('Pemicu', { exact: true }).selectOption(kind)
      await expect(page.locator('.op-name')).toHaveCount(1)
      await page.getByLabel('Cari nama otomatisasi', { exact: true }).fill('%literal%')
      await expect(
        page.getByText('Belum ada otomatisasi yang cocok', { exact: true }),
      ).toBeVisible()
      await page.getByLabel('Cari nama otomatisasi', { exact: true }).fill('')
      await page
        .getByRole('main')
        .getByLabel('Proyek', { exact: true })
        .selectOption({ label: 'Proyek Operasi Kosong' })
      await expect(
        page.getByText('Belum ada otomatisasi yang cocok', { exact: true }),
      ).toBeVisible()
    },
  )

test('workflow automation uses the frozen target and reaches actual human review', async ({
  page,
  request,
}) => {
  await create(page, 'Workflow Otomatisasi', 'interval', 'workflow')
  await approve(page)
  await page.getByRole('button', { name: 'Aktifkan', exact: true }).click()
  await page.getByRole('button', { name: 'Konfirmasi', exact: true }).click()
  await page.getByRole('button', { name: 'Jalankan sekali', exact: true }).click()
  await page.getByRole('button', { name: 'Konfirmasi', exact: true }).click()
  await request.post('/__test__/tick')
  await expect(page.getByRole('dialog').getByRole('link', { name: /^workflow_run_/ })).toBeVisible()
  await page
    .getByRole('dialog')
    .getByRole('link', { name: /^workflow_run_/ })
    .click()
  await expect(page.getByTestId('node-review')).toHaveAttribute('data-state', 'waiting_review')
  await page.screenshot({ path: resolve(evidence, 'automation-workflow-run.png') })
})

test('lost manual response retains its original intent and revision across refresh', async ({
  page,
  request,
}) => {
  await create(page, 'Delivery Terputus', 'daily')
  await approve(page)
  await page.getByRole('button', { name: 'Aktifkan', exact: true }).click()
  await page.getByRole('button', { name: 'Konfirmasi', exact: true }).click()
  let original: unknown
  await page.route('**/automations/*/run', async (route) => {
    original = route.request().postDataJSON()
    await route.fetch()
    await route.abort('failed')
  })
  await page.getByRole('button', { name: 'Jalankan sekali', exact: true }).click()
  await page.getByRole('button', { name: 'Konfirmasi', exact: true }).click()
  await expect(page.getByText(/Penerimaan occurrence belum pasti/)).toBeVisible()
  await page.unroute('**/automations/*/run')
  await request.post('/__test__/tick')
  await page.reload()
  await page.getByRole('button', { name: 'Kirim ulang intent yang sama', exact: true }).click()
  const delivered = page.waitForRequest((r) => r.method() === 'POST' && r.url().endsWith('/run'))
  await page.getByRole('button', { name: 'Konfirmasi', exact: true }).click()
  expect((await delivered).postDataJSON()).toEqual(original)
  await expect(page.getByRole('dialog').locator('tbody tr')).toHaveCount(1)
  await expect(page.getByRole('dialog').locator('.op-status[data-state="completed"]')).toBeVisible()
  await page.screenshot({ path: resolve(evidence, 'manual-response-recovery.png') })
  await page.getByRole('button', { name: 'Konfigurasi', exact: true }).click()
  await page.getByRole('button', { name: 'Jeda', exact: true }).click()
  await page.getByRole('button', { name: 'Konfirmasi', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Aktifkan', exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Jalankan sekali', exact: true })).toHaveCount(0)
})

test('English locale uses actual persisted preference and deep links reject foreign scope', async ({
  page,
}) => {
  await page.evaluate(async () => {
    const workspace = await fetch('/api/workspace/context').then((r) => r.json()),
      session = await fetch('/api/session', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: '{}',
      }).then((r) => r.json())
    await fetch('/api/projects/' + workspace.projects[0].id + '/chat/preferences', {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': session.csrf },
      body: JSON.stringify({ locale: 'en-US' }),
    })
  })
  await page.reload()
  await expect(page.getByRole('heading', { name: 'Runs', exact: true })).toBeVisible()
  await page.screenshot({ path: resolve(evidence, 'runs-english.png') })
  await page.goto('/automations')
  await expect(page.getByRole('heading', { name: 'Automations', exact: true })).toBeVisible()
  await page.getByRole('link', { name: 'Create Automation', exact: true }).click()
  await expect(page.getByLabel('Automation name', { exact: true })).toBeVisible()
  await page.screenshot({ path: resolve(evidence, 'builder-english.png') })
  await page.goto('/runs?project=foreign&run=run_foreign&runKind=agent')
  await expect(page.getByTestId('node-agent')).toHaveCount(0)
  await expect(page.getByRole('dialog')).toBeVisible()
  await expect(page.getByText('Isolated operations completed')).toHaveCount(0)
})
