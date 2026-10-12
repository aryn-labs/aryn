import { expect, test, type Page } from '@playwright/test'
import AxeBuilder from '@axe-core/playwright'
import { mkdir, writeFile } from 'node:fs/promises'
import { resolve } from 'node:path'
const evidence = resolve('../../.local/workflow-builder-evidence')
test.beforeAll(async () => {
  await mkdir(evidence, { recursive: true })
})
test.beforeEach(async ({ context, page }) => {
  await context.addInitScript(() => {
    if (!localStorage.getItem('aryn.shell.theme')) localStorage.setItem('aryn.shell.theme', 'dark')
    if (!localStorage.getItem('aryn.shell.language'))
      localStorage.setItem('aryn.shell.language', 'id-ID')
  })
  // Personal locale lives in the actual API. Isolate it between browser cases.
  await page.goto('/workflows')
  await page.evaluate(async () => {
    const session = await fetch('/api/session', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: '{}',
    }).then((r) => r.json())
    const workspace = await fetch('/api/workspace/context').then((r) => r.json())
    const response = await fetch(`/api/projects/${workspace.projects[0].id}/chat/preferences`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': session.csrf },
      body: JSON.stringify({ locale: 'id-ID' }),
    })
    if (!response.ok) throw new Error('Isolated locale setup failed')
  })
})
test.afterEach(async ({ request }) => {
  await request.post('/__test__/runtime-gate', { data: { hold: false } })
})
async function create(page: Page, name: string) {
  await page.goto('/workflows')
  await page.getByRole('button', { name: 'Buat Alur Kerja', exact: true }).first().click()
  await page.getByRole('dialog').getByLabel('Nama alur kerja', { exact: true }).fill(name)
  await page
    .getByRole('dialog')
    .getByRole('button', { name: 'Buat Alur Kerja', exact: true })
    .click()
  await expect(page.getByTestId('node-agent')).toBeVisible()
}
async function configure(page: Page) {
  await page.getByLabel('Assignment agen', { exact: true }).selectOption({ index: 1 })
  await page.getByRole('button', { name: 'Simpan Draft', exact: true }).click()
  await expect(page.getByText('Tersimpan', { exact: true }).first()).toBeVisible()
  await page.getByRole('button', { name: 'Validasi graph', exact: true }).click()
  await expect(page.getByText('Graph dan referensi agent valid menurut Core.')).toBeVisible()
  await page.locator('#studio-versions').click()
  await page.getByRole('button', { name: 'Buat Versi', exact: true }).click()
  await expect(page.getByText(/Melihat graph versi immutable/)).toBeVisible()
}
async function accessible(page: Page) {
  // Opaque, script-denied artifact frames cannot receive axe's injected script.
  // Keep every parent-page rule and verify preview isolation/semantics separately.
  const frames = page.locator('iframe')
  for (let i = 0; i < (await frames.count()); i++) {
    await expect(frames.nth(i)).toHaveAttribute('sandbox', '')
    await expect(frames.nth(i)).toHaveAttribute('title', /\S+/)
    await expect(frames.nth(i)).toHaveCSS('color-scheme', 'light')
    const frame = page.frameLocator('iframe').nth(i)
    await expect(frame.locator('main')).toHaveCount(1)
    await expect(frame.getByRole('heading', { level: 1 })).toBeVisible()
    await expect(frame.locator('script, form, a[href], img, iframe, object, embed')).toHaveCount(0)
  }
  // AxeBuilder recursively injects into frames before applying `iframes: false`.
  // Exclude only these isolated frame subtrees; their title/semantics are checked above.
  const result = await new AxeBuilder({ page }).exclude('iframe').analyze()
  expect(result.violations).toEqual([])
}

test('catalog, creation, agent pin, async Core dispatch, artifact, exact review and refresh', async ({
  page,
  request,
}) => {
  test.setTimeout(120_000)
  await page.setViewportSize({ width: 1600, height: 1000 })
  await page.goto('/workflows')
  await expect(
    page.getByRole('heading', { name: 'Belum ada alur kerja', exact: true }),
  ).toBeVisible()
  await page.screenshot({ path: resolve(evidence, 'catalog-empty.png') })
  await create(page, 'Orkestrasi Terisolasi')
  await expect(page.getByRole('navigation', { name: 'Navigasi utama' })).toHaveCount(0)
  await expect(page.locator('.topbar')).toHaveCount(0)
  await page.screenshot({ path: resolve(evidence, 'studio-desktop.png') })
  await expect(page.locator('.wf-issues')).toContainText('Graph perlu diperbaiki')
  await page.screenshot({ path: resolve(evidence, 'invalid-graph.png') })
  await page.getByLabel('Assignment agen', { exact: true }).selectOption({ index: 1 })
  await page.screenshot({ path: resolve(evidence, 'agent-inspector.png') })
  await configure(page)
  await request.post('/__test__/runtime-gate', { data: { hold: true } })
  await page.getByRole('button', { name: 'Jalankan', exact: true }).first().click()
  await page
    .getByLabel('Input alur kerja', { exact: true })
    .fill('Permintaan pengujian workflow terisolasi melalui Core.')
  await page.getByRole('checkbox', { name: /Saya mengizinkan input diproses/ }).check()
  await page.locator('.wf-panel').getByRole('button', { name: 'Jalankan', exact: true }).click()
  await expect(page.getByTestId('node-agent')).toHaveAttribute('data-state', 'running')
  await expect(page.getByTestId('node-start')).toHaveAttribute('data-state', 'completed')
  await expect(page.getByTestId('node-review')).toHaveAttribute('data-state', 'pending')
  await page.screenshot({ path: resolve(evidence, 'execution-running.png') })
  await request.post('/__test__/runtime-gate', { data: { hold: false } })
  await expect(page.getByTestId('node-review')).toHaveAttribute('data-state', 'waiting_review')
  await expect(page.getByTestId('node-end')).toHaveAttribute('data-state', 'pending')
  await expect(
    page.locator('.wf-inspector-result').getByText('test/model-a', { exact: true }),
  ).toBeVisible()
  await page.screenshot({ path: resolve(evidence, 'waiting-review.png') })
  await page.screenshot({ path: resolve(evidence, 'artifact-preview.png') })
  const workflowUrl = page.url(),
    parts = new URL(workflowUrl).pathname.split('/'),
    project = parts[2]!,
    workflow = parts[3]!
  const stored = await page.evaluate(
    ({ project, workflow }) =>
      fetch(`/api/projects/${project}/workflows/${workflow}/runs`).then((r) => r.json()),
    { project, workflow },
  )
  const run = await page.evaluate(
    ({ project, id }) =>
      fetch(`/api/projects/${project}/workflow-runs/${id}`).then((r) => r.json()),
    { project, id: stored.items[0].id },
  )
  expect(run.traversed_edges).toEqual(['edge_0', 'edge_1'])
  await writeFile(
    resolve(evidence, 'core-checkpoint-waiting.json'),
    JSON.stringify(
      {
        fixture: 'isolated runtime; actual API/Core/storage; safe checkpoint projection',
        id: run.id,
        workflow_id: run.workflow_id,
        version_id: run.version_id,
        organization_id: run.organization_id,
        project_id: run.project_id,
        graph_digest: run.graph_digest,
        status: run.status,
        cursor: run.cursor,
        tasks: run.tasks,
        traversed_edges: run.traversed_edges,
      },
      null,
      2,
    ),
  )
  await page
    .getByLabel('Alasan keputusan', { exact: true })
    .fill('Artifact dan digest diperiksa pada pengujian terisolasi.')
  await page.getByRole('button', { name: 'Terima hasil', exact: true }).click()
  await page.getByRole('dialog').getByRole('button', { name: 'Terima hasil', exact: true }).click()
  await expect(page.getByTestId('node-end')).toHaveAttribute('data-state', 'completed')
  await expect(page.getByText('Bukti keputusan', { exact: true })).toBeVisible()
  await page.screenshot({ path: resolve(evidence, 'execution-completed.png') })
  const download = page.waitForEvent('download')
  await page.getByRole('link', { name: 'Unduh artifact' }).click()
  expect((await download).suggestedFilename()).toMatch(/^artifact_.*\.json$/)
  await page.reload()
  await expect(page.getByTestId('node-end')).toHaveAttribute('data-state', 'completed')
  await accessible(page)
  await page.getByRole('link', { name: 'Alur Kerja', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Alur Kerja', exact: true })).toBeVisible()
  await page.getByLabel('Cari alur kerja…').fill('Orkestrasi Terisolasi')
  await expect(page.locator('.af-catalog-card')).toHaveCount(1)
  await page.screenshot({ path: resolve(evidence, 'catalog-desktop.png') })
  await page.goto(`/projects/${project}/work?selection=workflow-run:${run.id}`)
  await expect(page.getByRole('dialog')).toBeVisible()
  const studioLink = page
    .getByRole('dialog')
    .getByRole('link', { name: 'Buka Workflow Studio', exact: true })
  await expect(studioLink).toHaveAttribute(
    'href',
    `/workflows/${project}/${workflow}?run=${run.id}`,
  )
  await studioLink.click()
  await expect(page.getByTestId('node-end')).toHaveAttribute('data-state', 'completed')
  await expect(page.getByText('Bukti keputusan', { exact: true })).toBeVisible()
})

test('floating library, drag, typed ports, undo, draft refresh and CAS conflict', async ({
  page,
}) => {
  await page.setViewportSize({ width: 1600, height: 1000 })
  await create(page, 'Draft Interaksi')
  await page.locator('#studio-add-node').click()
  await page.screenshot({ path: resolve(evidence, 'node-library-all.png') })
  await page.getByPlaceholder('Cari node…').fill('Condition')
  await page.screenshot({ path: resolve(evidence, 'node-library.png') })
  await page.locator('.af-library-node').filter({ hasText: 'Condition' }).click()
  const condition = page.locator('[data-testid^="node-condition_"]')
  await expect(condition).toHaveCount(1)
  await page.getByLabel('Operator kondisi').selectOption('contains')
  await page.getByLabel('Nilai pembanding').fill('likuiditas')
  await page.screenshot({ path: resolve(evidence, 'condition-inspector.png') })
  const id = (await condition.getAttribute('data-testid'))!.replace('node-', '')
  await page.getByRole('button', { name: 'Hubungkan start value out', exact: true }).press('Enter')
  await page.getByRole('button', { name: `Hubungkan ${id} value in`, exact: true }).press('Enter')
  await expect(page.locator('.wf-issues')).toContainText(
    'Setiap port keluaran harus mempunyai tepat satu koneksi.',
  )
  await page.getByRole('button', { name: `Hubungkan ${id} yes out`, exact: true }).press('Enter')
  await page.getByRole('button', { name: 'Hubungkan agent value in', exact: true }).press('Enter')
  await expect(page.getByTestId(`edge-${id}-agent`)).toHaveCount(1)
  await page.getByRole('button', { name: `Hubungkan ${id} no out`, exact: true }).press('Enter')
  await page.getByRole('button', { name: 'Hubungkan review value in', exact: true }).press('Enter')
  await expect(page.getByTestId(`edge-${id}-review`)).toHaveCount(1)
  await page.keyboard.press('Escape')
  const box = await condition.locator('.af-node-head').boundingBox()
  await page.mouse.move(box!.x + 80, box!.y + 20)
  await page.mouse.down()
  await page.mouse.move(box!.x + 150, box!.y + 55, { steps: 5 })
  await page.mouse.up()
  await page.getByRole('button', { name: 'Urungkan', exact: true }).click()
  await page.getByRole('button', { name: 'Ulangi', exact: true }).click()
  await page.getByRole('button', { name: 'Simpan Draft', exact: true }).click()
  await expect(page.getByText('Tersimpan', { exact: true }).first()).toBeVisible()
  await page.reload()
  await expect(page.locator(`[data-testid="node-${id}"]`)).toBeVisible()
  const other = await page.context().newPage()
  await other.goto(page.url())
  await expect(other.getByTestId('node-agent')).toBeVisible()
  await page.getByLabel('Nama alur kerja', { exact: true }).fill('Revisi A')
  await page.getByRole('button', { name: 'Simpan Draft', exact: true }).click()
  await expect(page.getByText('Tersimpan', { exact: true }).first()).toBeVisible()
  await other.getByLabel('Nama alur kerja', { exact: true }).fill('Revisi B lokal')
  await other.getByRole('button', { name: 'Simpan Draft', exact: true }).click()
  await expect(other.getByText(/Revisi berubah di sesi lain/)).toBeVisible()
  await expect(other.getByLabel('Nama alur kerja', { exact: true })).toHaveValue('Revisi B lokal')
  await other.getByRole('button', { name: 'Muat versi server', exact: true }).click()
  await expect(other.getByLabel('Nama alur kerja', { exact: true })).toHaveValue('Revisi A')
  await other.close()
})

test('unsaved navigation retains edits and project ownership is immutable', async ({ page }) => {
  await create(page, 'Ownership Draft')
  await page.getByLabel('Nama alur kerja', { exact: true }).fill('Nama belum disimpan')
  await page.getByRole('link', { name: 'Alur Kerja', exact: true }).click()
  await expect(
    page.getByRole('dialog', { name: 'Ada perubahan yang belum disimpan' }),
  ).toBeVisible()
  await page.getByRole('button', { name: 'Tetap di editor' }).click()
  await expect(page.getByLabel('Nama alur kerja', { exact: true })).toHaveValue(
    'Nama belum disimpan',
  )
  await page.getByRole('link', { name: 'Alur Kerja', exact: true }).click()
  await page.getByRole('button', { name: 'Keluar tanpa menyimpan' }).click()
  await page
    .getByLabel('Proyek pemilik', { exact: true })
    .selectOption({ label: 'Proyek Workflow Kosong' })
  await expect(page.getByRole('heading', { name: 'Belum ada alur kerja' })).toBeVisible()
})

for (const width of [1440, 768, 390])
  for (const theme of ['dark', 'light'])
    test(`Workflow Studio ${width}px ${theme}: accessible responsive panels`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 })
      await page.addInitScript((value) => localStorage.setItem('aryn.shell.theme', value), theme)
      await create(page, `Responsif ${width} ${theme}`)
      await expect(page.locator('.af-board')).toBeVisible()
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(
        true,
      )
      await page.screenshot({ path: resolve(evidence, `studio-${width}-${theme}.png`) })
      if (width <= 900) {
        await page.getByRole('button', { name: 'Pilih Agent', exact: true }).click()
        await expect(page.getByRole('dialog', { name: 'Konfigurasi' })).toBeVisible()
        await page.keyboard.press('Tab')
        expect(
          await page
            .locator('#studio-inspector')
            .evaluate((el) => el.contains(document.activeElement)),
        ).toBe(true)
        await accessible(page)
        await page.screenshot({ path: resolve(evidence, `inspector-${width}-${theme}.png`) })
        await page.keyboard.press('Escape')
      } else await accessible(page)
      await page.locator('#studio-add-node').click()
      await expect(page.getByRole('dialog', { name: 'Node Library' })).toBeVisible()
      await page.keyboard.press('Escape')
      await expect(page.locator('#studio-add-node')).toBeFocused()
    })

test('English labels use the same Studio and genuine empty project data', async ({ page }) => {
  await page.goto('/settings')
  await page.getByLabel('Bahasa', { exact: true }).selectOption('en-US')
  await expect(page.getByLabel('Language', { exact: true })).toHaveValue('en-US')
  await page.goto('/workflows')
  await expect(page.getByRole('heading', { name: 'Workflows', exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Create Workflow', exact: true }).first().click()
  await page.getByRole('dialog').getByLabel('Workflow name').fill('English Workflow')
  await page
    .getByRole('dialog')
    .getByRole('button', { name: 'Create Workflow', exact: true })
    .click()
  await expect(page.getByRole('application', { name: 'Workflow Canvas' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Save Draft', exact: true })).toBeVisible()
  await page.screenshot({ path: resolve(evidence, 'studio-english.png') })
  await accessible(page)
})

test('a lost admission response retains the exact request across refresh without duplicate execution', async ({
  page,
}) => {
  await create(page, 'Idempotency Transport')
  await configure(page)
  const workflowPath = new URL(page.url()).pathname
  await page.getByRole('button', { name: 'Jalankan', exact: true }).first().click()
  await page
    .getByLabel('Input alur kerja', { exact: true })
    .fill('Permintaan identik untuk pengujian respons hilang.')
  await page.getByRole('checkbox', { name: /Saya mengizinkan input diproses/ }).check()
  let dropped = false
  await page.route('**/workflows/*/runs', async (route) => {
    if (route.request().method() !== 'POST' || dropped) return route.continue()
    dropped = true
    const response = await route.fetch()
    expect(response.status()).toBe(202)
    await route.abort('failed')
  })
  await page.locator('.wf-panel').getByRole('button', { name: 'Jalankan', exact: true }).click()
  await expect(page.getByText(/Penerimaan permintaan belum dapat dipastikan/)).toBeVisible()
  const before = await page.evaluate(
    () =>
      Object.entries(sessionStorage).find(([key]) => key.startsWith('aryn-workflow-request:'))?.[1],
  )
  expect(before).toBeTruthy()
  await page.reload()
  await page.getByRole('button', { name: 'Jalankan', exact: true }).first().click()
  await expect(page.getByLabel('Input alur kerja', { exact: true })).toHaveValue(
    'Permintaan identik untuk pengujian respons hilang.',
  )
  await page
    .getByRole('button', { name: 'Periksa / kirim ulang permintaan yang sama', exact: true })
    .click()
  await expect(page.getByTestId('node-review')).toHaveAttribute('data-state', 'waiting_review')
  const admitted = await page.evaluate((path) => {
    const [, , project, workflow] = path.split('/')
    return fetch(`/api/projects/${project}/workflows/${workflow}/runs`).then((r) => r.json())
  }, workflowPath)
  expect(admitted.items).toHaveLength(1)
})

test('authorized stop at review records cancellation and preserves the actual artifact', async ({
  page,
}) => {
  await create(page, 'Cancellation Review')
  await configure(page)
  await page.getByRole('button', { name: 'Jalankan', exact: true }).first().click()
  await page
    .getByLabel('Input alur kerja', { exact: true })
    .fill('Pengujian penghentian saat human review.')
  await page.getByRole('checkbox', { name: /Saya mengizinkan input diproses/ }).check()
  await page.locator('.wf-panel').getByRole('button', { name: 'Jalankan', exact: true }).click()
  await expect(page.getByTestId('node-review')).toHaveAttribute('data-state', 'waiting_review')
  await page.getByRole('button', { name: 'Hentikan eksekusi', exact: true }).click()
  await page
    .getByRole('dialog')
    .getByRole('button', { name: 'Hentikan eksekusi', exact: true })
    .click()
  await expect(page.getByTestId('node-review')).toHaveAttribute('data-state', 'cancelled')
  await expect(page.getByTestId('node-end')).toHaveAttribute('data-state', 'cancelled')
  await expect(page.getByRole('link', { name: 'Unduh artifact' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Terima hasil', exact: true })).toHaveCount(0)
})

for (const selectedYes of [true, false])
  test(`two governed agents, ${selectedYes ? 'yes' : 'no'} branch, inert renderer and rejected review`, async ({
    page,
  }) => {
    test.setTimeout(120_000)
    await page.setViewportSize({ width: 1600, height: 1000 })
    await create(page, 'Multi Agen ' + selectedYes)
    const segments = new URL(page.url()).pathname.split('/'),
      project = segments[2]!,
      workflow = segments[3]!
    const seeded = await page.evaluate(
      async ({ project, workflow, selectedYes }) => {
        const root = `/api/projects/${project}`,
          session = await fetch('/api/session', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: '{}',
          }).then((r) => r.json())
        const lifecycle = await fetch(root + '/lifecycle?limit=50').then((r) => r.json())
        const assignments = lifecycle.assignments.filter(
          (a: { status: string; activation_verified: boolean }) =>
            a.status === 'active' && a.activation_verified,
        )
        if (assignments.length < 2) throw new Error('Governed test fixtures missing')
        const n = (id: string, kind: string, input = 'text', output = input, extra = {}) => ({
          id,
          label: id,
          kind,
          input_schema: input,
          output_schema: output,
          assignment_id: null,
          agent_version_id: null,
          renderer: null,
          predicate: null,
          ...extra,
        })
        const nodes = [
          n('start', 'start'),
          n('research', 'agent', 'text', 'brief', {
            assignment_id: assignments[0].id,
            agent_version_id: assignments[0].version_id,
          }),
          n('branch', 'condition', 'brief', 'brief', {
            predicate: {
              operator: 'contains',
              literal: selectedYes ? 'Likuiditas' : 'no-match-in-isolated-output',
            },
          }),
          n('yes_step', 'handoff', 'brief'),
          n('no_step', 'handoff', 'brief'),
          n('writer', 'agent', 'brief', 'content', {
            assignment_id: assignments[1].id,
            agent_version_id: assignments[1].version_id,
          }),
          n('document', 'agent', 'content', 'website', { renderer: 'static-document-v1' }),
          n('review', 'review', 'website'),
          n('end', 'end', 'website'),
        ]
        const links = [
          ['start', 'research', 'value'],
          ['research', 'branch', 'value'],
          ['branch', 'yes_step', 'yes'],
          ['branch', 'no_step', 'no'],
          ['yes_step', 'writer', 'value'],
          ['no_step', 'writer', 'value'],
          ['writer', 'document', 'value'],
          ['document', 'review', 'value'],
          ['review', 'end', 'value'],
        ]
        const edges = links.map(([source, target, source_port], index) => ({
          id: 'edge_' + index,
          source,
          target,
          source_port,
          target_port: 'value',
        }))
        const definition = await fetch(root + '/workflows/' + workflow).then((r) => r.json())
        const saved = await fetch(root + '/workflows/' + workflow, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': session.csrf },
          body: JSON.stringify({
            name: definition.name,
            expected_revision: definition.revision,
            graph: { nodes, edges },
            positions: nodes.map((node, index) => ({
              id: node.id,
              x: 40 + index * 270,
              y: index === 4 ? 420 : 220,
            })),
          }),
        })
        return { status: saved.status }
      },
      { project, workflow, selectedYes },
    )
    expect(seeded.status).toBe(200)
    await page.reload()
    await expect(page.getByTestId('node-research')).toBeVisible()
    await page.locator('#studio-versions').click()
    await page.getByRole('button', { name: 'Buat Versi', exact: true }).click()
    await expect(page.getByText(/Melihat graph versi immutable/)).toBeVisible()
    await page.getByRole('button', { name: 'Pusatkan canvas', exact: true }).click()
    await page.getByRole('button', { name: 'Jalankan', exact: true }).first().click()
    await page
      .getByLabel('Input alur kerja', { exact: true })
      .fill('Pengujian multi-agent terisolasi.')
    await page.getByRole('checkbox', { name: /Saya mengizinkan input diproses/ }).check()
    await page.locator('.wf-panel').getByRole('button', { name: 'Jalankan', exact: true }).click()
    await expect(page.getByTestId('node-review')).toHaveAttribute('data-state', 'waiting_review')
    await expect(page.getByTestId('node-research')).toHaveAttribute('data-state', 'completed')
    await expect(page.getByTestId('node-writer')).toHaveAttribute('data-state', 'completed')
    await expect(page.getByTestId('node-document')).toHaveAttribute('data-state', 'completed')
    await expect(page.getByTestId(selectedYes ? 'node-no_step' : 'node-yes_step')).toHaveAttribute(
      'data-state',
      'skipped',
    )
    await expect(
      page.getByTestId(selectedYes ? 'edge-branch-no_step' : 'edge-branch-yes_step'),
    ).toHaveAttribute('data-state', 'idle')
    await expect(page.locator('iframe[title="Preview aman"]')).toHaveAttribute('sandbox', '')
    await expect(page.frameLocator('iframe[title="Preview aman"]').locator('body')).toContainText(
      '[PENGUJIAN TERISOLASI]',
    )
    await page.screenshot({
      path: resolve(evidence, `multi-agent-${selectedYes ? 'yes' : 'no'}-html.png`),
    })
    await page.locator('iframe[title="Preview aman"]').scrollIntoViewIfNeeded()
    const previewHeading = page
      .frameLocator('iframe[title="Preview aman"]')
      .getByRole('heading', { level: 1 })
    await expect(previewHeading).toBeVisible()
    await expect(previewHeading).toHaveCSS('color', 'rgb(0, 0, 0)')
    await previewHeading.screenshot({
      path: resolve(evidence, `artifact-heading-${selectedYes ? 'yes' : 'no'}.png`),
    })
    await page.screenshot({
      path: resolve(evidence, `artifact-html-${selectedYes ? 'yes' : 'no'}.png`),
    })
    await page
      .getByLabel('Alasan keputusan', { exact: true })
      .fill('Keputusan penolakan terisolasi untuk memverifikasi terminal state.')
    await page.getByRole('button', { name: 'Tolak hasil', exact: true }).click()
    await page.getByRole('dialog').getByRole('button', { name: 'Tolak hasil', exact: true }).click()
    await expect(page.getByTestId('node-end')).toHaveAttribute('data-state', 'skipped')
    await expect(page.getByTestId('edge-review-end')).toHaveAttribute('data-state', 'idle')
    await expect(page.getByText('Bukti keputusan', { exact: true })).toBeVisible()
    await accessible(page)
  })
