import { useInfiniteQuery, useQuery } from '@tanstack/react-query'
import { useWorkspace } from '@/app/providers/WorkspaceProvider'
import { request } from '@/lib/api/client'
import {
  assertProjectScope,
  collectionRequest,
  path,
  projectKey,
  projectSchema,
  projectsSchema,
  type Collection,
  type Scope,
  type CollectionOptions,
} from '../lib/api'

export function useProjectScope(project: string): Scope {
  const { context } = useWorkspace()
  return { user: context?.user.id ?? '', organization: context?.organization.id ?? '', project }
}
export function useProjects(q: string) {
  const scope = useProjectScope('')
  return useInfiniteQuery({
    queryKey: [...projectKey(scope), 'list', q],
    enabled: !!scope.organization,
    initialPageParam: null as string | null,
    retry: false,
    queryFn: async ({ signal, pageParam }) => {
      const params = new URLSearchParams({ q, limit: '25' })
      if (pageParam) params.set('cursor', pageParam)
      return assertProjectScope(
        await request('/api/projects?' + params, projectsSchema, { signal }),
        scope,
      )
    },
    getNextPageParam: (page) => page.next_cursor,
  })
}
export function useProject(projectId: string) {
  const scope = useProjectScope(projectId)
  return useQuery({
    queryKey: [...projectKey(scope), 'detail'],
    enabled: !!scope.organization && !!projectId,
    retry: false,
    queryFn: async ({ signal }) => {
      const data = await request(path(projectId), projectSchema, { signal })
      assertProjectScope(data, scope)
      if (data.id !== projectId) throw new Error('Project identity differs.')
      return data
    },
  })
}
export function useProjectCollection(
  scope: Scope,
  collection: Collection,
  options: CollectionOptions = {},
) {
  return useInfiniteQuery({
    queryKey: [...projectKey(scope), collection, options],
    enabled: !!scope.organization && !!scope.project,
    initialPageParam: null as string | null,
    retry: false,
    queryFn: ({ signal, pageParam }) =>
      collectionRequest(scope, collection, signal, { ...options, cursor: pageParam }),
    getNextPageParam: (page) => page.next_cursor,
  })
}
