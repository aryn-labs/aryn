import { render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ChatMessages } from '../components/ChatMessages'
import { ModelPicker } from '../components/ModelPicker'
import { scoped, sendTurn, type Conversation } from '../lib/chat-api'

afterEach(() => vi.unstubAllGlobals())
const scope = { organization: 'test-org', project: 'test-project', user: 'test-user' }
const conversation: Conversation = {
  organization_id: 'test-org',
  project_id: 'test-project',
  id: 'test-conversation',
  title: 'Isolated conversation',
  model: 'test/model',
  revision: 1,
  status: 'completed',
  can_send: true,
  error_code: null,
  created_at: '2026-10-10T00:00:00Z',
  updated_at: '2026-10-10T00:00:00Z',
  streaming: false,
  cancellation: false,
  messages: [
    {
      id: 'test-message',
      role: 'assistant',
      created_at: '2026-10-10T00:00:00Z',
      content:
        '**Safe text**\n\n```js\nconsole.log("not executed")\n```\n\n<script>alert(1)</script>\n\n![tracking](https://example.org/track)\n\n[unsafe](javascript:alert(1))\n\n[reference](https://example.org)',
    },
  ],
}
describe('Chat safety and delivery contracts', () => {
  it('offers catalog candidates honestly and discloses the metered connection check', () => {
    render(
      <ModelPicker
        model="test/model"
        onModel={vi.fn()}
        capability={{
          organization_id: scope.organization,
          project_id: scope.project,
          models: [
            { id: 'test/model', name: 'Test candidate', available: false, verifiable: true },
            { id: 'test/rejected', name: 'Rejected model', available: false, verifiable: false },
          ],
          can_send: true,
          permitted: true,
          reason: null,
          remote_consent_required: true,
          streaming: false,
          cancellation: false,
          max_message_length: 4000,
        }}
      />,
    )
    expect(screen.getByRole('combobox', { name: 'Model' })).toBeEnabled()
    expect(screen.getByRole('option', { name: 'Test candidate' })).toBeInTheDocument()
    expect(screen.queryByRole('option', { name: 'Rejected model' })).toBeNull()
    expect(screen.queryByRole('checkbox')).toBeNull()
  })
  it('renders Markdown and code as inert content without HTML, tracking images or executable URLs', () => {
    const { container } = render(<ChatMessages conversation={conversation} />)
    expect(screen.getByText('Safe text')).toBeVisible()
    expect(container.querySelector('pre code')?.textContent).toContain('console.log')
    expect(container.querySelector('script, img, iframe')).toBeNull()
    expect(screen.getAllByRole('link')).toHaveLength(1)
    expect(screen.getByRole('link')).toHaveAttribute('rel', 'noopener noreferrer')
  })
  it('rejects cross-scope data', () => {
    expect(() => scoped({ ...conversation, project_id: 'another' }, scope)).toThrow(
      'does not belong',
    )
  })
  it('uses session credentials, CSRF and idempotency without accepting alternate conversation IDs', async () => {
    const fetch = vi.fn().mockResolvedValue(Response.json({ ...conversation, id: 'unexpected' }))
    vi.stubGlobal('fetch', fetch)
    const input = {
      message: 'Isolated input',
      model: 'test/model',
      expected_revision: 1,
      allow_remote_model: true,
      idempotency_key: 'test-request-unique',
    }
    await expect(sendTurn(scope, 'test-csrf', input, conversation.id)).rejects.toThrow(
      'Delivery could not be confirmed',
    )
    const options = fetch.mock.calls[0]?.[1] as RequestInit
    expect(options.credentials).toBe('same-origin')
    expect(options.headers).toHaveProperty('X-CSRF-Token', 'test-csrf')
    expect(JSON.parse(options.body as string)).toEqual(input)
  })
  it('never exposes provider error text or reports network ambiguity as success', async () => {
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValue(
          Response.json(
            { message: 'secret raw provider error', error_code: 'rate_limited' },
            { status: 429 },
          ),
        ),
    )
    const input = {
      message: 'Test',
      model: 'test/model',
      expected_revision: 0,
      allow_remote_model: true,
      idempotency_key: 'test-request-unique',
    }
    await expect(sendTurn(scope, 'test-csrf', input)).rejects.toThrow(/wait a minute/i)
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('transport details')))
    await expect(sendTurn(scope, 'test-csrf', input)).rejects.toThrow(
      'Delivery could not be confirmed',
    )
  })
})
