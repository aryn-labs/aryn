import { test, expect, type Page } from '@playwright/test'
import AxeBuilder from '@axe-core/playwright'
import { mkdir } from 'node:fs/promises'
import { resolve } from 'node:path'
import { contextFixture, summaryFixture, runFixture, statusFixture } from '../src/test/fixtures'
const evidence = resolve('../../.local/studio-shell-v1')
async function mockApi(
  page: Page,
  options: {
    empty?: boolean
    activity?: boolean
    contextStatus?: number
    summaryStatus?: number
    slow?: boolean
    hosted?: boolean
    longNames?: boolean
  } = {},
) {
  await page.route('http://127.0.0.1:5173/api/**', async (route) => {
    const path = new URL(route.request().url()).pathname
    if (path === '/api/session') {
      await route.fulfill({
        json: { csrf: 'test-csrf', mode: options.hosted ? 'oidc' : 'development' },
      })
      return
    }
    if (path === '/api/logout') {
      await route.fulfill({ json: { logged_out: true } })
      return
    }
    if (path === '/api/workspace/context') {
      await route.fulfill({
        status: options.contextStatus ?? 200,
        json: options.contextStatus
          ? { login_url: '/auth/login' }
          : {
              ...contextFixture,
              ...(options.longNames
                ? {
                    organization: {
                      ...contextFixture.organization,
                      name: 'Organization '.repeat(12),
                    },
                  }
                : {}),
              mode: options.hosted ? 'hosted' : 'isolated-test',
              projects: options.empty
                ? []
                : options.longNames
                  ? contextFixture.projects.map((project) => ({
                      ...project,
                      name: `${project.name} ${'Workspace '.repeat(12)}`,
                    }))
                  : contextFixture.projects,
            },
      })
      return
    }
    if (path === '/api/workspace/status') {
      await route.fulfill({ json: statusFixture })
      return
    }
    if (path.endsWith('/summary')) {
      if (options.slow) await new Promise((res) => setTimeout(res, 1500))
      await route.fulfill({
        status: options.summaryStatus ?? 200,
        json: summaryFixture(
          path.includes('project-two') ? 'project-two' : 'project-one',
          options.activity,
        ),
      })
      return
    }
    if (path.endsWith('/runs/run-test')) {
      await route.fulfill({ json: runFixture })
      return
    }
    if (/\/(workflows|relay|review-queue)$/.test(path)) {
      await route.fulfill({ json: { items: [], next: null } })
      return
    }
    if (path.endsWith('/resources/blueprints')) {
      await route.fulfill({
        json: {
          organization_id: 'org-test',
          project_id: path.includes('project-two') ? 'project-two' : 'project-one',
          resource: 'blueprints',
          items:
            new URL(route.request().url()).searchParams.get('limit') === '4'
              ? []
              : [{ ...runFixture, id: 'agent-search', name: 'Test search agent' }],
          next_cursor: null,
          limit: 8,
          refreshed_at: '2026-10-09T12:00:00Z',
        },
      })
      return
    }
    if (path.endsWith('/blueprints/agent-search')) {
      await route.fulfill({
        json: { ...runFixture, id: 'agent-search', name: 'Test search agent' },
      })
      return
    }
    await route.fulfill({
      json: {
        organization_id: 'org-test',
        project_id: path.includes('project-two') ? 'project-two' : 'project-one',
        resource: path.includes('runs') ? 'runs' : 'projects',
        items: [],
        next_cursor: null,
        limit: 8,
        refreshed_at: '2026-10-09T12:00:00Z',
      },
    })
  })
}
test.beforeAll(async () => {
  await mkdir(evidence, { recursive: true })
})
for (const width of [1440, 768, 390]) {
  for (const theme of ['dark', 'light']) {
    test(`visual and accessibility ${width}px ${theme}`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 })
      await mockApi(page)
      await page.addInitScript((value) => localStorage.setItem('aryn.shell.theme', value), theme)
      await page.goto('/')
      await expect(page.getByText('Getting Started')).toBeVisible()
      await page.evaluate(() => document.fonts.ready)
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(
        true,
      )
      expect(
        await page.locator('.main-workspace').evaluate((el) => el.scrollWidth <= el.clientWidth),
      ).toBe(true)
      expect(
        await page.locator('.app-topbar').evaluate((el) => el.scrollWidth <= el.clientWidth),
      ).toBe(true)
      await page.screenshot({ path: resolve(evidence, `home-${width}-${theme}.png`) })
      const axe = await new AxeBuilder({ page })
        .withTags(['wcag2a', 'wcag2aa', 'wcag21aa'])
        .analyze()
      expect(axe.violations).toEqual([])
      await expect(page.getByRole('complementary', { name: 'Context inspector' })).toHaveCount(0)
      await expect(page.getByRole('button', { name: /context inspector/i })).toHaveCount(0)
      await expect(page.locator('.workspace-breadcrumb')).toHaveCount(0)
      const header = page.getByRole('banner')
      await expect(header.getByRole('button', { name: 'Environment information' })).toHaveCount(0)
      await expect(header.getByRole('button', { name: 'Model information' })).toHaveCount(0)
      await expect(header.getByRole('button')).toHaveCount(width === 390 ? 5 : 4)
      if (width === 1440) {
        expect((await page.locator('.app-topbar').boundingBox())?.height).toBe(60)
        expect((await page.locator('.app-sidebar').boundingBox())?.width).toBe(240)
        const sidebar = await page.locator('.app-sidebar').boundingBox()
        const brand = await page.locator('.topbar-brand').boundingBox()
        expect(brand?.x).toBe(sidebar?.x)
        expect(brand?.width).toBe(sidebar?.width)
        await page.getByRole('button', { name: 'Collapse sidebar' }).click()
        expect((await page.locator('.app-sidebar').boundingBox())?.width).toBe(64)
        expect((await page.locator('.topbar-brand').boundingBox())?.width).toBe(64)
        await page.screenshot({ path: resolve(evidence, `home-1440-${theme}-collapsed.png`) })
      } else {
        await expect(page.getByRole('dialog')).toHaveCount(0)
        if (width === 768) {
          expect((await page.locator('.app-sidebar').boundingBox())?.width).toBe(64)
          expect((await page.locator('.topbar-brand').boundingBox())?.width).toBe(64)
          expect((await page.locator('.topbar-brand').boundingBox())?.x).toBe(0)
        }
        await page.locator('.main-workspace').evaluate((el) => {
          el.scrollTop = el.scrollHeight
        })
        await expect(page.getByText('Getting Started')).toBeInViewport()
        await page.screenshot({ path: resolve(evidence, `home-${width}-${theme}-activity.png`) })
      }
    })
  }
}
for (const width of [1440, 390]) {
  test(`combined workspace menu supports keyboard project switching at ${width}px`, async ({
    page,
  }) => {
    await page.setViewportSize({ width, height: 900 })
    await mockApi(page)
    await page.goto('/')
    await expect(page.getByText('Getting Started')).toBeVisible()
    const trigger = page.getByRole('button', { name: 'Switch workspace' })
    await trigger.focus()
    await page.keyboard.press('ArrowDown')
    const first = page.getByRole('menuitemradio', { name: 'First Project' })
    await expect(first).toHaveAttribute('aria-checked', 'true')
    await expect(first).toBeFocused()
    await page.screenshot({ path: resolve(evidence, `workspace-menu-${width}-dark.png`) })
    const axe = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze()
    expect(axe.violations).toEqual([])
    await page.keyboard.press('ArrowDown')
    await expect(page.getByRole('menuitemradio', { name: 'Second Project' })).toBeFocused()
    await page.keyboard.press('Enter')
    await expect(trigger).toContainText('Second Project')
    await expect(trigger).toBeFocused()
    await page.reload()
    await expect(trigger).toContainText('Second Project')
    await trigger.click()
    await expect(page.getByRole('menuitemradio', { name: 'Second Project' })).toHaveAttribute(
      'aria-checked',
      'true',
    )
    await page.keyboard.press('Escape')
    await expect(trigger).toBeFocused()
  })
}

test('long organization and project names remain usable on a narrow mobile viewport', async ({
  page,
}) => {
  await page.setViewportSize({ width: 320, height: 740 })
  await mockApi(page, { longNames: true })
  await page.goto('/')
  await expect(page.getByText('Getting Started')).toBeVisible()
  expect(await page.locator('.app-topbar').evaluate((el) => el.scrollWidth <= el.clientWidth)).toBe(
    true,
  )
  await page.getByRole('button', { name: 'Switch workspace' }).click()
  const menu = page.getByRole('menu', { name: 'Switch workspace' })
  await expect(menu).toBeVisible()
  expect(await menu.evaluate((el) => el.scrollWidth <= el.clientWidth)).toBe(true)
  const bounds = await menu.boundingBox()
  expect(bounds!.x).toBeGreaterThanOrEqual(0)
  expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(320)
  await page.keyboard.press('Escape')
  await expect(page.getByRole('button', { name: 'Switch workspace' })).toBeFocused()
})

test('Settings contains contextual runtime/model information and remains accessible', async ({
  page,
}) => {
  await mockApi(page)
  await page.goto('/settings')
  await expect(page.getByText('Runtime not ready')).toBeVisible()
  await expect(page.getByText('Active model unavailable')).toBeVisible()
  await expect(page.getByRole('banner').getByText('Model unavailable')).toHaveCount(0)
  const axe = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze()
  expect(axe.violations).toEqual([])
  await page.setViewportSize({ width: 390, height: 900 })
  expect(
    await page.locator('.main-workspace').evaluate((el) => el.scrollWidth <= el.clientWidth),
  ).toBe(true)
  await page.screenshot({ path: resolve(evidence, 'settings-390-dark.png') })
})

test('legacy context preference stays removed and logo divider follows sidebar state', async ({
  page,
}) => {
  await page.setViewportSize({ width: 1440, height: 900 })
  await mockApi(page)
  await page.addInitScript(() => localStorage.setItem('aryn.shell.inspector', 'true'))
  await page.goto('/')
  await expect(page.getByText('Getting Started')).toBeVisible()
  await expect(page.getByRole('button', { name: /context inspector/i })).toHaveCount(0)
  await expect(page.getByRole('complementary', { name: 'Context inspector' })).toHaveCount(0)
  const collapse = page.getByRole('button', { name: 'Collapse sidebar' })
  await collapse.focus()
  await page.keyboard.press('Enter')
  expect((await page.locator('.app-sidebar').boundingBox())?.width).toBe(64)
  expect((await page.locator('.topbar-brand').boundingBox())?.width).toBe(64)
  await page.reload()
  expect((await page.locator('.topbar-brand').boundingBox())?.width).toBe(64)
  await page.getByRole('button', { name: 'Expand sidebar' }).focus()
  await page.keyboard.press('Space')
  expect((await page.locator('.topbar-brand').boundingBox())?.width).toBe(240)
  await page.getByRole('button', { name: 'Account menu' }).click()
  await expect(page.getByRole('menuitem', { name: /context inspector/i })).toHaveCount(0)
})
test('all sidebar routes, browser back and deep link reload work', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 })
  await mockApi(page)
  await page.goto('/')
  for (const title of [
    'Projects',
    'Agents',
    'Workflows',
    'Runs',
    'Automations',
    'Relay',
    'Brief',
    'Bench',
    'Integrations',
    'Deployments',
    'Approvals',
    'Settings',
    'Help & Support',
  ]) {
    await page
      .getByRole('navigation', { name: 'Primary navigation' })
      .getByRole('link', { name: title, exact: true })
      .click()
    await expect(page.getByRole('heading', { name: title, exact: true })).toBeVisible()
    await expect(page.locator('#main-content')).toBeFocused()
    await page.reload()
    await expect(page.getByRole('heading', { name: title, exact: true })).toBeVisible()
  }
  await page.goBack()
  await expect(page.getByRole('heading', { name: 'Settings', exact: true })).toBeVisible()
})
test('keyboard search opens, filters resources and restores focus', async ({ page }) => {
  await mockApi(page)
  await page.goto('/')
  await expect(page.getByText('Getting Started')).toBeVisible()
  await page.keyboard.press('Control+k')
  await expect(page.getByRole('combobox')).toBeFocused()
  await page.getByRole('combobox').fill('Test search')
  await page.getByRole('option', { name: /Test search agent/ }).click()
  await expect(page.getByRole('dialog', { name: 'Resource details' })).toBeVisible()
  await expect(page.getByText('agent-search', { exact: true })).toBeVisible()
  await page.keyboard.press('Control+k')
  await page.keyboard.press('Escape')
  await expect(page.getByRole('button', { name: 'Global search' })).toBeFocused()
  await page.keyboard.press('Control+k')
  await page.getByRole('combobox').fill('Bench')
  await page.keyboard.press('Enter')
  await expect(page).toHaveURL(/\/bench$/)
})
test('mobile navigation traps focus and closes on route selection', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await mockApi(page)
  await page.goto('/')
  await page.getByRole('button', { name: 'Open navigation' }).click()
  const dialog = page.getByRole('dialog')
  await expect(dialog).toBeVisible()
  for (let i = 0; i < 20; i++) {
    await page.keyboard.press('Tab')
    expect(await dialog.evaluate((el) => el.contains(document.activeElement))).toBe(true)
  }
  await dialog.getByRole('link', { name: 'Agents', exact: true }).click()
  await expect(dialog).toHaveCount(0)
  await expect(page).toHaveURL(/\/agents$/)
})
test('project selection persists and resource details do not leak old selections', async ({
  page,
}) => {
  await page.setViewportSize({ width: 1440, height: 900 })
  await mockApi(page, { activity: true })
  await page.goto('/')
  await page.getByRole('button', { name: 'Inspect Recorded test run' }).click()
  await expect(page.getByText('Verified by backend')).toBeVisible()
  await page.keyboard.press('Escape')
  await expect(page.getByRole('button', { name: 'Inspect Recorded test run' })).toBeFocused()
  await page.getByRole('button', { name: 'Switch workspace' }).click()
  await page.getByRole('menuitemradio', { name: 'Second Project' }).click()
  await expect(page.getByRole('dialog')).toHaveCount(0)
  await expect(page.getByText('Verified by backend')).toHaveCount(0)
  await page.reload()
  await expect(page.getByRole('button', { name: 'Switch workspace' })).toContainText(
    'Second Project',
  )
})
for (const width of [1440, 768, 390]) {
  test(`resource details remain accessible without a context panel at ${width}px`, async ({
    page,
  }) => {
    await page.setViewportSize({ width, height: 900 })
    await mockApi(page, { activity: true })
    await page.goto('/')
    const trigger = page.getByRole('button', { name: 'Inspect Recorded test run', exact: true })
    await trigger.focus()
    await page.keyboard.press('Enter')
    const dialog = page.getByRole('dialog', { name: 'Resource details' })
    await expect(dialog).toBeVisible()
    await expect(dialog.getByText('Verified by backend')).toBeVisible()
    await page.screenshot({ path: resolve(evidence, `resource-details-${width}-dark.png`) })
    const axe = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze()
    expect(axe.violations).toEqual([])
    for (let i = 0; i < 4; i++) {
      await page.keyboard.press('Tab')
      expect(await dialog.evaluate((el) => el.contains(document.activeElement))).toBe(true)
    }
    await page.keyboard.press('Escape')
    await expect(dialog).toHaveCount(0)
    await expect(trigger).toBeFocused()
    await expect(page.getByRole('complementary', { name: 'Context inspector' })).toHaveCount(0)
  })
}

test('notifications, environment, account and hosted logout use real states and CSRF', async ({
  page,
}) => {
  await mockApi(page, { hosted: true })
  await page.goto('/')
  await expect(page.getByText('Getting Started')).toBeVisible()
  await page.getByRole('button', { name: 'Notifications' }).click()
  await expect(page.getByText('Notifications unavailable')).toBeVisible()
  await page.keyboard.press('Escape')
  await expect(page.getByRole('button', { name: 'Notifications' })).toBeFocused()
  await page
    .getByRole('navigation', { name: 'Primary navigation' })
    .getByRole('link', { name: 'Settings', exact: true })
    .click()
  await expect(page.getByText('Runtime not ready')).toBeVisible()
  await expect(page.getByText('Active model unavailable')).toBeVisible()
  await page
    .getByRole('navigation', { name: 'Primary navigation' })
    .getByRole('link', { name: 'Home', exact: true })
    .click()
  await page.getByRole('button', { name: 'Account menu' }).click()
  await page.getByRole('menuitem', { name: 'Account details' }).click()
  const logoutRequest = page.waitForRequest('**/api/logout')
  await page.getByRole('button', { name: 'Sign out', exact: true }).click()
  expect((await logoutRequest).headers()['x-csrf-token']).toBe('test-csrf')
  await expect(page.getByText('You are signed out')).toBeVisible()
  await expect(page.getByText('Test Studio')).toHaveCount(0)
  await expect(page.getByRole('link', { name: 'Sign in to ARYN' })).toHaveAttribute(
    'href',
    '/auth/login',
  )
})
for (const status of [401, 403, 503])
  test(`server ${status} exposes the correct failure state`, async ({ page }) => {
    await mockApi(page, { contextStatus: status })
    await page.goto('/')
    await expect(
      page.getByText(status === 503 ? 'Unable to load data' : 'Access required').first(),
    ).toBeVisible()
    await expect(page.getByText('Test Studio')).toHaveCount(0)
    if (status === 401)
      await expect(page.getByRole('link', { name: 'Sign in to ARYN' }).first()).toHaveAttribute(
        'href',
        '/auth/login',
      )
  })
test('loading, no projects, recovery and unavailable runtime remain explicit', async ({ page }) => {
  await mockApi(page, { slow: true })
  await page.goto('/')
  await expect(page.getByText('Loading Home overview')).toBeVisible()
  await expect(page.getByText('Getting Started')).toBeVisible()
  await page.unroute('http://127.0.0.1:5173/api/**')
  await mockApi(page, { empty: true })
  await page.reload()
  await expect(page.getByRole('heading', { name: 'No accessible projects' })).toBeVisible()
})
test('unknown routes have a recoverable 404', async ({ page }) => {
  await mockApi(page)
  await page.goto('/unknown-route')
  await expect(page.getByRole('heading', { name: 'Page not found' })).toBeVisible()
  await page.getByRole('link', { name: 'Back to Home' }).click()
  await expect(page.getByRole('heading', { name: 'Your workspace' })).toBeVisible()
})
test('API recovery reboots the session and reloads the workspace', async ({ page }) => {
  await mockApi(page, { contextStatus: 503 })
  await page.goto('/')
  await expect(page.getByText('Unable to load data').first()).toBeVisible()
  await page.unroute('http://127.0.0.1:5173/api/**')
  await mockApi(page)
  await page.getByRole('button', { name: 'Try again' }).first().click()
  await expect(page.getByText('Getting Started')).toBeVisible()
})
test('global search reports partial API failure while keeping keyboard navigation usable', async ({
  page,
}) => {
  await mockApi(page)
  await page.route(
    'http://127.0.0.1:5173/api/projects/project-one/resources/blueprints?*',
    (route) =>
      new URL(route.request().url()).searchParams.get('limit') === '4'
        ? route.fallback()
        : route.fulfill({ status: 503, json: {} }),
  )
  await page.goto('/')
  await expect(page.getByText('Getting Started')).toBeVisible()
  await page.keyboard.press('Control+k')
  await page.getByRole('combobox').fill('Agents')
  await expect(page.getByText('Agents search unavailable.')).toBeVisible()
  const result = await new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa', 'wcag21aa'])
    .analyze()
  expect(result.violations).toEqual([])
  await page.keyboard.press('Enter')
  await expect(page).toHaveURL(/\/agents$/)
})
