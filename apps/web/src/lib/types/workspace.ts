import { z } from './validation'

export const identitySchema = z.object({ id: z.string(), name: z.string() })
export const contextSchema = z.object({
  organization: identitySchema,
  projects: z.array(identitySchema),
  user: identitySchema.extend({ role: z.string() }),
  mode: z.enum(['development', 'hosted', 'isolated-test']),
})
export const resourceSchema = z.object({
  id: z.string(),
  organization_id: z.string(),
  project_id: z.string(),
  name: z.string(),
  created_at: z.string(),
  status: z.string().nullable().optional(),
  description: z.string().nullable().optional(),
  verified: z.boolean().nullable().optional(),
  verification_reason: z.string().nullable().optional(),
  references: z.record(z.string(), z.unknown()).default({}),
})
export const metricSchema = z.object({
  value: z.number().nullable(),
  definition: z.string(),
  source: z.string(),
  verification: z.enum(['recorded_inventory', 'verified_bounded', 'unavailable']),
})
export const summarySchema = z.object({
  organization_id: z.string(),
  project_id: z.string(),
  refreshed_at: z.string(),
  metrics: z.record(z.string(), metricSchema),
  permissions: z.record(z.string(), z.boolean()),
  latest_runs: z.array(resourceSchema),
  latest_audits: z.array(resourceSchema),
  review_candidates: z.array(resourceSchema),
})
export const pageSchema = z.object({
  organization_id: z.string(),
  project_id: z.string(),
  resource: z.string(),
  items: z.array(resourceSchema),
  next_cursor: z.string().nullable(),
  refreshed_at: z.string(),
  limit: z.number(),
})
export const statusSchema = z.object({
  organization_id: z.string(),
  runtime: z.object({
    connected: z.boolean(),
    ready: z.boolean(),
    message: z.string(),
    readiness: z.string().optional(),
  }),
  models: z.array(
    z.object({
      model_id: z.string(),
      display_name: z.string(),
      availability: z.string().optional(),
    }),
  ),
})
export type WorkspaceContext = z.infer<typeof contextSchema>
export type ResourceItem = z.infer<typeof resourceSchema>
export type WorkspaceSummary = z.infer<typeof summarySchema>
export type Selection = {
  resource: 'runs' | 'audits' | 'blueprints' | 'projects'
  item: ResourceItem
}
