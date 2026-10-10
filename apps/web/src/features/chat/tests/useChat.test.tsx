import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { afterEach, expect, it, vi } from 'vitest'
import { useSendTurn } from '../hooks/useChat'

vi.mock('@/app/providers/WorkspaceProvider', () => ({
  useWorkspace: () => ({ csrf: 'test-csrf' }),
}))
afterEach(() => vi.unstubAllGlobals())

it('accepts only one submit before React has rendered pending state and cancels on unmount', async () => {
  const fetch = vi.fn().mockImplementation(() => new Promise(() => {}))
  vi.stubGlobal('fetch', fetch)
  const client = new QueryClient()
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  )
  const { result, unmount } = renderHook(
    () => useSendTurn({ user: 'user', organization: 'org', project: 'project' }),
    { wrapper },
  )
  const input = {
    message: 'One message',
    model: 'test/model',
    expected_revision: 0,
    allow_remote_model: false,
  }
  act(() => {
    result.current.mutate(input)
    result.current.mutate(input)
  })
  await waitFor(() => expect(fetch).toHaveBeenCalledTimes(1))
  const signal = fetch.mock.calls[0]?.[1].signal as AbortSignal
  expect(signal.aborted).toBe(false)
  unmount()
  expect(signal.aborted).toBe(true)
  client.clear()
})

it('freezes an uncertain delivery and retries the exact admitted input and idempotency key', async () => {
  const fetch = vi.fn().mockRejectedValue(new Error('network interrupted'))
  vi.stubGlobal('fetch', fetch)
  const client = new QueryClient({ defaultOptions: { mutations: { retry: false } } })
  const scope = { user: 'user', organization: 'org', project: 'project' }
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  )
  const { result } = renderHook(() => useSendTurn(scope), { wrapper })
  const input = {
    message: 'Original input',
    model: 'test/model',
    expected_revision: 0,
    allow_remote_model: true,
  }
  act(() => result.current.mutate(input))
  await waitFor(() => expect(result.current.uncertain).toBe(true))
  act(() => result.current.mutate({ ...input, message: 'Different input' }))
  await waitFor(() => expect(result.current.isError).toBe(true))
  expect(fetch).toHaveBeenCalledTimes(1)
  act(() => result.current.retryOriginal())
  await waitFor(() => expect(fetch).toHaveBeenCalledTimes(2))
  expect(fetch.mock.calls[0]?.[1].body).toBe(fetch.mock.calls[1]?.[1].body)
  client.clear()
})
