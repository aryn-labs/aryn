// Explicit opt-in: uses the real Studio API/Core/runtime and the selected gateway model.
// Never call a provider directly, install a mock route, or choose a fallback model.
import { chromium, expect } from '@playwright/test'
import { mkdir, writeFile } from 'node:fs/promises'
import { resolve } from 'node:path'
const model = process.argv[2]
const resumeUrl = process.argv[3]
if (!model) throw new Error('Supply an exact model from your configured 9Router catalog.')
const evidence = resolve('../../.local/chat-finalization')
await mkdir(evidence, { recursive: true })
const browser = await chromium.launch()
const context = await browser.newContext({ viewport: { width: 1440, height: 900 } })
const report = {
  model,
  live_response_received: false,
  follow_up_verified: false,
  refresh_verified: false,
  errors: [],
}
try {
  const page = await context.newPage()
  page.on('pageerror', (error) => report.errors.push(error.message))
  page.on('response', async (response) => {
    if (response.url().includes('/chat/') && response.status() >= 400) {
      const body = await response.json().catch(() => ({}))
      report.errors.push({
        status: response.status(),
        error_code: body.error_code ?? 'api_rejected',
      })
    }
  })
  await page.goto(resumeUrl ?? 'http://127.0.0.1:8710/')
  await page.waitForLoadState('networkidle')
  if (!resumeUrl) {
    await page.getByRole('combobox', { name: 'Model', exact: true }).selectOption(model)
    const input = page.locator('#home-goal')
    await input.fill('Jelaskan secara singkat mengapa pelangi terbentuk.')
    await expect(page.locator('.home-composer button[type="submit"]')).toBeEnabled()
    await input.press('Enter')
    const consent = page.getByRole('dialog')
    if (await consent.isVisible()) {
      report.first_use_consent = true
      await consent.getByRole('button', { name: /Setuju dan kirim|Agree and send/ }).click()
    }
    try {
      await Promise.race([
        page.waitForURL(/\/chat\/chat_[a-f0-9]+$/, { timeout: 75000 }),
        page
          .locator('[role="alert"]')
          .first()
          .waitFor({ state: 'visible', timeout: 75000 })
          .then(() => {
            throw new Error('Live model admission was rejected.')
          }),
      ])
    } catch {
      report.ui_error = await page.locator('[role="alert"]').allTextContents()
      throw new Error('Core did not accept a live conversation.')
    }
    report.conversation_url = page.url()
    const response = page.locator('.chat-message-assistant')
    await response.first().waitFor({ state: 'visible', timeout: 75000 })
    report.first_reply = await response.first().innerText()
    report.live_response_received = true
    const follow = page.locator('#chat-message')
    await follow.fill('Dari jawaban tadi, mengapa warna merah berada di bagian luar pelangi?')
    await expect(page.locator('.home-composer button[type="submit"]')).toBeEnabled()
    await follow.press('Enter')
    await response.nth(1).waitFor({ state: 'visible', timeout: 75000 })
    report.follow_up_reply = await response.nth(1).innerText()
    report.follow_up_verified = true
    await page.reload()
  }
  const response = page.locator('.chat-message-assistant')
  const follow = page.locator('#chat-message')
  await response.nth(1).waitFor({ state: 'visible', timeout: 15000 })
  report.refresh_verified = (await response.count()) === 2
  if (resumeUrl) {
    report.conversation_url = page.url()
    report.first_reply = await response.first().innerText()
    report.follow_up_reply = await response.nth(1).innerText()
    report.live_response_received = true
    report.follow_up_verified = true
    report.restored_existing_conversation = true
  }
  await follow.fill('Singkat saja: jadi warna apa yang paling luar?')
  await expect(page.locator('.home-composer button[type="submit"]')).toBeEnabled({ timeout: 15000 })
  await follow.press('Enter')
  await response.nth(2).waitFor({ state: 'visible', timeout: 75000 })
  report.resumed_reply = await response.nth(2).innerText()
  report.resume_verified = true
  report.consent_not_repeated = (await page.getByRole('dialog').count()) === 0
  await page.screenshot({ path: resolve(evidence, 'live-chat-1440-dark.png') })
} catch (error) {
  report.failure = error.message
  process.exitCode = 1
} finally {
  await writeFile(resolve(evidence, 'live-chat-result.json'), JSON.stringify(report, null, 2))
  await writeFile(
    resolve(evidence, `live-chat-${model.replace(/[^a-zA-Z0-9-]/g, '-')}-result.json`),
    JSON.stringify(report, null, 2),
  )
  console.log(JSON.stringify(report, null, 2))
  await context.close()
  await browser.close()
}
