import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import i18n from '@/i18n'
import { ProjectsPage } from '../ProjectsPage'
import { ProjectDialog } from '../components/ProjectDialog'
import { ProjectResourceDrawer } from '../components/ProjectResourceDrawer'
import { ResourceRows } from '../components/ResourceRows'
import { assertProjectScope, parseSelection, type ProjectResource } from '../lib/api'

const navigate = vi.fn(),
  selectProject = vi.fn()
vi.mock('@tanstack/react-router', () => ({
  useNavigate: () => navigate,
  Link: ({ children, className }: { children: ReactNode; className: string }) => (
    <a href="/projects/project" className={className}>
      {children}
    </a>
  ),
}))
vi.mock('@/app/providers/WorkspaceProvider', () => ({
  useWorkspace: () => ({
    csrf: 'test-csrf',
    context: {
      user: { id: 'owner' },
      organization: { id: 'org' },
      projects: [{ id: 'project', name: 'Project' }],
    },
    project: { id: 'project' },
    selectProject,
    loading: false,
    error: null,
  }),
}))
const scope = { user: 'owner', organization: 'org', project: 'project' }
const project = {
  id: 'project',
  organization_id: 'org',
  name: 'Project',
  slug: 'project',
  description: 'Objective',
  generation: 1,
  created_at: '2026-10-11T00:00:00Z',
  updated_at: '2026-10-11T00:00:00Z',
  can_edit: true,
}
const output: ProjectResource = {
  id: 'output',
  organization_id: 'org',
  project_id: 'project',
  name: 'Research',
  created_at: project.created_at,
  status: 'outcome_unknown',
  kind: 'artifact',
  format: 'website',
  verified: true,
  references: { workflow_run_id: 'governed-run', digest: 'exact-digest' },
}
function mount(children: ReactNode) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  render(<QueryClientProvider client={client}>{children}</QueryClientProvider>)
  return client
}
beforeEach(async () => {
  vi.clearAllMocks()
  await i18n.changeLanguage('id-ID')
})
afterEach(() => vi.unstubAllGlobals())

it.each([true, false])(
  'shows empty inventory with effective create permission %s',
  async (canCreate) => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        Response.json({
          organization_id: 'org',
          project_id: '',
          items: [],
          next_cursor: null,
          can_create: canCreate,
        }),
      ),
    )
    mount(<ProjectsPage />)
    expect(
      await screen.findByRole('heading', { name: 'Mulai proyek pertama Anda' }),
    ).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Buat Proyek' }) !== null).toBe(canCreate)
    expect(screen.queryByText('Aktif')).not.toBeInTheDocument()
  },
)
it('does not classify an unavailable service as empty', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(Response.json({}, { status: 503 })))
  mount(<ProjectsPage />)
  expect(
    await screen.findByText('Layanan proyek belum tersedia. Kondisi ini bukan proyek kosong.'),
  ).toBeInTheDocument()
  expect(screen.queryByText('Mulai proyek pertama Anda')).not.toBeInTheDocument()
})
it('sends validated authenticated create and activates the acknowledged project', async () => {
  const fetch = vi.fn().mockResolvedValue(Response.json(project))
  vi.stubGlobal('fetch', fetch)
  const close = vi.fn(),
    user = userEvent.setup()
  mount(<ProjectDialog onClose={close} />)
  await user.type(screen.getByLabelText(/Nama proyek/), 'New project')
  await user.click(screen.getByRole('button', { name: /^Buat Proyek$/ }))
  await waitFor(() =>
    expect(navigate).toHaveBeenCalledWith({
      to: '/projects/$projectId',
      params: { projectId: 'project' },
    }),
  )
  expect(fetch.mock.calls[0]?.[1]).toMatchObject({
    method: 'POST',
    credentials: 'same-origin',
    headers: { 'X-CSRF-Token': 'test-csrf' },
  })
  expect(selectProject).toHaveBeenCalledWith('project')
  expect(close).toHaveBeenCalledOnce()
})
it('retains failed edit input and idempotency identity until the input changes', async () => {
  const fetch = vi.fn().mockResolvedValue(Response.json({}, { status: 409 }))
  vi.stubGlobal('fetch', fetch)
  const user = userEvent.setup()
  mount(<ProjectDialog project={project} onClose={vi.fn()} />)
  const name = screen.getByLabelText(/Nama proyek/)
  await user.clear(name)
  await user.type(name, 'Retained name')
  await user.click(screen.getByRole('button', { name: 'Simpan Perubahan' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Nama sudah digunakan')
  expect(name).toHaveValue('Retained name')
  await user.click(screen.getByRole('button', { name: 'Simpan Perubahan' }))
  await waitFor(() => expect(fetch).toHaveBeenCalledTimes(2))
  const first = JSON.parse(fetch.mock.calls[0]?.[1].body as string),
    second = JSON.parse(fetch.mock.calls[1]?.[1].body as string)
  expect(first).toEqual(second)
  expect(first.expected_generation).toBe(1)
})
it('preserves unknown outcomes and opens rows by keyboard in both locales', async () => {
  const open = vi.fn(),
    user = userEvent.setup()
  mount(<ResourceRows items={[output]} onOpen={open} results />)
  await user.tab()
  await user.keyboard('{Enter}')
  expect(open).toHaveBeenCalledWith(output)
  expect(screen.getByText('Hasil perlu dipastikan')).toBeInTheDocument()
  await act(() => i18n.changeLanguage('en-US'))
  expect(screen.getByText('Outcome needs reconciliation')).toBeInTheDocument()
})
it('shows unsupported format provenance without executing or inventing a preview', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(Response.json(output)))
  mount(
    <ProjectResourceDrawer
      scope={scope}
      selection={{ id: 'output', kind: 'artifact' }}
      onClose={vi.fn()}
    />,
  )
  expect(await screen.findByText(/Viewer untuk format ini belum tersedia/)).toBeInTheDocument()
  expect(screen.getByText('governed-run')).toBeInTheDocument()
  expect(document.querySelector('iframe')).toBeNull()
})
it('rejects cross-scope responses and invalid deep link selectors', () => {
  expect(() =>
    assertProjectScope({ organization_id: 'foreign', project_id: 'project' }, scope),
  ).toThrow()
  expect(() => assertProjectScope({ organization_id: 'org', project_id: 'other' }, scope)).toThrow()
  expect(parseSelection('artifact:../secret')).toBeUndefined()
  expect(parseSelection('artifact:output')).toEqual({ kind: 'artifact', id: 'output' })
})
