import { z } from '@/lib/types/validation'
import { request } from '@/lib/api/client'
import { pageSchema, resourceSchema, summarySchema } from '@/lib/types/workspace'

const scopeSchema = z.object({ organization_id: z.string(), project_id: z.string() })
export type HomeScope = { organizationId: string; projectId: string }
export const homeSummarySchema = summarySchema.extend({
  attention: z.array(
    z.object({
      code: z.string(),
      count: z.number().int().nonnegative(),
      description: z.string(),
      route: z.string(),
    }),
  ),
})
export const workflowSchema = scopeSchema.extend({
  id: z.string(),
  name: z.string(),
  revision: z.number().int().positive(),
})
export const workflowRunSchema = scopeSchema.extend({
  id: z.string(),
  workflow_id: z.string(),
  version_id: z.string(),
  status: z.enum([
    'running',
    'waiting_review',
    'completed',
    'rejected',
    'failed',
    'outcome_unknown',
    'cancelled',
  ]),
  error_code: z.string().nullable().optional(),
})
export const incidentSchema = scopeSchema.extend({
  id: z.string(),
  title: z.string(),
  target_id: z.string(),
  created_at: z.string(),
  updated_at: z.string(),
  status: z.enum([
    'OPEN',
    'INVESTIGATING',
    'PROPOSED',
    'EXECUTING',
    'DEGRADED',
    'RECOVERED',
    'CLOSED',
    'OUTCOME_UNKNOWN',
  ]),
  severity: z.enum(['low', 'medium', 'high']),
  demo: z.literal(true),
})
const regressionSchema = scopeSchema.extend({
  comparison_id: z.string(),
  blueprint_id: z.string(),
  candidate: z.object({ version_id: z.string(), evaluation_id: z.string() }),
  promotion_blocked: z.boolean(),
  reason: z.string(),
  compared_at: z.string(),
})
const versionSchema = z.object({
  id: z.string(),
  blueprint_id: z.string(),
  version_number: z.string(),
  status: z.string(),
  created_at: z.string(),
  integrity_valid: z.boolean(),
  regression: regressionSchema.nullable(),
})
export const lifecycleSchema = scopeSchema.extend({
  versions: z.array(versionSchema),
  permissions: z.record(z.string(), z.boolean()),
})
export const inventorySchema = <T extends z.ZodType>(item: T) =>
  z.object({ items: z.array(item), next: z.string().nullable() })
export type HomeSummary = z.infer<typeof homeSummarySchema>
export type HomeWorkflow = z.infer<typeof workflowSchema>
export type HomeWorkflowRun = z.infer<typeof workflowRunSchema>
export type HomeIncident = z.infer<typeof incidentSchema>
export type HomeLifecycle = z.infer<typeof lifecycleSchema>

export function assertScope(
  value: { organization_id: string; project_id: string },
  scope: HomeScope,
) {
  if (value.organization_id !== scope.organizationId || value.project_id !== scope.projectId)
    throw new Error('Home data belongs to a different workspace.')
}
export async function homeRequest<T>(
  scope: HomeScope,
  suffix: string,
  schema: z.ZodType<T>,
  signal: AbortSignal,
) {
  return request(`/api/projects/${encodeURIComponent(scope.projectId)}/${suffix}`, schema, {
    signal,
  })
}
export async function getHomeSummary(scope: HomeScope, signal: AbortSignal) {
  const data = await homeRequest(scope, 'summary', homeSummarySchema, signal)
  assertScope(data, scope)
  for (const item of [...data.latest_runs, ...data.latest_audits, ...data.review_candidates])
    assertScope(item, scope)
  return data
}
export async function getHomeAgents(scope: HomeScope, signal: AbortSignal) {
  const data = await homeRequest(
    scope,
    'resources/blueprints?limit=4&sort=newest',
    pageSchema,
    signal,
  )
  assertScope(data, scope)
  if (data.resource !== 'blueprints')
    throw new Error('Home returned a different resource collection.')
  data.items.forEach((item) => assertScope(item, scope))
  return data.items
}
export async function getHomeInventory<T extends z.ZodType>(
  scope: HomeScope,
  path: string,
  schema: T,
  signal: AbortSignal,
) {
  const data = await homeRequest(scope, path, inventorySchema(schema), signal)
  for (const value of data.items) assertScope(scopeSchema.parse(value), scope)
  return data.items
}
export async function getHomeLifecycle(scope: HomeScope, signal: AbortSignal) {
  const data = await homeRequest(scope, 'lifecycle?limit=8', lifecycleSchema, signal)
  assertScope(data, scope)
  for (const version of data.versions) {
    if (version.regression) {
      assertScope(version.regression, scope)
      if (
        version.regression.candidate.version_id !== version.id ||
        version.regression.blueprint_id !== version.blueprint_id
      )
        throw new Error('Bench comparison belongs to a different version.')
    }
  }
  return data
}
export { resourceSchema }
