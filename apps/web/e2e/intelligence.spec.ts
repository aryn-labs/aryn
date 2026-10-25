import { test, expect, type Page } from '@playwright/test'
import AxeBuilder from '@axe-core/playwright'
import { readFile, mkdir } from 'node:fs/promises'
import { resolve } from 'node:path'
const evidence = resolve('../../.local/intelligence-evidence')
let records: Record<string, string>
test.beforeAll(async () => {
  await mkdir(evidence, { recursive: true })
  records = JSON.parse(await readFile(resolve(evidence, 'core-records.json'), 'utf8')) as Record<
    string,
    string
  >
})
test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    if (!localStorage.getItem('aryn.shell.language'))
      localStorage.setItem('aryn.shell.language', 'id-ID')
    if (!localStorage.getItem('aryn.shell.theme')) localStorage.setItem('aryn.shell.theme', 'dark')
  })
  await page.goto('/bench')
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
  await page.reload()
})
async function screenshot(page: Page, name: string) {
  await page.locator('#main-content').evaluate((el) => {
    el.scrollTop = 0
  })
  await page.screenshot({ path: resolve(evidence, name + '.png'), fullPage: true })
}
async function sectionScreenshot(page: Page, heading: string, name: string) {
  await page.getByRole('heading', { name: heading, exact: true }).evaluate((el) => {
    el.scrollIntoView({ block: 'start' })
  })
  await page.screenshot({ path: resolve(evidence, name + '.png'), fullPage: true })
}
async function confirm(page: Page, timeout = 5000) {
  await page
    .getByRole('dialog')
    .getByRole('button', { name: 'Konfirmasi tindakan', exact: true })
    .click()
  await expect(page.getByRole('dialog')).toBeHidden({ timeout })
}
async function axe(page: Page) {
  const result = await new AxeBuilder({ page }).analyze()
  expect(result.violations).toEqual([])
}
test('Bench catalog, persisted scenarios, graders and independent verification', async ({
  page,
}) => {
  await expect(page.locator('.intel-table tbody tr')).toHaveCount(4)
  await expect(page.getByText('Tidak terverifikasi', { exact: true })).toBeVisible()
  await screenshot(page, 'bench-catalog')
  await page.getByLabel('Status', { exact: true }).selectOption('failed')
  await expect(page.locator('.intel-table tbody tr')).toHaveCount(1)
  await page.goto('/bench/' + records.project + '/evaluations/' + records.evaluation)
  await expect(page.getByRole('heading', { name: 'Hasil Skenario', exact: true })).toBeVisible()
  await screenshot(page, 'bench-evaluation-detail')
  await page.locator('.intel-row > summary').first().click()
  await expect(page.getByRole('heading', { name: 'Rincian Grader', exact: true })).toBeVisible()
  await expect(
    page.locator('details[open]').first().getByText('isolated-test', { exact: true }).first(),
  ).toBeVisible()
  await sectionScreenshot(page, 'Rincian Grader', 'bench-graders')
  await axe(page)
})
test('critical regression remains blocked; exact version link selects lifecycle', async ({
  page,
}) => {
  await page.goto('/bench/' + records.project + '/evaluations/' + records.failed_evaluation)
  await expect(page.getByText(/critical/).first()).toBeVisible()
  await page.getByRole('button', { name: 'Perbandingan Baseline', exact: true }).click()
  await expect(
    page.getByRole('heading', { name: 'Perbandingan Baseline', exact: true }),
  ).toBeVisible()
  await screenshot(page, 'bench-baseline-comparison')
  await expect(page.getByRole('button', { name: 'Terima baseline', exact: true })).toBeDisabled()
  await page.goto('/bench/' + records.project + '/evaluations/' + records.evaluation)
  await page.getByRole('link', { name: 'Buka versi persis di Agent Factory', exact: true }).click()
  await expect(page).toHaveURL(new RegExp('version=' + records.version))
  await expect(page.locator('.af-version-detail h3')).toContainText('1.1.0')
})
test('unverified historical pass cannot accept baseline', async ({ page }) => {
  await page.goto('/bench/' + records.project + '/evaluations/' + records.unverified_evaluation)
  await expect(page.getByText('Tidak terverifikasi', { exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Terima baseline', exact: true })).toBeDisabled()
  await expect(page.locator('.intel-summary')).toContainText('4/4')
})
test('server suites and explicit baseline acceptance preserve the exact evaluation', async ({
  page,
}) => {
  await page.getByRole('button', { name: 'Suite', exact: true }).click()
  const suites = await page.request
    .get('/api/projects/' + records.project + '/bench/suites')
    .then((r) => r.json())
  await expect(page.getByRole('heading', { name: suites.items[0].name, exact: true })).toBeVisible()
  await screenshot(page, 'bench-suites')
  await page.goto('/bench/' + records.project + '/evaluations/' + records.evaluation)
  const before = await page.request
    .get('/api/projects/' + records.project + '/bench/evaluations/' + records.evaluation)
    .then((r) => r.json())
  await page.getByRole('button', { name: 'Terima baseline', exact: true }).click()
  await page
    .getByLabel('Alasan review', { exact: true })
    .fill('Explicit isolated human review of this exact current verified evaluation')
  await confirm(page)
  const after = await page.request
    .get('/api/projects/' + records.project + '/bench/evaluations/' + records.evaluation)
    .then((r) => r.json())
  expect(after.baseline.evaluation.evaluation_id).toBe(records.evaluation)
  expect(after.baseline.baseline_id).not.toBe(before.baseline.baseline_id)
  expect(after.version_status).toBe(before.version_status)
})
test('Runs evidence and project links navigate using their actual scoped identities', async ({
  page,
}) => {
  await page.goto('/runs?project=' + records.project + '&run=' + records.run + '&runKind=agent')
  await page.getByRole('link', { name: 'Record Terkait · Brief', exact: true }).click()
  await expect(page).toHaveURL(new RegExp('ref=' + records.run))
  await page.getByRole('link', { name: 'Run completion evidence', exact: true }).click()
  await expect(page).toHaveURL(new RegExp(records.run_bundle!))
  await expect(page.getByText('SUPPORTED', { exact: true }).first()).toBeVisible()
})
test('disposable fixture configuration and signal collection use actual Core revisions', async ({
  page,
}) => {
  await page.goto('/relay')
  await page.getByRole('button', { name: 'Fixture Demo', exact: true }).click()
  await page.getByRole('button', { name: 'Buat Fixture', exact: true }).click()
  await page.getByLabel('Nama', { exact: true }).fill('Browser governed disposable fixture')
  await confirm(page)
  await page.getByRole('button', { name: 'Fixture Demo', exact: true }).click()
  const panel = page.locator('.intel-panel').filter({
    has: page.getByRole('heading', { name: 'Browser governed disposable fixture', exact: true }),
  })
  await panel.getByRole('button', { name: 'Ubah state disposable', exact: true }).click()
  await page.getByRole('dialog').getByLabel('Fault penghambat', { exact: true }).check()
  await confirm(page)
  await panel.getByRole('button', { name: 'Kumpulkan sinyal demo', exact: true }).click()
  await confirm(page)
  await page.getByRole('button', { name: 'Insiden', exact: true }).click()
  await expect(
    page.getByRole('link', { name: /Browser governed disposable fixture/ }),
  ).toBeVisible()
})
test('Brief catalogs, source inspector and actual three-step bundle creation', async ({ page }) => {
  await page.goto('/brief')
  await expect(page.locator('.intel-table tbody tr').first()).toBeVisible()
  await screenshot(page, 'brief-catalog')
  await page.getByRole('button', { name: 'Buat Bundle', exact: true }).click()
  await page.getByLabel('Nama', { exact: true }).fill('Browser Core Evidence Bundle')
  await page.getByRole('dialog').getByRole('button', { name: 'Muat lainnya', exact: true }).click()
  await page.getByLabel(/Dokumen Pengujian Terisolasi/).check()
  await page.getByRole('dialog').getByRole('button', { name: 'Lanjutkan', exact: true }).click()
  await page
    .getByLabel('Pertanyaan', { exact: true })
    .fill('Apakah origin tersimpan memuat audit-pass?')
  await page.getByLabel('Teks literal', { exact: true }).fill('audit-pass')
  await page.getByRole('dialog').getByRole('button', { name: 'Lanjutkan', exact: true }).click()
  await screenshot(page, 'brief-create-wizard')
  await page
    .getByRole('dialog')
    .getByRole('button', { name: 'Simpan melalui Core', exact: true })
    .click()
  await expect(page.getByRole('dialog')).toBeHidden()
  await expect(page.getByRole('heading', { name: 'Browser Core Evidence Bundle' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Matriks Bukti' })).toBeVisible()
  await screenshot(page, 'brief-bundle-detail')
  await screenshot(page, 'brief-evidence-matrix')
  const url = page.url()
  await page.reload()
  await expect(page).toHaveURL(url)
  await expect(page.locator('.intel-excerpt')).toContainText('audit-pass')
  await page.locator('.intel-row a').first().click()
  await expect(page.getByRole('heading', { name: 'Snapshot tersanitasi' })).toBeVisible()
  await screenshot(page, 'brief-source-inspector')
  await axe(page)
})
test('Brief source ingestion persists through Core', async ({ page }) => {
  await page.goto('/brief')
  await page.getByRole('button', { name: 'Tambah Sumber', exact: true }).click()
  await page.getByLabel('Nama', { exact: true }).fill('Browser persisted document')
  await page
    .getByLabel('Teks dokumen', { exact: true })
    .fill('Bounded user evidence; this is not an external factual claim.')
  await confirm(page)
  await page.getByRole('button', { name: 'Sumber', exact: true }).click()
  await expect(
    page.getByRole('link', { name: 'Browser persisted document', exact: true }),
  ).toBeVisible()
})
test('Relay human approval, fixed recovery, causal verification and diagnostic replay', async ({
  page,
}) => {
  await page.goto('/relay')
  await expect(page.locator('.intel-table tbody tr').first()).toBeVisible()
  await screenshot(page, 'relay-catalog')
  await page.goto('/relay/' + records.project + '/' + records.incident)
  await page.getByRole('button', { name: 'Investigasi bukti', exact: true }).click()
  await confirm(page)
  await expect(page.getByRole('heading', { name: 'Matriks Bukti' })).toBeVisible()
  await page.getByRole('button', { name: 'Usulkan tindakan pemulihan', exact: true }).click()
  await page
    .getByLabel('Alasan review')
    .fill('Explicit review of disposable fixture evidence and exact revision')
  await confirm(page)
  await screenshot(page, 'relay-incident-detail')
  await expect(
    page.getByRole('button', { name: 'Jalankan tindakan disetujui', exact: true }),
  ).toBeDisabled()
  await page.getByRole('button', { name: 'Setujui hash persis', exact: true }).click()
  await page
    .getByLabel('Alasan review')
    .fill('Human exact-hash approval of the disposable recovery only')
  await confirm(page)
  await page.getByRole('button', { name: 'Jalankan tindakan disetujui', exact: true }).click()
  await confirm(page)
  await expect(
    page.getByRole('button', { name: 'Tutup insiden terverifikasi', exact: true }),
  ).toBeEnabled()
  await sectionScreenshot(page, 'Verifikasi Kesehatan Independen', 'relay-recovery-verification')
  await page.getByRole('button', { name: 'Tutup insiden terverifikasi', exact: true }).click()
  await confirm(page)
  await page
    .locator('.intel-panel')
    .filter({ has: page.getByRole('heading', { name: 'Capsule Insiden', exact: true }) })
    .getByRole('link')
    .first()
    .click()
  await page.getByRole('button', { name: 'Jalankan replay diagnostik', exact: true }).click()
  await confirm(page)
  await expect(page.getByRole('heading', { name: 'Rincian Grader', exact: true })).toBeVisible()
  await expect(page.getByText('deterministic_in_memory', { exact: true })).toBeVisible()
  await screenshot(page, 'bench-capsule-replay')
  await axe(page)
})
test('degraded and unknown never imply recovery or automatic retry', async ({ page }) => {
  await page.goto('/relay/' + records.project + '/' + records.degraded_incident)
  await expect(
    page.getByRole('button', { name: 'Tutup insiden terverifikasi', exact: true }),
  ).toBeDisabled()
  await expect(page.getByText('DEGRADED', { exact: true }).first()).toBeVisible()
  await page.goto('/relay/' + records.project + '/' + records.unknown_incident)
  await expect(page.getByText(/Outcome unknown. Rekonsiliasi secara eksplisit/)).toBeVisible()
  await expect(
    page.getByRole('button', { name: 'Jalankan tindakan disetujui', exact: true }),
  ).toBeDisabled()
  await screenshot(page, 'relay-outcome-unknown')
  await page.getByRole('button', { name: 'Rekonsiliasi outcome unknown', exact: true }).click()
  await confirm(page)
  await expect(
    page.getByRole('button', { name: 'Tutup insiden terverifikasi', exact: true }),
  ).toBeEnabled()
})
test('project filters and denied cross-project deep links hide private data', async ({ page }) => {
  await page.goto('/brief')
  await page
    .getByRole('combobox', { name: 'Proyek', exact: true })
    .selectOption('proj_intelligence_empty')
  await expect(page.getByText('Belum ada record', { exact: true })).toBeVisible()
  await page.goto('/brief/proj_intelligence_empty/' + records.bundle)
  await expect(page.locator('.data-state')).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Isolated audit-pass', exact: true })).toBeHidden()
})
test('dialogs trap focus, Escape restores trigger and block empty submission', async ({ page }) => {
  await page.goto('/brief')
  const button = page.getByRole('button', { name: 'Buat Bundle', exact: true })
  await button.click()
  await expect(
    page.getByRole('dialog').getByRole('button', { name: 'Lanjutkan', exact: true }),
  ).toBeDisabled()
  await page.keyboard.press('Escape')
  await expect(page.getByRole('dialog')).toBeHidden()
  await expect(button).toBeFocused()
})
for (const module of ['bench', 'relay', 'brief'])
  test('mobile ' + module + ' stays within the dashboard viewport', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 })
    await page.goto('/' + module)
    await expect(page.locator('.intel-table tbody tr').first()).toBeVisible()
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    await screenshot(page, module + '-mobile')
    await page.locator('.intel-table').scrollIntoViewIfNeeded()
    await page.screenshot({
      path: resolve(evidence, module + '-mobile-records.png'),
      fullPage: true,
    })
    await axe(page)
  })
test('light theme and English localization use the same Core records', async ({ page }) => {
  await page.evaluate(async () => {
    localStorage.setItem('aryn.shell.theme', 'light')
    localStorage.setItem('aryn.shell.language', 'en-US')
    const session = await fetch('/api/session', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: '{}',
    }).then((r) => r.json())
    const workspace = await fetch('/api/workspace/context').then((r) => r.json())
    await fetch('/api/projects/' + workspace.projects[0].id + '/chat/preferences', {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': session.csrf },
      body: JSON.stringify({ locale: 'en-US' }),
    })
  })
  await page.reload()
  await expect(page.getByRole('button', { name: 'Evaluations', exact: true })).toBeVisible()
  await expect(page.locator('html')).not.toHaveClass(/dark/)
  await screenshot(page, 'bench-light-english')
  await axe(page)
  for (const module of ['relay', 'brief']) {
    await page.goto('/' + module)
    await expect(page.locator('.intel-table tbody tr').first()).toBeVisible()
    await screenshot(page, module + '-light-english')
    await axe(page)
  }
})

test('operator-approved physical file connection captures evidence and supports revocation', async ({
  page,
}) => {
  await page.goto('/brief')
  await page.getByRole('button', { name: 'Koneksi sumber', exact: true }).click()
  await page.getByRole('button', { name: 'Registrasi koneksi sumber', exact: true }).click()
  await page
    .getByLabel('Koneksi yang disetujui operator', { exact: true })
    .selectOption('browser_runbooks')
  await page
    .getByRole('dialog')
    .getByLabel('Nama', { exact: true })
    .fill('Browser physical runbook')
  await axe(page)
  await confirm(page)
  const panel = page
    .locator('.intel-panel')
    .filter({ has: page.getByRole('heading', { name: 'Browser physical runbook', exact: true }) })
  await panel.getByRole('button', { name: 'Kumpulkan snapshot sumber', exact: true }).click()
  await page.getByLabel('File yang disetujui', { exact: true }).selectOption('runbook')
  await page.getByRole('dialog').getByLabel('Nama', { exact: true }).fill('Actual runbook snapshot')
  await confirm(page)
  const sources = await page.request
    .get('/api/projects/' + records.project + '/brief/sources')
    .then((r) => r.json())
  const source = sources.items.find(
    (item: { title: string }) => item.title === 'Actual runbook snapshot',
  )
  expect(source.source_ref.kind).toBe('file')
  await panel.getByRole('button', { name: 'Cabut akses', exact: true }).click()
  await confirm(page)
  await expect(
    panel.getByRole('button', { name: 'Kumpulkan snapshot sumber', exact: true }),
  ).toBeDisabled()
  await screenshot(page, 'brief-real-file-connection')
})

test('safe suite authoring and exact human review expose an immutable Factory choice', async ({
  page,
}) => {
  await page.getByRole('button', { name: 'Suite', exact: true }).click()
  await page.getByRole('button', { name: 'Buat versi suite', exact: true }).click()
  const dialog = page.getByRole('dialog')
  await dialog
    .getByLabel('Keluarga suite', { exact: true })
    .fill('browser_operational_observations')
  await dialog.getByLabel('Nama', { exact: true }).fill('Browser reviewed observation suite')
  await dialog.getByLabel('Versi evaluasi', { exact: true }).fill('1.0.0')
  await dialog.getByLabel('Nama skenario', { exact: true }).fill('Observed liquidity')
  await dialog
    .getByLabel('Instruksi skenario', { exact: true })
    .fill('Explain liquidity and solvency using their time horizons.')
  await dialog.getByLabel('Observasi literal wajib', { exact: true }).fill('Liquidity')
  await axe(page)
  await confirm(page)
  const panel = page.locator('.intel-panel').filter({
    has: page.getByRole('heading', { name: 'Browser reviewed observation suite', exact: true }),
  })
  await panel.getByRole('button', { name: 'Review suite', exact: true }).click()
  await page
    .getByRole('dialog')
    .getByLabel('Alasan review', { exact: true })
    .fill('Human review of the exact immutable declaration and mandatory security checks.')
  await confirm(page)
  const catalog = await page.request
    .get('/api/projects/' + records.project + '/bench/suites')
    .then((r) => r.json())
  expect(
    catalog.items.some(
      (item: { name: string }) => item.name === 'Browser reviewed observation suite',
    ),
  ).toBe(true)
  await screenshot(page, 'bench-reviewed-suite-authoring')
})

test('Core-governed operational protocol executes once and captures verification lineage', async ({
  page,
}) => {
  await page.goto('/relay/' + records.project + '/' + records.operational_incident)
  await page.getByRole('button', { name: 'Investigasi bukti', exact: true }).click()
  await confirm(page, 30000)
  await page.getByRole('button', { name: 'Usulkan tindakan pemulihan', exact: true }).click()
  await page
    .getByRole('dialog')
    .getByLabel('Alasan review', { exact: true })
    .fill(
      'Start only the exact stopped isolated process and independently verify its business endpoint.',
    )
  await confirm(page, 30000)
  await expect(
    page.getByRole('button', { name: 'Jalankan tindakan disetujui', exact: true }),
  ).toBeDisabled()
  await page.getByRole('button', { name: 'Setujui hash persis', exact: true }).click()
  await page
    .getByRole('dialog')
    .getByLabel('Alasan review', { exact: true })
    .fill('Review exact target, action, deadline, isolation and independent health verification.')
  await confirm(page, 30000)
  await page.getByRole('button', { name: 'Jalankan tindakan disetujui', exact: true }).click()
  await confirm(page, 30000)
  await expect(page.getByText('RECOVERED', { exact: true }).first()).toBeVisible()
  await page.getByText('Receipt eksekusi', { exact: true }).click()
  await expect(page.locator('details[open]')).toContainText('admission_hash')
  await page.getByRole('button', { name: 'Tutup insiden terverifikasi', exact: true }).click()
  await confirm(page, 30000)
  const result = await page.request
    .get('/api/projects/' + records.project + '/relay/' + records.operational_incident)
    .then((r) => r.json())
  expect(result.capsule.lineage.verification_observation.payload.healthy).toBe(true)
  await page.goto('/bench/' + records.project + '/capsules/' + result.capsule_id)
  await page.getByText('Bukti historis terautentikasi', { exact: true }).click()
  await expect(page.locator('details[open]')).toContainText('verification_observation')
  await axe(page)
  await screenshot(page, 'operational-capsule-lineage')
})

test('Brief interpretation requires consent and remains a separate informational Core run', async ({
  page,
}) => {
  await page.goto('/brief/' + records.project + '/' + records.bundle)
  await page
    .getByRole('button', { name: 'Interpretasi bukti dengan agen assigned', exact: true })
    .click()
  const dialog = page.getByRole('dialog')
  await dialog.getByRole('combobox').selectOption(records.assignment!)
  await expect(
    dialog.getByRole('button', { name: 'Konfirmasi tindakan', exact: true }),
  ).toBeDisabled()
  await dialog.getByRole('checkbox').check()
  await axe(page)
  await confirm(page)
  await expect(
    page.getByText('Interpretasi model · hanya informasi', { exact: true }),
  ).toBeVisible()
  const captured = await page.request
    .get('/api/projects/' + records.project + '/brief/' + records.bundle + '/interpretations')
    .then((r) => r.json())
  expect(captured.items[0].authority).toBe('informational_only')
  await screenshot(page, 'brief-informational-core-interpretation')
})

test('approved Git connection preserves an exact real commit and an accessible revision field', async ({
  page,
}) => {
  await page.goto('/brief')
  await page.getByRole('button', { name: 'Koneksi sumber', exact: true }).click()
  await page.getByRole('button', { name: 'Registrasi koneksi sumber', exact: true }).click()
  await page
    .getByLabel('Koneksi yang disetujui operator', { exact: true })
    .selectOption('browser_source_history')
  await page
    .getByRole('dialog')
    .getByLabel('Nama', { exact: true })
    .fill('Browser exact Git source')
  await confirm(page)
  const panel = page
    .locator('.intel-panel')
    .filter({ has: page.getByRole('heading', { name: 'Browser exact Git source', exact: true }) })
  await panel.getByRole('button', { name: 'Kumpulkan snapshot sumber', exact: true }).click()
  await page.getByLabel('File yang disetujui', { exact: true }).selectOption('readme')
  await page
    .getByRole('dialog')
    .getByLabel('Nama', { exact: true })
    .fill('Actual Git commit snapshot')
  await page.getByLabel('Revisi Git yang tepat', { exact: true }).fill(records.git_revision!)
  await axe(page)
  await confirm(page)
  const sources = await page.request
    .get('/api/projects/' + records.project + '/brief/sources')
    .then((r) => r.json())
  const source = sources.items.find(
    (item: { title: string }) => item.title === 'Actual Git commit snapshot',
  )
  expect(source.source_ref.kind).toBe('git')
  const captured = await page.request
    .get('/api/projects/' + records.project + '/brief/sources/' + source.id)
    .then((r) => r.json())
  expect(captured.content.revision).toBe(records.git_revision)
  expect(captured.content.current_revision).toBe(records.git_revision)
  await screenshot(page, 'brief-real-git-connection')
})
