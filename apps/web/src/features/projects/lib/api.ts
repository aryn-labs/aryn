import { z } from '@/lib/types/validation'
import { resourceSchema } from '@/lib/types/workspace'
import { ApiError, request } from '@/lib/api/client'

export const projectSchema = z.object({
  id: z.string(),
  organization_id: z.string(),
  name: z.string(),
  slug: z.string(),
  description: z.string(),
  generation: z.number().int().positive(),
  created_at: z.string(),
  updated_at: z.string(),
  can_edit: z.boolean().optional(),
})
export type Project = z.infer<typeof projectSchema>
export const projectsSchema = z.object({
  organization_id: z.string(),
  project_id: z.string(),
  items: z.array(
    resourceSchema.extend({ generation: z.number().int().positive(), slug: z.string() }),
  ),
  next_cursor: z.string().nullable(),
  can_create: z.boolean(),
})
export const kinds = [
  'workflow',
  'workflow-run',
  'run',
  'artifact',
  'evaluation',
  'assignment',
  'division',
  'member',
  'audit',
] as const
export const projectResourceSchema = resourceSchema.extend({
  kind: z.enum(kinds),
  format: z.string(),
  preview: z.object({ kind: z.literal('text'), text: z.string() }).optional(),
})
export type ProjectResource = z.infer<typeof projectResourceSchema>
export type Collection = 'work' | 'team' | 'results' | 'activity'
export const collectionSchema = z.object({
  organization_id: z.string(),
  project_id: z.string(),
  items: z.array(projectResourceSchema),
  next_cursor: z.string().nullable(),
  formats: z.array(z.string()),
})
export type Scope = { user: string; organization: string; project: string }
export const projectKey = (scope: Scope) => [
  'projects',
  scope.user,
  scope.organization,
  scope.project,
]
export function assertProjectScope<T extends { organization_id: string; project_id?: string }>(
  data: T,
  scope: Scope,
) {
  if (
    data.organization_id !== scope.organization ||
    (data.project_id !== undefined && data.project_id !== scope.project)
  )
    throw new ApiError(502, 'errors.scope')
  return data
}
export const path = (id: string) => '/api/projects/' + encodeURIComponent(id)
export type CollectionOptions = {
  cursor?: string | null
  q?: string
  format?: string
  limit?: number
  kind?: string
  active_only?: boolean
}
export function collectionRequest(
  scope: Scope,
  collection: Collection,
  signal: AbortSignal,
  options: CollectionOptions = {},
) {
  const query = new URLSearchParams({ limit: String(options.limit ?? 25) })
  if (options.q) query.set('q', options.q)
  if (options.format) query.set('format', options.format)
  if (options.cursor) query.set('cursor', options.cursor)
  if (options.kind) query.set('kind', options.kind)
  if (options.active_only) query.set('active_only', 'true')
  return request(
    path(scope.project) + '/project-resources/' + collection + '?' + query,
    collectionSchema,
    { signal },
  ).then((data) => assertProjectScope(data, scope))
}
export function selectionValue(item: Pick<ProjectResource, 'id' | 'kind'>) {
  return `${item.kind}:${item.id}`
}
export function parseSelection(value?: string) {
  const match =
    /^(workflow|workflow-run|run|artifact|evaluation|assignment|division|member|audit):([a-zA-Z0-9_-]{1,64})$/.exec(
      value ?? '',
    )
  return match?.[2] ? { kind: match[1] as ProjectResource['kind'], id: match[2] } : undefined
}
