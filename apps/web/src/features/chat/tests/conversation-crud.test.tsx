import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, render, renderHook, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactNode } from 'react'
import { afterEach, expect, it, vi } from 'vitest'
import i18n from '@/i18n'
import { ConversationActionDialog } from '../components/ConversationActionDialog'
import { ConversationMenu } from '../components/ConversationMenu'
import { useConversationChange } from '../hooks/useConversationChange'
import { changeConversation, chatKey, type HistoryItem } from '../lib/chat-api'

vi.mock('@/app/providers/WorkspaceProvider', () => ({
  useWorkspace: () => ({ csrf: 'test-csrf' }),
}))
afterEach(() => vi.unstubAllGlobals())
const scope = { user: 'owner', organization: 'org', project: 'project' }
const item: HistoryItem = {
  id: 'chat-one',
  title: 'Original title',
  model: 'test/model',
  updated_at: '2026-10-11T00:00:00Z',
  metadata_revision: 0,
  can_rename: true,
  can_delete: true,
}
const metadata = {
  id: item.id,
  title: 'Renamed title',
  organization_id: scope.organization,
  project_id: scope.project,
  metadata_revision: 1,
  deleted: false,
}
function fixture() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  )
  return { client, wrapper }
}

it('uses authenticated PATCH/DELETE with exact scope and rejects arbitrary responses', async () => {
  const fetch = vi.fn().mockResolvedValue(Response.json(metadata))
  vi.stubGlobal('fetch', fetch)
  const input = {
    title: metadata.title,
    expected_metadata_revision: 0,
    idempotency_key: 'test-metadata-request',
  }
  await expect(
    changeConversation(scope, 'csrf', item.id, 'PATCH', input, new AbortController().signal),
  ).resolves.toEqual(metadata)
  expect(fetch.mock.calls[0]?.[1]).toMatchObject({
    method: 'PATCH',
    credentials: 'same-origin',
    headers: { 'X-CSRF-Token': 'csrf' },
  })
  expect(JSON.parse(fetch.mock.calls[0]?.[1].body as string)).toEqual(input)
  fetch.mockResolvedValue(Response.json({ ...metadata, project_id: 'foreign' }))
  await expect(
    changeConversation(scope, 'csrf', item.id, 'PATCH', input, new AbortController().signal),
  ).rejects.toThrow(/could not be confirmed/i)
  fetch.mockResolvedValue(Response.json({ ...metadata, deleted: false }))
  await expect(
    changeConversation(scope, 'csrf', item.id, 'DELETE', input, new AbortController().signal),
  ).rejects.toThrow(/could not be confirmed/i)
  fetch.mockResolvedValue(Response.json({ message: 'private traceback' }, { status: 403 }))
  await expect(
    changeConversation(scope, 'csrf', item.id, 'DELETE', input, new AbortController().signal),
  ).rejects.toThrow(/denied/i)
})

it('updates title everywhere and removes deleted history/recent caches without crossing scope', async () => {
  const fetch = vi.fn().mockResolvedValue(Response.json(metadata))
  vi.stubGlobal('fetch', fetch)
  const { client, wrapper } = fixture()
  const history = {
    items: [item],
    next_cursor: null,
    organization_id: scope.organization,
    project_id: scope.project,
  }
  client.setQueryData([...chatKey(scope), 'history'], { pages: [history], pageParams: [''] })
  client.setQueryData([...chatKey(scope), 'recent'], history)
  client.setQueryData([...chatKey(scope), item.id], { messages: ['immutable'], ...item })
  const foreignKey = [...chatKey({ ...scope, project: 'foreign' }), 'recent']
  client.setQueryData(foreignKey, history)
  const deleted = vi.fn()
  const { result } = renderHook(() => useConversationChange(scope, deleted), { wrapper })
  act(() =>
    result.current.mutate({
      id: item.id,
      method: 'PATCH',
      input: { title: metadata.title, expected_metadata_revision: 0 },
    }),
  )
  await waitFor(() => expect(result.current.isSuccess).toBe(true))
  expect(client.getQueryData([...chatKey(scope), item.id])).toMatchObject({
    title: metadata.title,
    messages: ['immutable'],
  })
  expect(client.getQueryData([...chatKey(scope), 'recent'])).toMatchObject({
    items: [{ title: metadata.title }],
  })
  fetch.mockResolvedValue(Response.json({ ...metadata, metadata_revision: 2, deleted: true }))
  act(() =>
    result.current.mutate({
      id: item.id,
      method: 'DELETE',
      input: { expected_metadata_revision: 1 },
    }),
  )
  await waitFor(() => expect(deleted).toHaveBeenCalledWith(item.id))
  expect(client.getQueryData([...chatKey(scope), item.id])).toBeUndefined()
  expect(client.getQueryData([...chatKey(scope), 'recent'])).toMatchObject({ items: [] })
  expect(client.getQueryData([...chatKey(scope), 'history'])).toMatchObject({
    pages: [{ items: [] }],
  })
  expect(client.getQueryData(foreignKey)).toEqual(history)
  client.clear()
})

it('latches duplicate mutations and retries an unknown acknowledgement with the same key/body', async () => {
  const fetch = vi.fn().mockRejectedValue(new Error('network'))
  vi.stubGlobal('fetch', fetch)
  const { client, wrapper } = fixture()
  const { result, unmount } = renderHook(() => useConversationChange(scope, vi.fn()), { wrapper })
  const value = {
    id: item.id,
    method: 'PATCH' as const,
    input: { title: 'Saved title', expected_metadata_revision: 0 },
  }
  act(() => {
    result.current.mutate(value)
    result.current.mutate(value)
  })
  await waitFor(() => expect(result.current.uncertain).toBe(true))
  expect(fetch).toHaveBeenCalledTimes(1)
  act(() =>
    result.current.mutate({ ...value, input: { ...value.input, title: 'Different title' } }),
  )
  await waitFor(() => expect(result.current.isError).toBe(true))
  expect(fetch).toHaveBeenCalledTimes(1)
  act(() => result.current.retryOriginal())
  await waitFor(() => expect(fetch).toHaveBeenCalledTimes(2))
  expect(fetch.mock.calls[0]?.[1].body).toBe(fetch.mock.calls[1]?.[1].body)
  const signal = fetch.mock.calls[1]?.[1].signal as AbortSignal
  unmount()
  expect(signal.aborted).toBe(true)
  client.clear()
})

it('shows backend-authorized actions and hides them without permission', async () => {
  const user = userEvent.setup()
  const onAction = vi.fn()
  const { rerender } = render(<ConversationMenu item={item} onAction={onAction} />)
  await user.click(screen.getByRole('button', { name: /Manage conversation/ }))
  await user.click(screen.getByRole('menuitem', { name: 'Rename' }))
  expect(onAction).toHaveBeenCalledWith(expect.objectContaining({ item, mode: 'rename' }))
  rerender(
    <ConversationMenu
      item={{ ...item, can_delete: false, can_rename: false }}
      onAction={onAction}
    />,
  )
  expect(screen.queryByRole('button')).toBeNull()
})

it('validates a title, preserves it on denial and submits no message edits', async () => {
  const user = userEvent.setup()
  const fetch = vi.fn().mockResolvedValue(Response.json({}, { status: 409 }))
  vi.stubGlobal('fetch', fetch)
  const { client, wrapper } = fixture()
  render(
    <ConversationActionDialog
      action={{ item, mode: 'rename', trigger: null }}
      scope={scope}
      onClose={vi.fn()}
      onDeleted={vi.fn()}
      fallbackFocus={vi.fn()}
    />,
    { wrapper },
  )
  const input = screen.getByRole('textbox', { name: /Conversation/ })
  await waitFor(() => expect(input).toHaveFocus())
  await user.keyboard('{Enter}')
  expect(fetch).not.toHaveBeenCalled()
  await user.clear(input)
  await user.type(input, '   ')
  expect(screen.getByRole('button', { name: 'Save title' })).toBeDisabled()
  await user.clear(input)
  await user.type(input, 'New title')
  await user.click(screen.getByRole('button', { name: 'Save title' }))
  await waitFor(() => expect(screen.getByRole('alert')).toBeVisible())
  expect(input).toHaveValue('New title')
  expect(JSON.parse(fetch.mock.calls[0]?.[1].body as string)).toEqual({
    title: 'New title',
    expected_metadata_revision: 0,
    idempotency_key: expect.any(String),
  })
  client.clear()
})

it('keeps a pending deletion visible until acknowledgement and disables dismissal controls', async () => {
  const user = userEvent.setup()
  let acknowledge: (value: Response) => void = () => undefined
  vi.stubGlobal(
    'fetch',
    vi.fn().mockImplementation(
      () =>
        new Promise<Response>((resolve) => {
          acknowledge = resolve
        }),
    ),
  )
  const { client, wrapper } = fixture()
  const close = vi.fn()
  render(
    <ConversationActionDialog
      action={{ item, mode: 'delete', trigger: null }}
      scope={scope}
      onClose={close}
      onDeleted={vi.fn()}
      fallbackFocus={vi.fn()}
    />,
    { wrapper },
  )
  await user.click(screen.getByRole('button', { name: /^Delete conversation$/ }))
  await waitFor(() => expect(screen.getByRole('button', { name: 'Close dialog' })).toBeDisabled())
  expect(screen.getByRole('button', { name: 'Cancel' })).toBeDisabled()
  await user.keyboard('{Escape}')
  expect(close).not.toHaveBeenCalled()
  act(() => acknowledge(Response.json({ ...metadata, deleted: true })))
  await waitFor(() => expect(close).toHaveBeenCalledOnce())
  client.clear()
})

it('confirms deletion explicitly, focuses Cancel and translates to Indonesian', async () => {
  await i18n.changeLanguage('id-ID')
  const user = userEvent.setup()
  const fetch = vi.fn()
  vi.stubGlobal('fetch', fetch)
  const { client, wrapper } = fixture()
  const close = vi.fn()
  render(
    <ConversationActionDialog
      action={{ item, mode: 'delete', trigger: null }}
      scope={scope}
      onClose={close}
      onDeleted={vi.fn()}
      fallbackFocus={vi.fn()}
    />,
    { wrapper },
  )
  expect(screen.getByText(/bukti eksekusi tetap disimpan/)).toBeVisible()
  await waitFor(() => expect(screen.getByRole('button', { name: 'Batal' })).toHaveFocus())
  await user.click(screen.getByRole('button', { name: 'Batal' }))
  expect(close).toHaveBeenCalledOnce()
  expect(fetch).not.toHaveBeenCalled()
  await i18n.changeLanguage('en-US')
  client.clear()
})
