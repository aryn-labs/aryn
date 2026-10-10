import { act, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient } from '@tanstack/react-query'
import { createMemoryHistory, RouterProvider } from '@tanstack/react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { AppProviders } from '@/app/providers/AppProviders'
import { createAppRouter } from '@/app/router'
import { getHomeAgents, getHomeInventory, getHomeLifecycle, workflowSchema } from '../lib/home-api'
import { homeFixture, type HomeScenario } from './fixtures'
import { runFixture } from '@/test/fixtures'

const clients: QueryClient[] = []
afterEach(() => {
  clients.forEach((client) => client.clear())
  clients.length = 0
  vi.unstubAllGlobals()
})
function mockHome(scenario: HomeScenario = 'new', writable = true) {
  const fetchMock = vi.fn(async (url: string, options?: RequestInit): Promise<Response> => {
    if (options?.signal?.aborted) throw new DOMException('Aborted', 'AbortError')
    const data = homeFixture(
      scenario,
      url.includes('project-two') ? 'project-two' : 'project-one',
      writable,
    )
    if (url === '/api/session') return Response.json({ csrf: 'test', mode: 'development' })
    if (url === '/api/workspace/context') return Response.json(data.context)
    if (url.endsWith('/summary')) return Response.json(data.summary)
    if (url.includes('resources/blueprints?'))
      return Response.json({
        organization_id: 'org-test',
        project_id: data.summary.project_id,
        resource: 'blueprints',
        items: data.agents,
        next_cursor: null,
        limit: 4,
        refreshed_at: data.summary.refreshed_at,
      })
    if (url.includes('/workflows?')) return Response.json({ items: data.workflows, next: null })
    if (url.includes('/relay?')) return Response.json({ items: data.incidents, next: null })
    if (url.includes('/review-queue?')) return Response.json({ items: data.reviews, next: null })
    if (url.includes('/lifecycle?')) return Response.json(data.lifecycle)
    if (url.endsWith('/workflows/workflow-one')) return Response.json(data.workflows[0])
    if (url.endsWith('/resources/blueprints/agent-one')) return Response.json(data.agents[0])
    if (url.endsWith('/resources/runs/run-test'))
      return Response.json({ ...runFixture, project_id: data.summary.project_id })
    return Response.json({}, { status: 404 })
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}
function renderHome() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })
  clients.push(client)
  const router = createAppRouter(createMemoryHistory({ initialEntries: ['/'] }))
  render(
    <AppProviders client={client}>
      <RouterProvider router={router} />
    </AppProviders>,
  )
  return { user: userEvent.setup(), client, router }
}
describe('Home overview interactions', () => {
  it('uses confirmed new workspace data without empty dashboards or recent lists', async () => {
    mockHome()
    renderHome()
    await screen.findByRole('heading', { name: 'Getting Started' })
    expect(screen.queryByRole('heading', { name: 'Continue Working' })).toBeNull()
    expect(screen.queryByRole('heading', { name: 'Recent Activity' })).toBeNull()
    expect(screen.queryByRole('heading', { name: 'Needs Your Attention' })).toBeNull()
    expect(screen.getByRole('button', { name: 'Create Agent' })).toBeEnabled()
    expect(screen.getByRole('button', { name: 'Continue' })).toBeDisabled()
  })
  it('shows active compact lists and opens actual workflow details with focus return', async () => {
    mockHome('active')
    const { user } = renderHome()
    const trigger = await screen.findByRole('button', { name: 'Inspect Research review' })
    expect(screen.getByRole('heading', { name: 'Continue Working' })).toBeVisible()
    expect(screen.queryByText('Getting Started')).toBeNull()
    await user.click(trigger)
    const drawer = screen.getByRole('dialog', { name: 'Resource details' })
    expect(await within(drawer).findByText('Revision')).toBeVisible()
    expect(within(drawer).getByText('3')).toBeVisible()
    await user.keyboard('{Escape}')
    expect(trigger).toHaveFocus()
  })
  it('places actionable attention before continued work and does not offer approval/retry shortcuts', async () => {
    mockHome('issues')
    renderHome()
    const attention = await screen.findByRole('heading', { name: 'Needs Your Attention' })
    const continued = screen.getByRole('heading', { name: 'Continue Working' })
    expect(
      attention.compareDocumentPosition(continued) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy()
    expect(screen.getAllByRole('button', { name: /^Inspect/ })).toHaveLength(8)
    expect(screen.queryByRole('button', { name: /^(Retry|Approve|Publish|Run agent)/ })).toBeNull()
  })
  it('opens an honest conversation and creates a draft only after explicit selection', async () => {
    const fetchMock = mockHome()
    const { user, router } = renderHome()
    await screen.findByText('Getting Started')
    await user.type(
      screen.getByRole('textbox', { name: 'Describe the agent or workflow you want to build' }),
      'Review research sources',
    )
    await user.keyboard('{Control>}{Enter}{/Control}')
    expect(screen.queryByRole('dialog')).toBeNull()
    expect(screen.getByText('Not sent')).toBeVisible()
    expect(screen.getByRole('heading', { name: 'Assistant unavailable' })).toBeVisible()
    expect(screen.getByRole('button', { name: 'Send' })).toBeDisabled()
    const followUp = screen.getByRole('textbox', { name: 'Follow-up message' })
    await user.type(followUp, 'Do not execute anything')
    await user.keyboard('{Control>}{Enter}{/Control}')
    expect(screen.getByRole('list', { name: 'Conversation messages' }).children).toHaveLength(1)
    await user.click(screen.getByRole('button', { name: 'Create Workflow draft' }))
    const drawer = screen.getByRole('dialog')
    expect(
      within(drawer).getByRole('textbox', { name: 'Describe the work (required)' }),
    ).toHaveValue('Review research sources')
    expect(within(drawer).getByRole('radio', { name: /Workflow Tasks/ })).toBeChecked()
    await user.type(
      within(drawer).getByRole('textbox', { name: 'Expected output' }),
      'Cited report',
    )
    await user.selectOptions(within(drawer).getByRole('combobox'), 'external')
    await user.type(
      within(drawer).getByRole('textbox', { name: 'Integration requirements' }),
      'Read access to approved knowledge sources',
    )
    await user.click(within(drawer).getByRole('button', { name: 'Review brief' }))
    expect(within(drawer).getByText('Cited report')).toBeVisible()
    await user.click(within(drawer).getByRole('button', { name: 'Open Workflow Builder' }))
    await waitFor(() => expect(router.state.location.pathname).toBe('/workflows'))
    expect(
      await screen.findByRole('heading', { name: 'Workflow Builder unavailable' }),
    ).toBeVisible()
    expect(screen.getByText('Review research sources')).toBeVisible()
    expect(router.state.location.search).toEqual({})
    expect([...Object.values(localStorage)]).not.toContain('Review research sources')
    expect(
      fetchMock.mock.calls.filter(
        ([url, options]) => url !== '/api/session' && options?.method && options.method !== 'GET',
      ),
    ).toHaveLength(0)
  })
  it('offers scratch creation without inventing a saved definition', async () => {
    mockHome()
    const { user } = renderHome()
    await user.click(await screen.findByRole('button', { name: 'Start from Scratch' }))
    await user.click(screen.getByRole('button', { name: 'Review brief' }))
    expect(screen.getAllByText('To be defined in Builder')).toHaveLength(2)
    await user.click(screen.getByRole('button', { name: 'Edit details' }))
    expect(screen.getByRole('textbox', { name: 'Describe the work' })).toHaveValue('')
  })
  it('returns to the overview with editable input and clears conversation on scope change', async () => {
    mockHome()
    const { user } = renderHome()
    await screen.findByText('Getting Started')
    const composer = screen.getByRole('textbox', {
      name: 'Describe the agent or workflow you want to build',
    })
    await user.type(composer, 'Private message for project one')
    await user.click(screen.getByRole('button', { name: 'Continue' }))
    expect(screen.queryByText('Getting Started')).toBeNull()
    await user.click(screen.getByRole('button', { name: 'Back to overview' }))
    expect(
      screen.getByRole('textbox', { name: 'Describe the agent or workflow you want to build' }),
    ).toHaveValue('Private message for project one')
    await user.click(screen.getByRole('button', { name: 'Continue' }))
    await user.click(screen.getByRole('button', { name: 'Switch workspace' }))
    await user.click(screen.getByRole('menuitemradio', { name: 'Second Project' }))
    await screen.findByText('Getting Started')
    expect(screen.queryByText('Private message for project one')).toBeNull()
    expect(
      screen.getByRole('textbox', { name: 'Describe the agent or workflow you want to build' }),
    ).toHaveValue('')
  })
  it('does not confuse viewing access with conversational or draft creation authority', async () => {
    const fetchMock = mockHome('new', false)
    const { user } = renderHome()
    await screen.findByText('Getting Started')
    await user.type(
      screen.getByRole('textbox', { name: 'Describe the agent or workflow you want to build' }),
      'A private question',
    )
    await user.click(screen.getByRole('button', { name: 'Continue' }))
    expect(screen.getByText('Not sent')).toBeVisible()
    expect(screen.getByRole('button', { name: 'Send' })).toBeDisabled()
    expect(screen.queryByRole('button', { name: /Create (Agent|Workflow) draft/ })).toBeNull()
    expect(
      fetchMock.mock.calls.filter(
        ([url, options]) => url !== '/api/session' && options?.method && options.method !== 'GET',
      ),
    ).toHaveLength(0)
  })
  it('shows friendly recorded activity and real agent information', async () => {
    const fetchMock = mockHome('active')
    const original = fetchMock.getMockImplementation()!
    fetchMock.mockImplementation((url, options) => {
      if (!url.endsWith('/summary')) return original(url, options)
      const data = homeFixture('active')
      data.summary.latest_audits = [
        {
          ...data.agents[0]!,
          id: 'audit-one',
          name: 'factory.blueprint.created',
          status: 'completed',
        },
      ]
      return Promise.resolve(Response.json(data.summary))
    })
    renderHome()
    await screen.findByRole('button', { name: 'Inspect Agent definition created' })
    expect(screen.queryByText('factory.blueprint.created')).toBeNull()
    const agent = screen.getByRole('button', { name: 'Inspect Research assistant' })
    expect(within(agent).getByText('Review sources and prepare a cited brief.')).toBeVisible()
    expect(within(agent).getByText(/^Created /)).toBeVisible()
  })
  it('identifies agent descriptions that the backend leaves blank without inventing one', async () => {
    const fetchMock = mockHome('active')
    const original = fetchMock.getMockImplementation()!
    fetchMock.mockImplementation(async (url, options) => {
      const response = await original(url, options)
      if (!url.includes('resources/blueprints?')) return response
      const data = await response.json()
      data.items[0].description = '   '
      return Response.json(data)
    })
    renderHome()
    const agent = await screen.findByRole('button', { name: 'Inspect Research assistant' })
    expect(within(agent).getByText('Agent definition · description not provided')).toBeVisible()
    expect(within(agent).queryByText('Review sources and prepare a cited brief.')).toBeNull()
  })
  it('uses effective permissions to disable creation and suppress inaccessible attention', async () => {
    mockHome('issues', false)
    renderHome()
    await screen.findByText('Continue Working')
    expect(screen.getByRole('button', { name: 'Create Agent' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Build Workflow' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Start from Scratch' })).toBeDisabled()
    expect(screen.queryByRole('button', { name: 'Inspect Version 1.0.1' })).toBeNull()
    expect(
      screen.queryByRole('button', { name: 'Inspect Disposable service needs review' }),
    ).toBeNull()
  })
  it('never treats a failed inventory request as a new workspace and recovers it', async () => {
    const fetchMock = mockHome()
    const original = fetchMock.getMockImplementation()!
    fetchMock.mockImplementation((url, options) =>
      url.includes('/workflows?')
        ? Promise.resolve(Response.json({}, { status: 503 }))
        : original(url, options),
    )
    const { user } = renderHome()
    await screen.findByText('Some workspace data is unavailable')
    expect(screen.queryByText('Getting Started')).toBeNull()
    fetchMock.mockImplementation(original)
    await user.click(screen.getByText('Some workspace data is unavailable'))
    await user.click(screen.getByRole('button', { name: 'Try again — Workflow definitions' }))
    expect(await screen.findByText('Getting Started')).toBeVisible()
  })
  it('shows unavailable services separately from an empty project', async () => {
    const fetchMock = mockHome()
    const original = fetchMock.getMockImplementation()!
    fetchMock.mockImplementation((url, options) =>
      url.includes('/relay?')
        ? Promise.resolve(Response.json({}, { status: 404 }))
        : original(url, options),
    )
    renderHome()
    await screen.findByText('Some workspace data is unavailable')
    expect(screen.queryByText('Getting Started')).toBeNull()
  })
  it('preserves available work during partial service failures without inventing empty lists', async () => {
    const fetchMock = mockHome('active')
    const original = fetchMock.getMockImplementation()!
    fetchMock.mockImplementation((url, options) =>
      /\/(workflows|relay|review-queue)\?/.test(url)
        ? Promise.resolve(Response.json({}, { status: 404 }))
        : original(url, options),
    )
    renderHome()
    await screen.findByText('Some workspace data is unavailable')
    expect(screen.getByRole('button', { name: 'Inspect Research assistant' })).toBeVisible()
    expect(screen.getByRole('heading', { name: 'Recent Activity' })).toBeVisible()
    expect(screen.queryByText('No workflow definitions yet.')).toBeNull()
    expect(screen.queryByText('Getting Started')).toBeNull()
  })
  it('cancels obsolete inventory requests on project change and never shows their data', async () => {
    const fetchMock = mockHome()
    const original = fetchMock.getMockImplementation()!
    let aborted = false
    fetchMock.mockImplementation((url, options) =>
      url.includes('/project-one/resources/blueprints?')
        ? new Promise((_, reject) => {
            options?.signal?.addEventListener('abort', () => {
              aborted = true
              reject(new DOMException('Aborted', 'AbortError'))
            })
          })
        : original(url, options),
    )
    const { user } = renderHome()
    await screen.findByText('Loading Home overview')
    await user.click(screen.getByRole('button', { name: 'Switch workspace' }))
    await user.click(screen.getByRole('menuitemradio', { name: 'Second Project' }))
    await screen.findByText('Getting Started')
    expect(aborted).toBe(true)
    expect(screen.queryByText('Research assistant')).toBeNull()
  })
  it('clears creation input and private details when project access is revoked', async () => {
    const fetchMock = mockHome()
    const { user, client } = renderHome()
    await user.click(await screen.findByRole('button', { name: 'Create Agent' }))
    await user.type(
      screen.getByRole('textbox', { name: 'Describe the work (required)' }),
      'Private idea',
    )
    fetchMock.mockImplementation(async () => Response.json({}, { status: 403 }))
    await act(async () => {
      await client.invalidateQueries({ queryKey: ['summary'] })
    })
    await screen.findAllByText('Access required')
    expect(screen.queryByRole('dialog')).toBeNull()
    expect(screen.queryByDisplayValue('Private idea')).toBeNull()
  })
})
describe('Home collection boundaries', () => {
  it('rejects a foreign item inside an otherwise correct agent envelope', async () => {
    const data = homeFixture('active')
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        Response.json({
          organization_id: 'org-test',
          project_id: 'project-one',
          resource: 'blueprints',
          items: [{ ...data.agents[0], project_id: 'foreign' }],
          next_cursor: null,
          limit: 4,
          refreshed_at: data.summary.refreshed_at,
        }),
      ),
    )
    await expect(
      getHomeAgents(
        { organizationId: 'org-test', projectId: 'project-one' },
        new AbortController().signal,
      ),
    ).rejects.toThrow('different workspace')
  })
  it('rejects foreign workflows even without a page envelope', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        Response.json({
          items: [{ ...homeFixture('active').workflows[0], organization_id: 'foreign' }],
          next: null,
        }),
      ),
    )
    await expect(
      getHomeInventory(
        { organizationId: 'org-test', projectId: 'project-one' },
        'workflows?limit=4',
        workflowSchema,
        new AbortController().signal,
      ),
    ).rejects.toThrow('different workspace')
  })
  it('rejects a Bench comparison from another version', async () => {
    const data = homeFixture('issues').lifecycle
    data.versions[0]!.regression.candidate.version_id = 'other-version'
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => Response.json(data)),
    )
    await expect(
      getHomeLifecycle(
        { organizationId: 'org-test', projectId: 'project-one' },
        new AbortController().signal,
      ),
    ).rejects.toThrow('different version')
  })
})
