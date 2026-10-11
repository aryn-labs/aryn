import { test, expect, type Page } from '@playwright/test'
import AxeBuilder from '@axe-core/playwright'
import { mkdir } from 'node:fs/promises'
import { resolve } from 'node:path'
const evidence = resolve('../../.local/conversation-crud')
test.beforeAll(async () => {
  await mkdir(evidence, { recursive: true })
})
async function openProject(page: Page, project: string) {
  await page.addInitScript((value) => localStorage.setItem('aryn.shell.project', value), project)
  await page.goto('/')
}
async function send(page: Page, title: string) {
  const input = page.getByRole('textbox', { name: 'Pesan untuk ARYN' })
  await input.fill(title)
  await expect(page.getByRole('button', { name: 'Kirim pesan', exact: true })).toBeEnabled()
  await input.press('Enter')
  const consent = page.getByRole('button', { name: 'Setuju dan kirim' })
  await expect
    .poll(async () => (await consent.isVisible()) || /\/chat\/chat_[a-f0-9]+$/.test(page.url()))
    .toBe(true)
  if (await consent.isVisible()) await consent.click()
  await expect(page).toHaveURL(/\/chat\/chat_[a-f0-9]+$/)
  return page.url().split('/').at(-1)!
}
async function history(page: Page) {
  await page.getByRole('button', { name: 'Riwayat percakapan', exact: true }).click()
  await expect(page.getByRole('dialog', { name: 'Riwayat percakapan', exact: true })).toBeVisible()
}
async function menu(page: Page, title: string, action: string) {
  const label = title.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  await page
    .getByRole('button', { name: new RegExp(`^Kelola percakapan: ${label}(?:…)?$`) })
    .click()
  await page.getByRole('menuitem', { name: action, exact: true }).click()
}
for (const width of [1920, 1440, 1024, 768, 390])
  for (const theme of ['dark', 'light']) {
    test(`conversation rename/delete, refresh, keyboard and retention ${width} ${theme}`, async ({
      page,
    }) => {
      const errors: string[] = []
      page.on('pageerror', (error) => errors.push(error.message))
      await page.setViewportSize({ width, height: 900 })
      await page.addInitScript((value) => localStorage.setItem('aryn.shell.theme', value), theme)
      await openProject(page, `browser-crud-${width}-${theme}`)
      const initial = `CRUD contract ${width} ${theme}`
      const id = await send(page, initial)
      await expect(page.locator('.chat-message-assistant')).toHaveCount(1)
      await history(page)
      await menu(page, initial, 'Ubah Nama')
      const dialog = page.getByRole('dialog', { name: 'Ubah Nama', exact: true })
      const title = dialog.getByRole('textbox', { name: 'Percakapan' })
      await expect(title).toBeFocused()
      const renamed = `Riset ${width} ${theme}`
      await title.fill(renamed)
      await page.keyboard.press('Tab')
      expect(await dialog.evaluate((node) => node.contains(document.activeElement))).toBe(true)
      await page.screenshot({ path: resolve(evidence, `rename-${width}-${theme}.png`) })
      await dialog.getByRole('button', { name: 'Simpan Nama' }).click()
      await expect(dialog).not.toBeVisible()
      await expect(
        page.getByRole('button', { name: `Kelola percakapan: ${renamed}`, exact: true }),
      ).toBeFocused()
      await page.keyboard.press('Escape')
      await expect(page.locator('.chat-subtitle')).toHaveText(renamed)
      await page.reload()
      await expect(page.locator('.chat-subtitle')).toHaveText(renamed)
      await page.getByRole('link', { name: 'Chat Baru', exact: true }).click()
      await expect(page.getByRole('link', { name: new RegExp(renamed) })).toBeVisible()
      await page.getByRole('link', { name: new RegExp(renamed) }).click()
      await history(page)
      await menu(page, renamed, 'Hapus Percakapan')
      const confirmation = page.getByRole('dialog', { name: 'Hapus Percakapan', exact: true })
      await expect(confirmation.getByRole('button', { name: 'Batal' })).toBeFocused()
      await confirmation.getByRole('button', { name: 'Batal' }).click()
      await expect(
        page.getByRole('button', { name: `Kelola percakapan: ${renamed}`, exact: true }),
      ).toBeFocused()
      await menu(page, renamed, 'Hapus Percakapan')
      await expect(confirmation.getByText(/bukti eksekusi tetap disimpan/)).toBeVisible()
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(
        true,
      )
      expect(
        (await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze())
          .violations,
      ).toEqual([])
      await page.screenshot({ path: resolve(evidence, `delete-${width}-${theme}.png`) })
      await confirmation.getByRole('button', { name: 'Hapus Percakapan', exact: true }).click()
      await expect(page).toHaveURL(/\/$/)
      await expect(page.getByRole('link', { name: new RegExp(renamed) })).toHaveCount(0)
      await page.reload()
      await expect(page.getByRole('link', { name: new RegExp(renamed) })).toHaveCount(0)
      expect(
        (
          await page.request.get(
            `/api/projects/browser-crud-${width}-${theme}/chat/conversations/${id}`,
          )
        ).status(),
      ).toBe(404)
      await page.goto(`/chat/${id}`)
      await expect(page.getByRole('alert')).toBeVisible()
      await expect(page.locator('.chat-message')).toHaveCount(0)
      await expect(page.getByRole('textbox', { name: 'Pesan untuk ARYN' })).toHaveCount(0)
      expect(errors).toEqual([])
    })
  }

test('rename acknowledgement lost: exact retry; English actions and deletion from inactive history', async ({
  page,
}) => {
  await openProject(page, 'browser-crud-retry')
  await send(page, 'Original retry conversation')
  await expect(page.locator('.chat-message-assistant')).toHaveCount(1)
  const bodies: string[] = []
  await page.route('**/chat/conversations/chat_*', async (route) => {
    if (route.request().method() !== 'PATCH') return route.continue()
    bodies.push(route.request().postData() ?? '')
    if (bodies.length !== 1) return route.continue()
    expect((await route.fetch()).status()).toBe(200)
    await route.abort('failed')
  })
  await history(page)
  await menu(page, 'Original retry conversation', 'Ubah Nama')
  const dialog = page.getByRole('dialog', { name: 'Ubah Nama', exact: true })
  await dialog.getByRole('textbox', { name: 'Percakapan' }).fill('Confirmed rename')
  await dialog.getByRole('button', { name: 'Simpan Nama' }).click()
  await expect(dialog.getByRole('alert')).toContainText('Perubahan belum dapat dipastikan')
  await expect(dialog.getByRole('textbox')).toHaveAttribute('readonly')
  await dialog.getByRole('button', { name: 'Coba ulang permintaan semula' }).click()
  await expect(dialog).not.toBeVisible()
  expect(bodies).toHaveLength(2)
  expect(bodies[0]).toBe(bodies[1])
  await page.keyboard.press('Escape')
  await page.goto('/settings')
  await page.getByRole('combobox', { name: 'Bahasa' }).selectOption('en-US')
  await page.goto('/')
  await page.getByRole('link', { name: /Confirmed rename/ }).click()
  await page.getByRole('button', { name: 'Conversation history', exact: true }).click()
  await page.getByRole('button', { name: 'Manage conversation: Confirmed rename' }).click()
  await expect(page.getByRole('menuitem', { name: 'Rename', exact: true })).toBeVisible()
  await page.getByRole('menuitem', { name: 'Delete conversation', exact: true }).click()
  await page
    .getByRole('dialog', { name: 'Delete conversation', exact: true })
    .getByRole('button', { name: 'Delete conversation', exact: true })
    .click()
  await expect(page).toHaveURL(/\/$/)
  await page.goto('/settings')
  await page.getByRole('combobox', { name: 'Language' }).selectOption('id-ID')
})

test('delete another conversation leaves the active chat and its messages intact', async ({
  page,
}) => {
  await openProject(page, 'browser-crud-inactive')
  const removed = await send(page, 'Earlier saved chat')
  await expect(page.locator('.chat-message-assistant')).toHaveCount(1)
  await page.getByRole('link', { name: 'Chat Baru', exact: true }).click()
  const active = await send(page, 'Active chat stays open')
  await expect(page.locator('.chat-message-assistant')).toHaveCount(1)
  await history(page)
  await menu(page, 'Earlier saved chat', 'Hapus Percakapan')
  await page
    .getByRole('dialog', { name: 'Hapus Percakapan', exact: true })
    .getByRole('button', { name: 'Hapus Percakapan', exact: true })
    .click()
  await expect(
    page.getByRole('button', { name: /Kelola percakapan: Earlier saved chat/ }),
  ).toHaveCount(0)
  await expect(page).toHaveURL(new RegExp(`/chat/${active}$`))
  await expect(page.getByRole('heading', { name: 'Riwayat percakapan', exact: true })).toBeFocused()
  await page.keyboard.press('Escape')
  await expect(page.locator('.chat-message-assistant')).toHaveCount(1)
  expect(
    (
      await page.request.get(`/api/projects/browser-crud-inactive/chat/conversations/${removed}`)
    ).status(),
  ).toBe(404)
})

test('History menu keyboard actions keep focus inside dialogs and restore the trigger', async ({
  page,
}) => {
  await openProject(page, 'browser-crud-keyboard')
  await send(page, 'Keyboard conversation')
  await expect(page.locator('.chat-message-assistant')).toHaveCount(1)
  await history(page)
  const trigger = page.getByRole('button', { name: /Kelola percakapan: Keyboard conversation/ })
  await trigger.focus()
  await trigger.press('ArrowDown')
  await expect(page.getByRole('menuitem', { name: 'Ubah Nama', exact: true })).toBeFocused()
  await page.keyboard.press('Enter')
  const rename = page.getByRole('dialog', { name: 'Ubah Nama', exact: true })
  await expect(rename.getByRole('textbox')).toBeFocused()
  await page.keyboard.press('Escape')
  await expect(trigger).toBeFocused()
  await trigger.press('ArrowDown')
  await page.keyboard.press('End')
  await expect(page.getByRole('menuitem', { name: 'Hapus Percakapan', exact: true })).toBeFocused()
  await page.keyboard.press('Enter')
  const cancel = page
    .getByRole('dialog', { name: 'Hapus Percakapan', exact: true })
    .getByRole('button', { name: 'Batal' })
  await expect(cancel).toBeFocused()
  await page.keyboard.press('Enter')
  await expect(trigger).toBeFocused()
})

test('in-flight response cannot restore a deleted conversation', async ({ page }) => {
  await openProject(page, 'browser-crud-inflight')
  const id = await send(page, 'Pending isolated response')
  await expect(page.getByText('ARYN sedang menulis respons…').first()).toBeVisible()
  await history(page)
  await menu(page, 'Pending isolated response', 'Hapus Percakapan')
  await page
    .getByRole('dialog', { name: 'Hapus Percakapan', exact: true })
    .getByRole('button', { name: 'Hapus Percakapan', exact: true })
    .click()
  await expect(page).toHaveURL(/\/$/)
  await expect
    .poll(
      async () => {
        const response = await page.request.get(
          '/api/projects/browser-crud-inflight/resources/runs',
        )
        const data = (await response.json()) as { items: { status: string }[] }
        return data.items[0]?.status
      },
      { timeout: 15_000 },
    )
    .toBe('completed')
  await page.reload()
  expect(
    (
      await page.request.get(`/api/projects/browser-crud-inflight/chat/conversations/${id}`)
    ).status(),
  ).toBe(404)
  await expect(page.getByRole('link', { name: /Pending isolated response/ })).toHaveCount(0)
})

test('session-bound API refuses cross-user and cross-project rename/delete and preserves failed input', async ({
  page,
}) => {
  await openProject(page, 'browser-crud-isolation')
  const id = await send(page, 'Scoped owner conversation')
  await expect(page.locator('.chat-message-assistant')).toHaveCount(1)
  const csrf = await page.evaluate(
    async () =>
      (
        (await (
          await fetch('/api/session', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: '{}',
          })
        ).json()) as { csrf: string }
      ).csrf,
  )
  for (const method of ['PATCH', 'DELETE']) {
    const body = {
      idempotency_key: `isolation-browser-${method}`,
      expected_metadata_revision: 0,
      ...(method === 'PATCH' ? { title: 'Forbidden rename' } : {}),
    }
    for (const path of [
      `/api/projects/browser-crud-isolation/chat/conversations/chat_browser_other_user`,
      `/api/projects/browser-crud-inactive/chat/conversations/${id}`,
    ]) {
      const result = await page.request.fetch(path, {
        method,
        headers: { 'X-CSRF-Token': csrf, Origin: 'http://127.0.0.1:8871' },
        data: body,
      })
      expect(result.status()).toBe(404)
    }
    expect(
      (
        await page.request.fetch(`/api/projects/browser-crud-isolation/chat/conversations/${id}`, {
          method,
          headers: { 'X-CSRF-Token': 'invalid', Origin: 'http://127.0.0.1:8871' },
          data: body,
        })
      ).status(),
    ).toBe(403)
  }
  await history(page)
  await menu(page, 'Scoped owner conversation', 'Ubah Nama')
  await page.route(`**/chat/conversations/${id}`, async (route) => {
    if (route.request().method() !== 'PATCH') return route.continue()
    await route.continue({ headers: { ...route.request().headers(), 'x-csrf-token': 'invalid' } })
  })
  const dialog = page.getByRole('dialog', { name: 'Ubah Nama', exact: true })
  await dialog.getByRole('textbox').fill('Draft stays after rejection')
  await dialog.getByRole('button', { name: 'Simpan Nama' }).click()
  // Real API rejection of an invalid CSRF token, without replacing its response.
  await expect(dialog.getByRole('alert')).toBeVisible()
  await expect(dialog.getByRole('textbox')).toHaveValue('Draft stays after rejection')
})
