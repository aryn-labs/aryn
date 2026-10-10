import { test, expect } from '@playwright/test'
import AxeBuilder from '@axe-core/playwright'
import { mkdir } from 'node:fs/promises'
import { resolve } from 'node:path'
const evidence = resolve('../../.local/chat-finalization')
test.beforeAll(async () => {
  await mkdir(evidence, { recursive: true })
})
for (const width of [1920, 1440, 1024, 768, 390])
  for (const theme of ['dark', 'light']) {
    test(`Real API/Core with isolated runtime: multi-turn and resume ${width} ${theme}`, async ({
      page,
    }) => {
      const errors: string[] = []
      page.on('pageerror', (error) => errors.push(error.message))
      await page.setViewportSize({ width, height: 900 })
      await page.addInitScript((value) => localStorage.setItem('aryn.shell.theme', value), theme)
      await page.addInitScript(
        (value) => localStorage.setItem('aryn.shell.project', value),
        `browser-${width}-${theme}`,
      )
      await page.goto('/')
      const input = page.getByRole('textbox', {
        name: 'Pesan untuk ARYN',
      })
      await expect(input).toBeVisible()
      const topic = `Isolated browser contract ${width} ${theme}`
      await input.fill(topic)
      await expect(page.getByRole('button', { name: 'Kirim pesan', exact: true })).toBeEnabled()
      await input.press('Enter')
      await page.getByRole('button', { name: 'Setuju dan kirim' }).click()
      await expect(page).toHaveURL(/\/chat\/chat_[a-f0-9]+$/)
      await expect(page.getByRole('dialog')).toHaveCount(0)
      await expect(page.getByText('[PENGUJIAN TERISOLASI]', { exact: false }).first()).toBeVisible()
      await expect(page.getByRole('main')).toBeFocused()
      const follow = page.getByRole('textbox', { name: 'Pesan untuk ARYN' })
      await follow.fill('Explain the previous answer with an example.')
      await follow.press('Enter')
      await expect(page.getByRole('dialog')).toHaveCount(0)
      await expect(page.locator('.chat-message-assistant')).toHaveCount(2)
      const url = page.url()
      await page.reload()
      await expect(page.locator('.chat-message-assistant')).toHaveCount(2)
      await follow.fill('Continue this same conversation after refresh.')
      await follow.press('Enter')
      await expect(page.locator('.chat-message-assistant')).toHaveCount(3)
      await expect(page.getByRole('dialog')).toHaveCount(0)
      await expect(page.getByText(topic, { exact: true }).last()).toBeVisible()
      await expect(page.getByRole('button', { name: 'Kirim pesan', exact: true })).toBeDisabled()
      await expect(page.getByRole('button', { name: 'Stop', exact: true })).toHaveCount(0)
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(
        true,
      )
      expect(
        await page
          .locator('.chat-workspace')
          .evaluate((node) => node.scrollWidth <= node.clientWidth),
      ).toBe(true)
      const checks = await new AxeBuilder({ page })
        .withTags(['wcag2a', 'wcag2aa', 'wcag21aa'])
        .analyze()
      expect(checks.violations).toEqual([])
      await page.screenshot({ path: resolve(evidence, `chat-offline-core-${width}-${theme}.png`) })
      await page.getByRole('button', { name: 'Riwayat percakapan', exact: true }).click()
      const drawer = page.getByRole('dialog')
      await expect(drawer).toBeVisible()
      await page.keyboard.press('Tab')
      expect(await drawer.evaluate((node) => node.contains(document.activeElement))).toBe(true)
      await page.keyboard.press('Escape')
      await expect(
        page.getByRole('button', { name: 'Riwayat percakapan', exact: true }),
      ).toBeFocused()
      await page.getByRole('link', { name: 'Chat Baru' }).click()
      await page.locator('#continue-heading').waitFor()
      await page
        .getByRole('link', { name: new RegExp('Isolated browser contract ' + width) })
        .click()
      await expect(page).toHaveURL(url)
      await expect(page.locator('.chat-message-assistant')).toHaveCount(3)
      expect(errors).toEqual([])
    })
  }

test('lost acknowledgement retries the exact persisted request without a duplicate turn', async ({
  page,
}) => {
  await page.addInitScript(() => localStorage.setItem('aryn.shell.project', 'browser-delivery'))
  const requests: string[] = []
  let acceptedId = ''
  await page.route('**/api/projects/browser-delivery/chat/conversations', async (route) => {
    if (route.request().method() !== 'POST') return route.continue()
    requests.push(route.request().postData() ?? '')
    if (requests.length !== 1) return route.continue()
    const response = await route.fetch()
    expect(response.status()).toBe(202)
    acceptedId = (await response.json()).id as string
    await route.abort('failed')
  })
  await page.goto('/')
  const input = page.getByRole('textbox', {
    name: 'Pesan untuk ARYN',
  })
  await input.fill('An isolated delivery test')
  await input.press('Enter')
  await page.getByRole('button', { name: 'Setuju dan kirim' }).click()
  await expect(page.getByRole('alert')).toContainText('Pengiriman belum dapat dipastikan')
  await expect(input).toHaveAttribute('readonly')
  await page.getByRole('button', { name: 'Coba ulang permintaan semula' }).click()
  await expect(page).toHaveURL(new RegExp(`/chat/${acceptedId}$`))
  await expect(page.locator('.chat-message-assistant')).toHaveCount(1)
  expect(requests).toHaveLength(2)
  expect(requests[0]).toBe(requests[1])
  await page.reload()
  await expect(page.locator('.chat-message')).toHaveCount(2)
})

test('first-use consent can be declined, persisted, reviewed and revoked; language persists', async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 900 })
  await page.addInitScript(() => localStorage.setItem('aryn.shell.project', 'browser-consent'))
  const sends: string[] = []
  page.on('request', (request) => {
    if (request.method() === 'POST' && request.url().endsWith('/chat/conversations'))
      sends.push(request.postData() ?? '')
  })
  await page.goto('/')
  const input = page.getByRole('textbox', { name: 'Pesan untuk ARYN' })
  await input.fill('Private draft remains here')
  await input.press('Shift+Enter')
  await expect(input).toHaveValue('Private draft remains here\n')
  await input.dispatchEvent('keydown', { key: 'Enter', isComposing: true, keyCode: 229 })
  await expect(page.getByRole('dialog')).toHaveCount(0)
  expect(sends).toHaveLength(0)
  await input.press('Enter')
  await expect(page.getByRole('dialog', { name: 'Gunakan provider model ini?' })).toBeVisible()
  await page.getByRole('button', { name: 'Nanti saja' }).click()
  await expect(input).toHaveValue('Private draft remains here\n')
  await expect(input).toBeFocused()
  expect(sends).toHaveLength(0)
  await input.press('Enter')
  await page.getByRole('button', { name: 'Setuju dan kirim' }).click()
  await expect(page.locator('.chat-message-assistant')).toHaveCount(1)
  expect(sends).toHaveLength(1)
  await page.goto('/settings')
  await expect(page.getByText('Persetujuan tersimpan')).toBeVisible()
  await page.getByRole('combobox', { name: 'Bahasa' }).selectOption('en-US')
  await expect(page.getByRole('heading', { name: 'Preferences', exact: true })).toBeVisible()
  await page.reload()
  await expect(page.getByRole('combobox', { name: 'Language' })).toHaveValue('en-US')
  await page.getByRole('button', { name: 'Revoke consent' }).click()
  await expect(
    page.getByText('Consent revoked. Future messages require approval again.'),
  ).toBeVisible()
  await page.goto('/')
  await expect(page.getByRole('button', { name: 'Create Agent' })).toBeVisible()
  const english = page.getByRole('textbox', { name: 'Message to ARYN' })
  await english.fill('Consent is required again')
  await english.press('Enter')
  await expect(page.getByRole('dialog', { name: 'Use this model provider?' })).toBeVisible()
  await page.getByRole('button', { name: 'Not now' }).click()
  expect(sends).toHaveLength(1)
  await page.goto('/settings')
  await page.getByRole('combobox', { name: 'Language' }).selectOption('id-ID')
  await expect(page.getByRole('heading', { name: 'Preferensi', exact: true })).toBeVisible()
})

test('chat input stays usable in a short mobile viewport with bounded growth', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 600 })
  await page.addInitScript(() =>
    localStorage.setItem('aryn.shell.project', 'browser-short-viewport'),
  )
  await page.goto('/')
  const input = page.getByRole('textbox', {
    name: 'Pesan untuk ARYN',
  })
  await input.fill('An isolated small-screen test')
  await input.press('Enter')
  await page.getByRole('button', { name: 'Setuju dan kirim' }).click()
  await expect(page.locator('.chat-message-assistant')).toHaveCount(1)
  const follow = page.getByRole('textbox', { name: 'Pesan untuk ARYN' })
  await follow.fill('Long input\n'.repeat(100))
  await expect(follow).toBeVisible()
  expect((await follow.boundingBox())?.height).toBeLessThanOrEqual(168)
  await expect(page.getByRole('button', { name: 'Kirim pesan', exact: true })).toBeInViewport()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
})

test('new replies preserve reading position and follow the bottom only when already there', async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 600 })
  await page.addInitScript(() => localStorage.setItem('aryn.shell.project', 'browser-scroll'))
  await page.goto('/')
  const send = page.getByRole('button', { name: 'Kirim pesan', exact: true })
  const input = page.getByRole('textbox', { name: 'Pesan untuk ARYN' })
  await input.fill('An isolated request for scroll coverage.\n'.repeat(12))
  await expect(send).toBeEnabled()
  await input.press('Enter')
  await page.getByRole('button', { name: 'Setuju dan kirim' }).click()
  const replies = page.locator('.chat-message-assistant')
  await expect(replies).toHaveCount(1)
  await input.fill('First follow-up')
  await expect(send).toBeEnabled()
  await input.press('Enter')
  await expect(replies).toHaveCount(2)
  const viewport = page.locator('.chat-scroll')
  expect(await viewport.evaluate((node) => node.scrollHeight > node.clientHeight + 80)).toBe(true)
  await viewport.evaluate((node) => {
    node.scrollTop = 0
  })
  await expect.poll(() => viewport.evaluate((node) => node.scrollTop)).toBe(0)
  await input.fill('Continue while I read the earlier response')
  await expect(send).toBeEnabled()
  await input.press('Enter')
  await expect(replies).toHaveCount(3)
  expect(await viewport.evaluate((node) => node.scrollTop)).toBeLessThanOrEqual(2)
  await viewport.evaluate((node) => {
    node.scrollTop = node.scrollHeight
  })
  await expect
    .poll(() => viewport.evaluate((node) => node.scrollHeight - node.scrollTop - node.clientHeight))
    .toBeLessThan(80)
  await input.fill('Now I am reading the latest reply')
  await expect(send).toBeEnabled()
  await input.press('Enter')
  await expect(replies).toHaveCount(4)
  await expect
    .poll(() => viewport.evaluate((node) => node.scrollHeight - node.scrollTop - node.clientHeight))
    .toBeLessThan(80)
})
