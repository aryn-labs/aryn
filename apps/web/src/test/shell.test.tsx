import { act, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient } from '@tanstack/react-query'
import { RouterProvider, createMemoryHistory } from '@tanstack/react-router'
import { vi, describe, it, expect, afterEach } from 'vitest'
import { AppProviders } from '@/app/providers/AppProviders'
import { createAppRouter } from '@/app/router'
import { request, ApiError } from '@/lib/api/client'
import { contextSchema } from '@/lib/types/workspace'
import { contextFixture, runFixture, summaryFixture, statusFixture } from './fixtures'
const clients: QueryClient[] = []
afterEach(() => {
  clients.forEach((client) => client.clear())
  clients.length = 0
  vi.unstubAllGlobals()
})
function mockApi({
  contextStatus = 200,
  activity = false,
  empty = false,
  summaryStatus = 200,
  malformed = false,
} = {}) {
  const fetchMock = vi.fn(async (url: string, options?: RequestInit) => {
    if (options?.signal?.aborted) throw new DOMException('Aborted', 'AbortError')
    if (url === '/api/session') return Response.json({ csrf: 'test-csrf', mode: 'development' })
    if (url === '/api/workspace/context')
      return Response.json(
        contextStatus === 200
          ? { ...contextFixture, projects: empty ? [] : contextFixture.projects }
          : {},
        { status: contextStatus },
      )
    if (url === '/api/workspace/status') return Response.json(statusFixture)
    if (url.includes('/summary'))
      return Response.json(
        malformed
          ? { arbitrary: 'invalid' }
          : summaryFixture(url.includes('project-two') ? 'project-two' : 'project-one', activity),
        { status: summaryStatus },
      )
    if (url.endsWith('/runs/run-test')) return Response.json(runFixture)
    if (/\/(workflows|relay|review-queue)\?/.test(url))
      return Response.json({ items: [], next: null })
    return Response.json({
      organization_id: 'org-test',
      project_id: url.includes('project-two') ? 'project-two' : 'project-one',
      resource: url.includes('blueprints')
        ? 'blueprints'
        : url.includes('runs')
          ? 'runs'
          : 'projects',
      items: [],
      next_cursor: null,
      limit: 8,
      refreshed_at: '2026-10-09T12:00:00Z',
    })
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}
function renderShell(path = '/') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })
  clients.push(client)
  const router = createAppRouter(createMemoryHistory({ initialEntries: [path] }))
  render(
    <AppProviders client={client}>
      <RouterProvider router={router} />
    </AppProviders>,
  )
  return { user: userEvent.setup(), router, client }
}
describe('Studio shell', () => {
  it('bootstraps server session without identity input and renders honest empty states', async () => {
    const fetchMock = mockApi()
    renderShell()
    expect(await screen.findByText('Getting Started')).toBeVisible()
    expect(fetchMock.mock.calls[0]?.[0]).toBe('/api/session')
    expect(fetchMock.mock.calls[0]?.[1]).toMatchObject({
      method: 'POST',
      credentials: 'same-origin',
    })
    expect(fetchMock.mock.calls[0]?.[1]?.body).toBeUndefined()
    expect(screen.queryByText('GPT-4o')).not.toBeInTheDocument()
  })
  it('changes project scope and keeps the validated selection on reload', async () => {
    const fetchMock = mockApi()
    const { user } = renderShell()
    await screen.findByText('Getting Started')
    await user.click(screen.getByRole('button', { name: 'Switch workspace' }))
    await user.click(screen.getByRole('menuitemradio', { name: 'Second Project' }))
    await waitFor(() =>
      expect(fetchMock.mock.calls.some(([url]) => url.includes('/project-two/summary'))).toBe(true),
    )
    expect(localStorage.getItem('aryn.shell.project')).toBe('project-two')
  })
  it('ignores an inaccessible project preference', async () => {
    localStorage.setItem('aryn.shell.project', 'outside-tenant')
    const fetchMock = mockApi()
    renderShell()
    await screen.findByText('Getting Started')
    expect(fetchMock.mock.calls.some(([url]) => url.includes('outside-tenant'))).toBe(false)
  })
  it('supports navigation, sidebar collapse and expansion', async () => {
    mockApi()
    const { user, router } = renderShell()
    await screen.findByText('Getting Started')
    await user.click(screen.getByRole('button', { name: 'Collapse sidebar' }))
    expect(screen.getByRole('complementary', { name: 'Workspace sidebar' })).toHaveClass(
      'is-collapsed',
    )
    const expand = screen.getByRole('button', { name: 'Expand sidebar' })
    expand.focus()
    await user.keyboard('{Enter}')
    expect(screen.getByRole('complementary', { name: 'Workspace sidebar' })).not.toHaveClass(
      'is-collapsed',
    )
    await user.click(
      within(screen.getAllByRole('navigation', { name: 'Primary navigation' })[0]!).getByRole(
        'link',
        { name: 'Agents' },
      ),
    )
    expect(await screen.findByText('Agents workspace is not available yet')).toBeVisible()
    expect(router.state.location.pathname).toBe('/agents')
  })
  it('does not restore the removed context panel from a legacy preference', async () => {
    localStorage.setItem('aryn.shell.inspector', 'true')
    mockApi()
    const { user } = renderShell()
    await screen.findByText('Getting Started')
    expect(screen.queryByRole('complementary', { name: 'Context inspector' })).toBeNull()
    expect(screen.queryByRole('button', { name: /context inspector/i })).toBeNull()
    expect(screen.queryByRole('button', { name: 'View context' })).toBeNull()
    await user.click(screen.getByRole('button', { name: 'Account menu' }))
    expect(screen.queryByRole('menuitem', { name: /context inspector/i })).toBeNull()
  })
  it('opens global search using Ctrl+K, selects a route with keyboard, restores focus on Escape', async () => {
    mockApi()
    const { user, router } = renderShell()
    await screen.findByText('Getting Started')
    await user.keyboard('{Control>}k{/Control}')
    await user.type(screen.getByRole('combobox', { name: 'Search workspace' }), 'Bench')
    await user.keyboard('{Enter}')
    await waitFor(() => expect(router.state.location.pathname).toBe('/bench'))
    await user.keyboard('{Control>}k{/Control}')
    await user.keyboard('{Escape}')
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Global search' })).toHaveFocus()
  })
  it('inspects an actual returned resource and clears selection on project change', async () => {
    mockApi({ activity: true })
    const { user } = renderShell()
    await user.click(await screen.findByRole('button', { name: 'Inspect Recorded test run' }))
    expect(screen.getByRole('dialog', { name: 'Resource details' })).toBeVisible()
    expect(await screen.findByText('Verified by backend')).toBeVisible()
    await user.keyboard('{Escape}')
    expect(screen.queryByRole('dialog')).toBeNull()
    expect(screen.getByRole('button', { name: 'Inspect Recorded test run' })).toHaveFocus()
    await user.click(screen.getByRole('button', { name: 'Switch workspace' }))
    await user.click(screen.getByRole('menuitemradio', { name: 'Second Project' }))
    expect(screen.queryByRole('dialog')).toBeNull()
    expect(screen.queryByText('Verified by backend')).toBeNull()
  })
  it('keeps resource failure recoverable without exposing stale details', async () => {
    const fetchMock = mockApi({ activity: true })
    const originalFetch = fetchMock.getMockImplementation()!
    fetchMock.mockImplementation(async (url, options) =>
      url.endsWith('/runs/run-test')
        ? Response.json({}, { status: 503 })
        : originalFetch(url, options),
    )
    const { user } = renderShell()
    await user.click(await screen.findByRole('button', { name: 'Inspect Recorded test run' }))
    const dialog = screen.getByRole('dialog', { name: 'Resource details' })
    expect(await within(dialog).findByText('Unable to load data')).toBeVisible()
    expect(within(dialog).queryByText('Verified by backend')).toBeNull()
    await user.click(within(dialog).getByRole('button', { name: 'Close dialog' }))
    expect(screen.queryByRole('dialog')).toBeNull()
  })
  it('keeps the topbar minimal and loads runtime information only in Settings', async () => {
    const fetchMock = mockApi()
    const { user } = renderShell()
    await screen.findByText('Getting Started')
    const header = screen.getByRole('banner')
    expect(within(header).getByRole('button', { name: 'Switch workspace' })).toBeVisible()
    expect(within(header).getByRole('button', { name: 'Global search' })).toBeVisible()
    expect(screen.queryByRole('button', { name: 'Environment information' })).toBeNull()
    expect(screen.queryByRole('button', { name: 'Model information' })).toBeNull()
    expect(fetchMock.mock.calls.some(([url]) => url === '/api/workspace/status')).toBe(false)
    await user.click(screen.getByRole('button', { name: 'Notifications' }))
    expect(screen.getByText('Notifications unavailable')).toBeVisible()
    await user.keyboard('{Escape}')
    await user.click(screen.getByRole('button', { name: 'Account menu' }))
    await user.click(screen.getByRole('menuitem', { name: 'Use light theme' }))
    expect(document.documentElement).not.toHaveClass('dark')
    await user.click(screen.getAllByRole('link', { name: 'Settings' })[0]!)
    expect(await screen.findByText('Active model unavailable')).toBeVisible()
    expect(await screen.findByText('Runtime not ready')).toBeVisible()
    expect(fetchMock.mock.calls.some(([url]) => url === '/api/workspace/status')).toBe(true)
  })
  it('groups the current organization and authorized projects with a checked selection', async () => {
    mockApi()
    const { user } = renderShell()
    await screen.findByText('Getting Started')
    const trigger = screen.getByRole('button', { name: 'Switch workspace' })
    expect(trigger).toHaveAccessibleDescription(/Test Studio.*First Project/)
    await user.click(trigger)
    expect(screen.getByText('Organization switching unavailable.')).toBeVisible()
    expect(screen.getByRole('menuitemradio', { name: 'First Project' })).toHaveAttribute(
      'aria-checked',
      'true',
    )
    expect(screen.getByRole('menuitemradio', { name: 'Second Project' })).toHaveAttribute(
      'aria-checked',
      'false',
    )
    await user.click(screen.getByRole('menuitemradio', { name: 'Second Project' }))
    expect(trigger).toHaveAccessibleDescription(/Test Studio.*Second Project/)
    expect(trigger).toHaveFocus()
  })
  it('does not offer projects or request scoped data when the authorized list is empty', async () => {
    const fetchMock = mockApi({ empty: true })
    const { user } = renderShell()
    await screen.findByText('No accessible projects', { selector: 'h3' })
    await user.click(screen.getByRole('button', { name: 'Switch workspace' }))
    expect(screen.queryByRole('menuitemradio')).toBeNull()
    expect(screen.getByText('No accessible projects.')).toBeVisible()
    expect(fetchMock.mock.calls.some(([url]) => url.includes('/api/projects/'))).toBe(false)
  })
  it('rejects runtime data from another organization in Settings', async () => {
    const fetchMock = mockApi()
    const originalFetch = fetchMock.getMockImplementation()!
    fetchMock.mockImplementation(async (url, options) =>
      url === '/api/workspace/status'
        ? Response.json({ ...statusFixture, organization_id: 'outside-tenant' })
        : originalFetch(url, options),
    )
    renderShell('/settings')
    expect(
      (await screen.findAllByText('Status belongs to a different organization.')).length,
    ).toBeGreaterThan(0)
    expect(screen.queryByText('Runtime not ready')).toBeNull()
  })
  it.each([401, 403])('does not expose workspace data after server denial %s', async (status) => {
    mockApi({ contextStatus: status })
    renderShell()
    expect((await screen.findAllByText('Access required')).length).toBeGreaterThan(0)
    expect(screen.queryByText('Test Studio')).not.toBeInTheDocument()
    expect(screen.queryByText('Recorded test run')).not.toBeInTheDocument()
  })
  it('hides cached private data after a project denial', async () => {
    const fetchMock = mockApi({ activity: true })
    const { client } = renderShell()
    await screen.findByRole('button', { name: 'Inspect Recorded test run' })
    expect(screen.getAllByText('Test Studio').length).toBeGreaterThan(0)
    fetchMock.mockImplementation(async () => Response.json({}, { status: 403 }))
    await act(async () => {
      await client.invalidateQueries({ queryKey: ['summary'] })
    })
    await screen.findAllByText('Access required')
    expect(screen.queryByText('Test Studio')).not.toBeInTheDocument()
    expect(screen.queryByText('Recorded test run')).not.toBeInTheDocument()
  })
  it('shows an empty project state without issuing scoped requests', async () => {
    const fetchMock = mockApi({ empty: true })
    renderShell()
    await screen.findByText('No accessible projects', { selector: 'h3' })
    expect(fetchMock.mock.calls.some(([url]) => url.includes('/api/projects/'))).toBe(false)
  })
  it('rejects malformed backend contracts and offers recovery', async () => {
    mockApi({ malformed: true })
    renderShell()
    await screen.findAllByText('The API response does not match the workspace contract.')
    expect(screen.getAllByRole('button', { name: 'Try again' }).length).toBeGreaterThan(0)
  })
  it('renders an honest missing-route page', async () => {
    mockApi()
    renderShell('/does-not-exist')
    expect(await screen.findByRole('heading', { name: 'Page not found' })).toBeVisible()
  })
})
describe('API boundary', () => {
  it('sanitizes arbitrary proxy errors and accepts only the server login path', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        Response.json(
          { message: 'internal secret', login_url: 'https://external.invalid' },
          { status: 401 },
        ),
      ),
    )
    await expect(request('/api/workspace/context', contextSchema)).rejects.toEqual(
      new ApiError(401, 'Your session is unavailable or has expired.'),
    )
  })
  it('reports network unavailability', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => {
        throw new TypeError('network')
      }),
    )
    await expect(request('/api/workspace/context', contextSchema)).rejects.toMatchObject({
      status: 0,
    })
  })
})
