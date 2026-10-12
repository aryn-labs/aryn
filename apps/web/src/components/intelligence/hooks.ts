import { useState, useDeferredValue, useRef } from 'react'
import { useQuery, useInfiniteQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { useWorkspace } from '@/app/providers/WorkspaceProvider'
import { base, scoped, request, pageSchema, contextSchema } from '@/features/intelligence/api'
import { ApiError } from '@/lib/api/client'
import type { z } from '@/lib/types/validation'
export function useDialogFocus() {
  const target = useRef<HTMLElement | null>(null)
  return {
    onOpenAutoFocus: () => {
      target.current = document.activeElement instanceof HTMLElement ? document.activeElement : null
    },
    onCloseAutoFocus: (event: Event) => {
      event.preventDefault()
      if (target.current?.isConnected) target.current.focus()
      else document.getElementById('main-content')?.focus()
    },
  }
}
export function useCopy() {
  const { t } = useTranslation()
  return (key: string) => t('intelligence.' + key)
}

export function useIntelligenceContext(project: string) {
  const workspace = useWorkspace()
  return useQuery({
    queryKey: [
      'intelligence-context',
      workspace.context?.user.id,
      workspace.context?.organization.id,
      project,
    ],
    enabled: !!workspace.context?.projects.some((p) => p.id === project),
    retry: false,
    queryFn: async ({ signal }) =>
      scoped(
        await request(base(project) + '/intelligence/context', contextSchema, { signal }),
        workspace.context!.organization.id,
        project,
      ),
  })
}

export function useRecord<T extends { id: string; organization_id: string; project_id: string }>(
  project: string,
  path: string,
  id: string,
  schema: z.ZodType<T>,
) {
  const workspace = useWorkspace()
  return useQuery({
    queryKey: [
      'intelligence-record',
      workspace.context?.user.id,
      workspace.context?.organization.id,
      project,
      path,
      id,
    ],
    retry: false,
    enabled: !!id && !!workspace.context?.projects.some((p) => p.id === project),
    refetchOnWindowFocus: false,
    queryFn: async ({ signal }) => {
      const data = scoped(
        await request(base(project) + path + '/' + encodeURIComponent(id), schema, { signal }),
        workspace.context!.organization.id,
        project,
      )
      if (data.id !== id) throw new ApiError(502, 'errors.scope')
      return data
    },
  })
}

export function useCatalog<T extends { organization_id: string; project_id: string }>(
  path: string,
  schema: z.ZodType<T>,
  project: string,
  args: Record<string, string> = {},
  enabled = true,
) {
  const workspace = useWorkspace(),
    projects = workspace.context?.projects.filter((p) => !project || p.id === project) ?? []
  return useInfiniteQuery({
    queryKey: [
      'intelligence-catalog',
      workspace.context?.user.id,
      workspace.context?.organization.id,
      project,
      path,
      args,
    ],
    enabled: enabled && !!workspace.context,
    retry: false,
    initialPageParam: null as Record<string, string> | null,
    queryFn: async ({ signal, pageParam }) => {
      if (project && !projects.length) throw new ApiError(404, 'errors.scope')
      const pages = await Promise.all(
        projects
          .filter((p) => !pageParam || pageParam[p.id])
          .map(async (p) => {
            const data = await request(
              base(p.id) +
                path +
                '?' +
                new URLSearchParams({ ...args, limit: '25', after: pageParam?.[p.id] ?? '' }),
              pageSchema(schema),
              { signal },
            )
            return {
              items: data.items.map((item) =>
                scoped(item, workspace.context!.organization.id, p.id),
              ),
              next: data.next,
              project: p.id,
            }
          }),
      )
      return {
        items: pages.flatMap((p) => p.items),
        cursors: Object.fromEntries(pages.filter((p) => p.next).map((p) => [p.project, p.next!])),
      }
    },
    getNextPageParam: (last) => (Object.keys(last.cursors).length ? last.cursors : undefined),
  })
}

export function useFilters(initialProject = '') {
  const [project, setProject] = useState(initialProject),
    [q, setQ] = useState(''),
    [status, setStatus] = useState('')
  return { project, setProject, q, setQ, status, setStatus, term: useDeferredValue(q.trim()) }
}
