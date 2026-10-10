import { createContext, useContext, useState, useSyncExternalStore, type ReactNode } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { getSession } from '@/lib/auth/session'
import { request, ApiError } from '@/lib/api/client'
import { contextSchema, type WorkspaceContext } from '@/lib/types/workspace'
import { readPreference, savePreference } from '@/lib/utils'
type Workspace = {
  context?: WorkspaceContext
  project?: { id: string; name: string }
  loading: boolean
  error: Error | null
  selectProject: (id: string) => void
  retry: () => void
  csrf?: string
  signedOut: boolean
  clearSession: () => void
}
const WorkspaceContextValue = createContext<Workspace | null>(null)
export function WorkspaceProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient()
  const [projectId, setProjectId] = useState(() => readPreference('project'))
  const [signedOut, setSignedOut] = useState(false)
  const session = useQuery({
    queryKey: ['session'],
    queryFn: ({ signal }) => getSession(signal),
    enabled: !signedOut,
    staleTime: 20 * 60_000,
    retry: false,
  })
  const workspace = useQuery({
    queryKey: ['workspace-context'],
    queryFn: ({ signal }) => request('/api/workspace/context', contextSchema, { signal }),
    enabled: session.isSuccess && !signedOut,
    staleTime: 60_000,
    retry: false,
  })
  const denied = useSyncExternalStore(
    (callback) => queryClient.getQueryCache().subscribe(callback),
    () =>
      queryClient
        .getQueryCache()
        .getAll()
        .some(
          (query) =>
            query.state.error instanceof ApiError && [401, 403].includes(query.state.error.status),
        ),
  )
  // A server denial hides cached private identity and data until a fresh session/context succeeds.
  const context =
    !signedOut && !workspace.isError && !session.isError && !denied ? workspace.data : undefined
  const project = context?.projects.find((item) => item.id === projectId) ?? context?.projects[0]
  return (
    <WorkspaceContextValue.Provider
      value={{
        context,
        project,
        signedOut,
        csrf: session.data?.csrf,
        loading: !signedOut && (session.isPending || (session.isSuccess && workspace.isPending)),
        error:
          session.error ??
          workspace.error ??
          (denied
            ? new ApiError(403, 'ARYN Core denied access. Refresh your session to continue.')
            : null),
        selectProject(id) {
          if (context?.projects.some((item) => item.id === id)) {
            setProjectId(id)
            savePreference('project', id)
          }
        },
        retry() {
          queryClient.clear()
          setSignedOut(false)
          void session.refetch()
        },
        clearSession() {
          setSignedOut(true)
          queryClient.clear()
        },
      }}
    >
      {children}
    </WorkspaceContextValue.Provider>
  )
}
export function useWorkspace() {
  const context = useContext(WorkspaceContextValue)
  if (!context) throw new Error('WorkspaceProvider is required')
  return context
}
