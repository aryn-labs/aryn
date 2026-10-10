import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { afterEach, expect, it, vi } from 'vitest'
import { useLocalePreference } from '../hooks/useChatSettings'

vi.mock('@/app/providers/WorkspaceProvider', () => ({
  useWorkspace: () => ({ csrf: 'test-csrf' }),
}))
afterEach(() => vi.unstubAllGlobals())

function harness() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return {
    client,
    wrapper: ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    ),
  }
}

it('cancels a preference read authorized against the previous project', async () => {
  const fetch = vi.fn().mockImplementation(() => new Promise(() => {}))
  vi.stubGlobal('fetch', fetch)
  const { client, wrapper } = harness()
  const scope = { user: 'person', organization: 'org', project: 'project-a' }
  const { rerender, unmount } = renderHook(({ selected }) => useLocalePreference(selected), {
    initialProps: { selected: scope },
    wrapper,
  })
  await waitFor(() => expect(fetch).toHaveBeenCalledTimes(1))
  const signal = fetch.mock.calls[0]?.[1].signal as AbortSignal
  act(() => rerender({ selected: { ...scope, project: 'project-b' } }))
  await waitFor(() => expect(fetch).toHaveBeenCalledTimes(2))
  expect(signal.aborted).toBe(true)
  expect(fetch.mock.calls[1]?.[0]).toContain('/projects/project-b/chat/preferences')
  unmount()
  client.clear()
})

it('does not reuse the previous person or organization preference while loading', async () => {
  const fetch = vi
    .fn()
    .mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          organization_id: 'org',
          actor_id: 'person',
          locale: 'en-US',
        }),
      ),
    )
    .mockImplementation(() => new Promise(() => {}))
  vi.stubGlobal('fetch', fetch)
  const { client, wrapper } = harness()
  const scope = { user: 'person', organization: 'org', project: 'project' }
  const { result, rerender, unmount } = renderHook(
    ({ selected }) => useLocalePreference(selected),
    {
      initialProps: { selected: scope },
      wrapper,
    },
  )
  await waitFor(() => expect(result.current.data?.locale).toBe('en-US'))
  act(() => rerender({ selected: { ...scope, user: 'another-person' } }))
  expect(result.current.data).toBeUndefined()
  act(() => rerender({ selected: { ...scope, organization: 'another-org' } }))
  expect(result.current.data).toBeUndefined()
  unmount()
  client.clear()
})
