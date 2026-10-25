import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, expect, test, vi } from 'vitest'
import { MutationDialog } from './IntelligenceUI'
import { write } from '@/features/intelligence/api'

vi.mock('@/features/intelligence/api', () => ({
  base: (project: string) => '/api/projects/' + project,
  write: vi.fn(),
}))
vi.mock('@/app/providers/WorkspaceProvider', () => ({
  useWorkspace: () => ({ csrf: 'explicit-test-csrf' }),
}))
vi.mock('./hooks', () => ({ useCopy: () => (key: string) => key, useDialogFocus: () => ({}) }))

beforeEach(() => vi.clearAllMocks())

test('pending Core cancellation stays reachable without aborting or duplicating the original mutation', async () => {
  const user = userEvent.setup(),
    cancellation = vi.fn(),
    close = vi.fn()
  let finish!: (value: unknown) => void
  vi.mocked(write).mockImplementation(
    () =>
      new Promise((resolve) => {
        finish = resolve
      }),
  )
  render(
    <MutationDialog
      title="Recovery"
      description="Exact Core action"
      project="project"
      path="/relay/incident/execute"
      body={{}}
      allowed
      onClose={close}
      onSuccess={() => {}}
      pendingActions={<button onClick={cancellation}>Cancel pending dispatch</button>}
    />,
  )
  expect(screen.queryByRole('button', { name: 'Cancel pending dispatch' })).not.toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: 'confirm' }))
  await user.click(screen.getByRole('button', { name: 'Cancel pending dispatch' }))
  expect(cancellation).toHaveBeenCalledOnce()
  expect(write).toHaveBeenCalledOnce()
  expect(close).not.toHaveBeenCalled()
  await act(async () => finish({ status: 'DEGRADED' }))
  await waitFor(() => expect(close).toHaveBeenCalledOnce())
})

test('denied mutation never exposes pending actions or submits a request', async () => {
  const user = userEvent.setup()
  render(
    <MutationDialog
      title="Denied"
      description="No authority"
      project="project"
      path="/relay/incident/execute"
      body={{}}
      allowed={false}
      onClose={() => {}}
      onSuccess={() => {}}
      pendingActions={<button>Cancel pending dispatch</button>}
    />,
  )
  await user.click(screen.getByRole('button', { name: 'confirm' }))
  expect(write).not.toHaveBeenCalled()
  expect(screen.queryByRole('button', { name: 'Cancel pending dispatch' })).not.toBeInTheDocument()
})
