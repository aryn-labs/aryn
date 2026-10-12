import { z } from '@/lib/types/validation'
import { runSchema, versionSchema } from '@/features/workflows/api'
export { request } from '@/lib/api/client'
export { base, scoped, write } from '@/features/workflows/api'
export const runItemSchema = z.object({
  organization_id: z.string(),
  project_id: z.string(),
  id: z.string(),
  kind: z.enum(['agent', 'workflow']),
  name: z.string(),
  status: z.string(),
  source: z.string(),
  created_at: z.string(),
  completed_at: z.string().nullable(),
  duration_seconds: z.number().nullable(),
  verified: z.boolean(),
  references: z.record(z.string(), z.unknown()),
})
export const catalogSchema = z.object({
  organization_id: z.string(),
  project_id: z.string(),
  items: z.array(runItemSchema),
  next_cursor: z.string().nullable(),
})
export const detailSchema = runItemSchema.extend({
  timeline: z.array(z.record(z.string(), z.unknown())),
  io: z.object({ input: z.string().nullable(), output: z.string().nullable() }).nullable(),
  usage: z.record(z.string(), z.unknown()).nullable(),
  workflow_run: runSchema.nullable(),
  workflow_version: versionSchema.nullable(),
  permissions: z.record(z.string(), z.boolean()),
})
export type RunItem = z.infer<typeof runItemSchema>
export type Detail = z.infer<typeof detailSchema>
