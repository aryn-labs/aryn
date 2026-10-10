import { useQuery } from '@tanstack/react-query'
import { request } from '@/lib/api/client'
import { resourceSchema, summarySchema, pageSchema, statusSchema } from '@/lib/types/workspace'
import { useWorkspace } from '@/app/providers/WorkspaceProvider'
export function useSummary() {
  const { project, context } = useWorkspace()
  return useQuery({
    queryKey: ['summary', context?.organization.id, project?.id],
    enabled: !!project,
    queryFn: async ({ signal }) => {
      const result = await request(
        `/api/projects/${encodeURIComponent(project!.id)}/summary`,
        summarySchema,
        { signal },
      )
      if (result.project_id !== project!.id || result.organization_id !== context!.organization.id)
        throw new Error('The summary belongs to a different workspace.')
      return result
    },
  })
}
export function useWorkspaceStatus(enabled = true) {
  const { context } = useWorkspace()
  return useQuery({
    queryKey: ['workspace-status', context?.organization.id],
    enabled: !!context && enabled,
    staleTime: 30_000,
    queryFn: async ({ signal }) => {
      const status = await request('/api/workspace/status', statusSchema, { signal })
      if (status.organization_id !== context!.organization.id)
        throw new Error('Status belongs to a different organization.')
      return status
    },
  })
}
export function useResources(resource: string, q: string, enabled: boolean) {
  const { project, context } = useWorkspace()
  return useQuery({
    queryKey: ['resources', context?.organization.id, project?.id, resource, q],
    enabled: !!project && enabled,
    queryFn: async ({ signal }) => {
      const page = await request(
        `/api/projects/${encodeURIComponent(project!.id)}/resources/${resource}?${new URLSearchParams({ q, limit: '8' })}`,
        pageSchema,
        { signal },
      )
      if (
        page.organization_id !== context!.organization.id ||
        page.project_id !== project!.id ||
        page.resource !== resource
      )
        throw new Error('Search returned a different scope.')
      return page
    },
  })
}
export function useResourceDetail(resource?: string, id?: string) {
  const { project, context } = useWorkspace()
  return useQuery({
    queryKey: ['detail', context?.organization.id, project?.id, resource, id],
    enabled: !!project && !!resource && !!id,
    queryFn: async ({ signal }) => {
      const item = await request(
        `/api/projects/${encodeURIComponent(project!.id)}/resources/${resource}/${encodeURIComponent(id!)}`,
        resourceSchema,
        { signal },
      )
      if (
        item.organization_id !== context!.organization.id ||
        item.project_id !== project!.id ||
        item.id !== id
      )
        throw new Error('The item belongs to a different scope.')
      return item
    },
  })
}
