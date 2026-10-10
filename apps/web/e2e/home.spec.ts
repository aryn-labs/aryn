import { test, expect, type Page } from '@playwright/test'
import AxeBuilder from '@axe-core/playwright'
import { mkdir } from 'node:fs/promises'
import { resolve } from 'node:path'
import { homeFixture, type HomeScenario } from '../src/features/home/tests/fixtures'
const evidence = resolve('../../.local/home-audit-v2')
async function mockHome(page: Page, scenario: HomeScenario = 'new', writable = true) {
  const writes: string[] = []
  await page.route('http://127.0.0.1:5173/api/**', async (route) => {
    const url = new URL(route.request().url()),
      path = url.pathname
    const data = homeFixture(
      scenario,
      path.includes('project-two') ? 'project-two' : 'project-one',
      writable,
    )
    if (route.request().method() !== 'GET' && path !== '/api/session') writes.push(path)
    if (path === '/api/session')
      return route.fulfill({ json: { csrf: 'test', mode: 'development' } })
    if (path === '/api/workspace/context') return route.fulfill({ json: data.context })
    if (path.endsWith('/summary')) return route.fulfill({ json: data.summary })
    if (path.endsWith('/resources/blueprints'))
      return route.fulfill({
        json: {
          organization_id: 'org-test',
          project_id: data.summary.project_id,
          resource: 'blueprints',
          items: data.agents,
          next_cursor: null,
          limit: 4,
          refreshed_at: data.summary.refreshed_at,
        },
      })
    if (path.endsWith('/workflows'))
      return route.fulfill({ json: { items: data.workflows, next: null } })
    if (path.endsWith('/relay'))
      return route.fulfill({ json: { items: data.incidents, next: null } })
    if (path.endsWith('/review-queue'))
      return route.fulfill({ json: { items: data.reviews, next: null } })
    if (path.endsWith('/lifecycle')) return route.fulfill({ json: data.lifecycle })
    if (path.endsWith('/workflows/workflow-one')) return route.fulfill({ json: data.workflows[0] })
    if (path.endsWith('/relay/incident-one')) return route.fulfill({ json: data.incidents[0] })
    if (path.endsWith('/workflow-runs/workflow-review'))
      return route.fulfill({ json: data.reviews[0] })
    if (path.endsWith('/resources/blueprints/agent-one'))
      return route.fulfill({ json: data.agents[0] })
    if (path.endsWith('/resources/versions/version-review'))
      return route.fulfill({ json: data.summary.review_candidates[0] })
    if (path.endsWith('/resources/runs/run-test'))
      return route.fulfill({ json: data.summary.latest_runs[0] })
    return route.fulfill({ status: 404, json: {} })
  })
  return writes
}
async function assertAccessible(page: Page) {
  const result = await new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa', 'wcag21aa'])
    .analyze()
  expect(result.violations).toEqual([])
}
test.beforeAll(async () => {
  await mkdir(evidence, { recursive: true })
})
for (const scenario of ['new', 'active', 'issues'] as const)
  for (const width of [1440, 768, 390])
    for (const theme of ['dark', 'light']) {
      test(`Home ${scenario} · ${width}px · ${theme}`, async ({ page }) => {
        const errors: string[] = []
        page.on('pageerror', (error) => errors.push(error.message))
        await page.setViewportSize({ width, height: 900 })
        const writes = await mockHome(page, scenario)
        await page.addInitScript((value) => localStorage.setItem('aryn.shell.theme', value), theme)
        await page.goto('/')
        await expect(page.locator('[data-home-state]')).toHaveAttribute('data-home-state', scenario)
        await page.evaluate(() => document.fonts.ready)
        await expect(page.getByRole('heading', { name: 'Your workspace' })).toBeVisible()
        if (scenario === 'new') {
          await expect(page.getByRole('heading', { name: 'Getting Started' })).toBeVisible()
          await expect(page.getByRole('heading', { name: 'Continue Working' })).toHaveCount(0)
          await expect(page.getByRole('heading', { name: 'Recent Activity' })).toHaveCount(0)
        } else {
          await expect(page.getByRole('heading', { name: 'Continue Working' })).toBeVisible()
          await expect(page.getByRole('heading', { name: 'Getting Started' })).toHaveCount(0)
          await expect(page.getByRole('heading', { name: 'Recent Activity' })).toHaveCount(1)
        }
        if (scenario === 'issues')
          expect(
            await page
              .locator('#attention-heading')
              .evaluate(
                (element) =>
                  !!(
                    element.compareDocumentPosition(document.getElementById('continue-heading')!) &
                    Node.DOCUMENT_POSITION_FOLLOWING
                  ),
              ),
          ).toBe(true)
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(
          true,
        )
        expect(
          await page
            .locator('.main-workspace')
            .evaluate((element) => element.scrollWidth <= element.clientWidth),
        ).toBe(true)
        await assertAccessible(page)
        await page.screenshot({ path: resolve(evidence, `home-${scenario}-${width}-${theme}.png`) })
        await page.locator('.main-workspace').evaluate((element) => {
          element.scrollTop = element.scrollHeight
        })
        await page.screenshot({
          path: resolve(evidence, `home-${scenario}-${width}-${theme}-lower.png`),
        })
        expect(writes).toEqual([])
        expect(errors).toEqual([])
      })
    }
for (const width of [1440, 768, 390])
  for (const theme of ['dark', 'light']) {
    test(`Home composer and blocked conversation at ${width}px ${theme}`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 })
      const writes = await mockHome(page, 'active')
      const externalRequests: string[] = []
      page.on('request', (request) => {
        if (new URL(request.url()).origin !== 'http://127.0.0.1:5173')
          externalRequests.push(request.url())
      })
      await page.addInitScript((value) => localStorage.setItem('aryn.shell.theme', value), theme)
      await page.goto('/')
      const input = page.getByRole('textbox', {
        name: 'Describe the agent or workflow you want to build',
      })
      await expect(input).toBeVisible()
      const initialHeight = await input.evaluate((element) => element.clientHeight)
      await input.fill(
        Array.from({ length: 24 }, (_, index) => `A line of requirements ${index}`).join('\n'),
      )
      await expect
        .poll(() => input.evaluate((element) => element.clientHeight))
        .toBeGreaterThan(initialHeight)
      const box = await input.evaluate((element) => {
        const style = getComputedStyle(element)
        return {
          height: element.clientHeight,
          maximum: parseFloat(style.maxHeight),
          scroll: element.scrollHeight,
          resize: style.resize,
          border: style.borderTopWidth,
          outline: style.outlineStyle,
        }
      })
      expect(box.height).toBeLessThanOrEqual(box.maximum)
      expect(box.scroll).toBeGreaterThan(box.height)
      expect(box.resize).toBe('none')
      expect(box.border).toBe('0px')
      expect(box.outline).toBe('none')
      const inputRect = await input.boundingBox()
      const buttonRect = await page
        .getByRole('button', { name: 'Continue', exact: true })
        .boundingBox()
      expect(inputRect!.y + inputRect!.height).toBeLessThanOrEqual(buttonRect!.y)
      await input.fill('Review customer research without running tools.')
      await expect.poll(() => input.evaluate((element) => element.clientHeight)).toBe(initialHeight)
      await input.press('Control+Enter')
      await expect(page.getByRole('heading', { name: 'Assistant', exact: true })).toBeFocused()
      await expect(page.getByRole('dialog')).toHaveCount(0)
      await expect(page.getByText('Not sent', { exact: true })).toBeVisible()
      await expect(page.getByRole('heading', { name: 'Assistant unavailable' })).toBeVisible()
      const followUp = page.getByRole('textbox', { name: 'Follow-up message' })
      await followUp.fill('Draft a cited report.')
      await followUp.press('Control+Enter')
      await expect(page.getByRole('button', { name: 'Send', exact: true })).toBeDisabled()
      await expect(
        page.getByRole('list', { name: 'Conversation messages' }).getByRole('listitem'),
      ).toHaveCount(1)
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(
        true,
      )
      expect(
        await page
          .locator('.main-workspace')
          .evaluate((element) => element.scrollWidth <= element.clientWidth),
      ).toBe(true)
      await assertAccessible(page)
      await page.locator('.main-workspace').evaluate((element) => {
        element.scrollTop = 0
      })
      await page.screenshot({ path: resolve(evidence, `conversation-${width}-${theme}.png`) })
      await page.getByRole('button', { name: 'Back to overview' }).click()
      await expect(input).toHaveValue('Review customer research without running tools.')
      await expect(input).toBeFocused()
      expect(writes).toEqual([])
      expect(externalRequests).toEqual([])
    })
    test(`Guided Creation keyboard review and unsaved handoff at ${width}px ${theme}`, async ({
      page,
    }) => {
      await page.setViewportSize({ width, height: 900 })
      const writes = await mockHome(page)
      await page.addInitScript((value) => localStorage.setItem('aryn.shell.theme', value), theme)
      await page.goto('/')
      await expect(page.locator('[data-home-state]')).toHaveAttribute('data-home-state', 'new')
      const composer = page.getByRole('textbox', {
        name: 'Describe the agent or workflow you want to build',
      })
      await composer.fill('Review customer research')
      await composer.press('Control+Enter')
      await expect(page.getByRole('heading', { name: 'Assistant', exact: true })).toBeFocused()
      await expect(page.getByText('Not sent', { exact: true })).toBeVisible()
      await expect(page.getByRole('button', { name: 'Send', exact: true })).toBeDisabled()
      await expect(page.getByRole('dialog')).toHaveCount(0)
      await page.getByRole('button', { name: 'Create Workflow draft', exact: true }).click()
      const drawer = page.getByRole('dialog')
      await expect(drawer).toBeVisible()
      await expect(
        drawer.getByRole('textbox', { name: 'Describe the work (required)' }),
      ).toBeFocused()
      await drawer.getByRole('radio', { name: /Workflow Tasks/ }).check()
      await drawer.getByRole('textbox', { name: 'Expected output' }).fill('A cited report')
      await drawer.getByRole('combobox').selectOption('external')
      await drawer
        .getByRole('textbox', { name: 'Integration requirements' })
        .fill('Approved document read access')
      await assertAccessible(page)
      for (let i = 0; i < 9; i++) {
        await page.keyboard.press('Tab')
        expect(await drawer.evaluate((element) => element.contains(document.activeElement))).toBe(
          true,
        )
      }
      await drawer.getByRole('button', { name: 'Review brief' }).click()
      await expect(
        drawer.getByRole('heading', { name: 'Review your starting brief' }),
      ).toBeFocused()
      await assertAccessible(page)
      await page.screenshot({ path: resolve(evidence, `guided-review-${width}-${theme}.png`) })
      await drawer.getByRole('button', { name: 'Open Workflow Builder' }).click()
      await expect(page).toHaveURL(/\/workflows$/)
      await expect(
        page.getByRole('heading', { name: 'Workflow Builder unavailable' }),
      ).toBeVisible()
      await expect(page.getByText('Review customer research')).toBeVisible()
      expect(
        await page.evaluate(() =>
          JSON.stringify(localStorage).includes('Review customer research'),
        ),
      ).toBe(false)
      await assertAccessible(page)
      await page.reload()
      await expect(page.getByText('Review customer research')).toHaveCount(0)
      expect(writes).toEqual([])
    })
    test(`Home details drawer supports keyboard and focus return at ${width}px ${theme}`, async ({
      page,
    }) => {
      await page.setViewportSize({ width, height: 900 })
      await mockHome(page, 'active')
      await page.addInitScript((value) => localStorage.setItem('aryn.shell.theme', value), theme)
      await page.goto('/')
      const trigger = page.getByRole('button', { name: 'Inspect Research assistant' })
      await trigger.focus()
      await trigger.press('Enter')
      const drawer = page.getByRole('dialog', { name: 'Resource details' })
      await expect(drawer.getByText('agent-one', { exact: true })).toBeVisible()
      await assertAccessible(page)
      for (let i = 0; i < 4; i++) {
        await page.keyboard.press('Tab')
        expect(await drawer.evaluate((element) => element.contains(document.activeElement))).toBe(
          true,
        )
      }
      await page.screenshot({ path: resolve(evidence, `home-details-${width}-${theme}.png`) })
      await page.keyboard.press('Escape')
      await expect(drawer).toHaveCount(0)
      await expect(trigger).toBeFocused()
    })
  }
test('attention resources resolve to real, scoped detail contracts', async ({ page }) => {
  const writes = await mockHome(page, 'issues')
  await page.goto('/')
  for (const name of [
    'Version 1.0.1',
    'Disposable service needs review',
    'Recorded test run',
    '1.1.0',
    'Workflow output review',
  ]) {
    await page
      .getByRole('button', { name: `Inspect ${name}`, exact: true })
      .first()
      .click()
    await expect(page.getByRole('dialog').getByText('Loading resource')).toHaveCount(0)
    await expect(page.getByRole('dialog').getByText('Unable to load data')).toHaveCount(0)
    await assertAccessible(page)
    await page.keyboard.press('Escape')
  }
  expect(writes).toEqual([])
})
test('project switching clears unsaved handoff and home composer input', async ({ page }) => {
  await mockHome(page)
  await page.goto('/')
  const composer = page.getByRole('textbox', {
    name: 'Describe the agent or workflow you want to build',
  })
  await composer.fill('Private project-one brief')
  await page.getByRole('button', { name: 'Switch workspace' }).click()
  await page.getByRole('menuitemradio', { name: 'Second Project' }).click()
  await expect(composer).toHaveValue('')
  await page.getByRole('button', { name: 'Create Agent', exact: true }).click()
  await page
    .getByRole('textbox', { name: 'Describe the work (required)' })
    .fill('Second project only')
  await page.getByRole('button', { name: 'Review brief' }).click()
  await page.getByRole('button', { name: 'Open Agent Builder' }).click()
  await expect(page.getByText('Second project only')).toBeVisible()
  await page.getByRole('button', { name: 'Switch workspace' }).click()
  await page.getByRole('menuitemradio', { name: 'First Project' }).click()
  await expect(page.getByText('Second project only')).toHaveCount(0)
})
test('partial unavailable services keep real work usable and never imply an empty workspace', async ({
  page,
}) => {
  await mockHome(page, 'active')
  await page.route('http://127.0.0.1:5173/api/projects/project-one/workflows?*', (route) =>
    route.fulfill({ status: 404, json: {} }),
  )
  await page.route('http://127.0.0.1:5173/api/projects/project-one/relay?*', (route) =>
    route.fulfill({ status: 404, json: {} }),
  )
  await page.goto('/')
  await expect(page.locator('[data-home-state]')).toHaveAttribute('data-home-state', 'active')
  await expect(page.getByText('Some workspace data is unavailable')).toBeVisible()
  const notice = page.locator('.home-service-status')
  await expect(notice).not.toHaveAttribute('open')
  await expect(
    notice.getByRole('button', { name: 'Try again — Workflow definitions' }),
  ).not.toBeVisible()
  const collapsed = await notice.boundingBox()
  expect(collapsed!.height).toBeLessThan(80)
  await notice.locator('summary').focus()
  await page.keyboard.press('Enter')
  await expect(
    notice.getByRole('button', { name: 'Try again — Workflow definitions' }),
  ).toBeVisible()
  await expect(page.getByRole('button', { name: 'Inspect Research assistant' })).toBeVisible()
  await expect(page.getByText('No workflow definitions yet.')).toHaveCount(0)
  await expect(page.getByText('Getting Started')).toHaveCount(0)
  await assertAccessible(page)
})
test('view permissions never expose unauthorized creation or fabricated success', async ({
  page,
}) => {
  const writes = await mockHome(page, 'issues', false)
  await page.goto('/')
  await expect(page.getByRole('button', { name: 'Create Agent' })).toBeDisabled()
  await expect(page.getByRole('button', { name: 'Build Workflow' })).toBeDisabled()
  await expect(
    page.getByRole('button', { name: 'Inspect Disposable service needs review' }),
  ).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Inspect 1.1.0' })).toHaveCount(0)
  await expect(page.getByRole('button', { name: /^(Retry|Approve|Publish)/ })).toHaveCount(0)
  expect(writes).toEqual([])
})
