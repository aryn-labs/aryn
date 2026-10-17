import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import { RuntimeControl } from './RuntimeControl'

const workspace = vi.hoisted(() => ({ role: 'admin', organization: 'org', project: 'project' }))
vi.mock('@/app/providers/WorkspaceProvider', () => ({
  useWorkspace: () => ({
    project: { id: workspace.project },
    csrf: 'test-csrf',
    context: { organization: { id: workspace.organization }, user: { role: workspace.role } },
  }),
}))
afterEach(() => {
  vi.unstubAllGlobals()
  workspace.role = 'admin'
})

function setup({ mismatched = false } = {}) {
  const replies = {
    supported: true,
    reason: 'discovered',
    administration_available: true,
    base_url: 'http://127.0.0.1:20128/v1',
    configuration_id: 'a'.repeat(64),
    credential_configured: true,
    connected: true,
    discovery_valid: true,
    runtime_binding_verified: true,
    models: [],
  }
  const fetch = vi.fn().mockImplementation((path: string) =>
    Promise.resolve(
      new Response(
        JSON.stringify(
          path.endsWith('/runtime')
            ? {
                organization_id: mismatched ? 'other-org' : 'org',
                project_id: 'project',
                attestation: 'signed',
                inventory: {
                  version: 'observed-runtime',
                  source_revision: null,
                  configuration_id: null,
                  reason: 'runtime_observed',
                  toolsets: [],
                  features: [],
                  skills: [],
                  settings: {},
                },
              }
            : path.endsWith('/native-tools')
              ? { configured: false, tools: [], bindings: [] }
              : replies,
        ),
      ),
    ),
  )
  vi.stubGlobal('fetch', fetch)
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const result = render(
    <QueryClientProvider client={client}>
      <RuntimeControl />
    </QueryClientProvider>,
  )
  return { fetch, client, ...result }
}

it('sends a replacement only to Core and clears the password after storage', async () => {
  const { fetch, unmount, client } = setup()
  const user = userEvent.setup()
  const password = await screen.findByLabelText('Replace API key')
  await user.type(password, 'synthetic-private-key')
  await user.click(screen.getByRole('button', { name: 'Replace connection' }))
  await waitFor(() => expect(password).toHaveValue(''))
  const call = fetch.mock.calls.find(([, options]) => options?.method === 'POST')
  expect(call?.[0]).toBe('/api/projects/project/model-connection')
  expect(JSON.parse(call?.[1].body)).toMatchObject({
    api_key: 'synthetic-private-key',
    expected_configuration_id: 'a'.repeat(64),
  })
  expect(localStorage.length).toBe(0)
  expect(
    JSON.stringify(
      client
        .getQueryCache()
        .getAll()
        .map((query) => query.state.data),
    ),
  ).not.toContain('synthetic-private-key')
  expect(fetch.mock.calls.every(([path]) => path.startsWith('/api/projects/'))).toBe(true)
  unmount()
  client.clear()
})

it('withholds administrative credential inputs from viewers', async () => {
  workspace.role = 'viewer'
  const { client, unmount } = setup()
  await screen.findByText('Runtime binding: verified')
  expect(screen.queryByLabelText('Replace API key')).not.toBeInTheDocument()
  expect(screen.getByText(/BLOCKED · Configure a reviewed/)).toBeInTheDocument()
  unmount()
  client.clear()
})

it('rejects an inventory from another organization instead of displaying it', async () => {
  const { client, unmount } = setup({ mismatched: true })
  await waitFor(() =>
    expect(screen.queryByText(/Version: observed-runtime/)).not.toBeInTheDocument(),
  )
  await waitFor(() =>
    expect(
      client.getQueryCache().find({ queryKey: ['runtime-inventory', 'org', 'project'] })?.state
        .status,
    ).toBe('error'),
  )
  unmount()
  client.clear()
})
