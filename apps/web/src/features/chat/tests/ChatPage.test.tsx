import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { expect, it, vi } from 'vitest'
import { ChatPage } from '../ChatPage'

vi.mock('@tanstack/react-router', () => ({
  useParams: () => ({ conversationId: 'test-conversation' }),
  Link: () => null,
}))
vi.mock('@/app/providers/WorkspaceProvider', () => ({
  useWorkspace: () => ({
    loading: false,
    error: null,
    context: { user: { id: 'test-user' }, organization: { id: 'test-org' } },
  }),
}))

it('reports a missing accessible project instead of leaving a disabled query loading forever', () => {
  const client = new QueryClient()
  render(
    <QueryClientProvider client={client}>
      <ChatPage />
    </QueryClientProvider>,
  )
  expect(screen.getByRole('heading', { name: 'Select a project' })).toBeVisible()
  expect(screen.queryByText('Loading conversation')).not.toBeInTheDocument()
  client.clear()
})
