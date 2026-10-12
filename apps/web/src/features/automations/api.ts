import { z } from '@/lib/types/validation'
export { request } from '@/lib/api/client'
export { write, base, scoped, pageSchema } from '@/features/workflows/api'
export const scheduleSchema = z.object({
  kind: z.enum(['interval', 'daily', 'weekly', 'cron', 'webhook']),
  timezone: z.string(),
  start_at: z.string(),
  interval_minutes: z.number().int().min(1).max(10080),
  local_time: z.string(),
  weekdays: z.array(z.number().int().min(0).max(6)).min(1).max(7),
  cron_expression: z
    .string()
    .nullish()
    .transform((value) => value ?? null),
})
export const targetSchema = z.object({
  kind: z.enum(['agent', 'workflow']),
  id: z.string(),
  version_id: z.string(),
  payload_hash: z.string(),
  activation_id: z.string().nullable().optional(),
})
export const policySchema = z.object({
  overlap: z.enum(['skip', 'queue']),
  missed: z.enum(['skip', 'catch_up']),
  catch_up_limit: z.number().int().min(1).max(3),
  max_runs_per_day: z.number().int().min(1).max(100),
  max_tokens_per_task: z.number().int().min(128).max(32768),
  max_attempts: z.number().int().min(1).max(3),
  backoff_seconds: z.number().int().min(60).max(3600),
})
export const configurationSchema = z.object({
  title: z.string().min(1).max(160),
  target: targetSchema,
  input: z.string().min(1).max(8000),
  allow_remote_model: z.literal(true),
  schedule: scheduleSchema,
  policy: policySchema,
  expected_revision: z.number().nullable().optional(),
})
const scope = { organization_id: z.string(), project_id: z.string() }
export const definitionSchema = z.object({
  ...scope,
  id: z.string(),
  title: z.string(),
  target_label: z.string().nullable().optional(),
  owner_actor_id: z.string(),
  revision: z.number().int(),
  configuration: configurationSchema,
  payload_hash: z.string(),
  status: z.enum(['paused', 'enabled']),
  next_run_at: z.string(),
  last_occurrence_id: z.string().nullable(),
  created_at: z.string(),
  updated_at: z.string(),
  approval_verified: z.boolean().optional(),
  preview: z.array(z.object({ utc: z.string(), local: z.string() })).optional(),
  webhook: z.object({ id: z.string(), url: z.string() }).nullable().optional(),
})
export const occurrenceSchema = z.object({
  ...scope,
  id: z.string(),
  automation_id: z.string(),
  scheduled_at: z.string(),
  admitted_at: z.string().nullable(),
  completed_at: z.string().nullable(),
  definition_revision: z.number(),
  status: z.string(),
  attempts: z.number(),
  run_id: z.string().nullable(),
  run_kind: z.enum(['agent', 'workflow']),
  error_code: z.string().nullable(),
  retry_at: z.string().nullable(),
  created_at: z.string(),
})
export const eventSchema = z.object({
  ...scope,
  id: z.string(),
  automation_id: z.string(),
  event: z.string(),
  occurred_at: z.string().optional(),
  created_at: z.string(),
  occurrence_id: z.string().nullable().optional(),
})
export const targetsSchema = z.object({
  ...scope,
  items: z.array(
    z.object({
      target: targetSchema.nullable(),
      label: z.string(),
      available: z.boolean(),
      reason: z.string().nullable(),
    }),
  ),
  next: z.string().nullable(),
})
export const checkedTargetSchema = z.object({
  ...scope,
  target: targetSchema,
  available: z.literal(true),
  label: z.string(),
  reason: z.null(),
})
export const triggerSchema = z.object({
  ...scope,
  mode: z.enum(['local', 'hosted']),
  webhook_available: z.boolean(),
  webhook_reason: z.string().nullable(),
  webhook_authentication: z.string(),
  mcp_available: z.literal(false),
  kinds: z.array(z.string()),
  scheduler: z.object({
    authority: z.string(),
    last_tick_at: z.string().nullable(),
    error_code: z.string().nullable(),
  }),
})
export const previewSchema = z.object({
  instants: z.array(z.object({ utc: z.string(), local: z.string() })),
  dst_gap: z.string(),
  dst_fold: z.string(),
})
export type Configuration = z.infer<typeof configurationSchema>
export type Definition = z.infer<typeof definitionSchema>
export type Occurrence = z.infer<typeof occurrenceSchema>
export type TriggerCapabilities = z.infer<typeof triggerSchema>
