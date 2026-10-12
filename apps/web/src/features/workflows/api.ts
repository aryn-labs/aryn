import { z } from '@/lib/types/validation'
import { ApiError, request } from '@/lib/api/client'

export const kinds = ['start', 'agent', 'condition', 'handoff', 'review', 'end'] as const
export const schemas = ['text', 'brief', 'content', 'website'] as const
export const nodeSchema = z.object({
  id: z.string().regex(/^[a-zA-Z][a-zA-Z0-9_-]{0,47}$/),
  label: z.string().min(1).max(120),
  kind: z.enum(kinds),
  input_schema: z.enum(schemas),
  output_schema: z.enum(schemas),
  assignment_id: z.string().max(64).nullable(),
  agent_version_id: z.string().max(64).nullable(),
  renderer: z.literal('static-document-v1').nullable(),
  predicate: z
    .object({ operator: z.enum(['contains', 'equals', 'nonempty']), literal: z.string().max(100) })
    .nullable(),
})
export const edgeSchema = z.object({
  id: z.string().regex(/^[a-zA-Z][a-zA-Z0-9_-]{0,47}$/),
  source: z.string(),
  target: z.string(),
  source_port: z.enum(['value', 'yes', 'no']),
  target_port: z.literal('value'),
})
export const graphSchema = z.object({
  nodes: z.array(nodeSchema).max(24),
  edges: z.array(edgeSchema).max(32),
})
export const positionSchema = z.object({
  id: z.string(),
  x: z.number().min(-10000).max(10000),
  y: z.number().min(-10000).max(10000),
})
export const draftSchema = z.object({
  name: z.string().min(1).max(120),
  graph: graphSchema,
  positions: z.array(positionSchema).max(24),
})
const scope = { organization_id: z.string(), project_id: z.string() }
export const summarySchema = z.object({
  ...scope,
  id: z.string(),
  name: z.string(),
  revision: z.number().int().positive(),
})
export const definitionSchema = summarySchema.extend({
  graph: graphSchema,
  positions: z.array(positionSchema),
})
export const versionSummarySchema = z.object({
  ...scope,
  id: z.string(),
  workflow_id: z.string(),
  revision: z.number().int().positive(),
  digest: z.string().regex(/^[0-9a-f]{64}$/),
})
export const versionSchema = versionSummarySchema.extend({ graph: graphSchema })
export const taskSchema = z.object({
  node_id: z.string(),
  status: z.enum([
    'pending',
    'running',
    'completed',
    'waiting_review',
    'skipped',
    'failed',
    'outcome_unknown',
    'cancelled',
  ]),
  core_run_id: z.string().nullable(),
  input_artifact_id: z.string().nullable(),
  output_artifact_id: z.string().nullable(),
})
export const runSummarySchema = z.object({
  ...scope,
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
  artifact_id: z.string().nullable(),
  error_code: z.string().nullable(),
})
export const runSchema = runSummarySchema.extend({
  input: z.string(),
  cursor: z.string(),
  tasks: z.array(taskSchema),
  graph_digest: z.string().optional(),
  traversed_edges: z.array(z.string()).default([]),
})
export const artifactSchema = z.object({
  ...scope,
  id: z.string(),
  workflow_run_id: z.string(),
  task_id: z.string(),
  schema_name: z.enum(schemas),
  mime: z.enum(['application/json', 'text/html']),
  digest: z.string().regex(/^[0-9a-f]{64}$/),
  length: z.number().int().min(1).max(65536),
  source_artifact_id: z.string().nullable(),
  core_run_id: z.string().nullable(),
  agent_version_id: z.string().nullable(),
  model: z.string().nullable(),
  created_at: z.string(),
  validation: z.enum(['text-envelope', 'inert-static-document']),
  consumers: z.array(z.string()).optional(),
})
export const deliverableSchema = z.object({
  ...scope,
  id: z.string(),
  workflow_run_id: z.string(),
  artifact_id: z.string(),
  digest: z.string(),
  reviewer: z.string(),
  decision: z.enum(['accepted', 'rejected']),
  reason: z.string(),
  created_at: z.string(),
})
export const issueSchema = z.object({
  subject: z.string().max(64),
  code: z.string().regex(/^[a-z_]{1,64}$/),
})
export type Issue = z.infer<typeof issueSchema>
export type Node = z.infer<typeof nodeSchema>
export type Edge = z.infer<typeof edgeSchema>
export type Graph = z.infer<typeof graphSchema>
export type Definition = z.infer<typeof definitionSchema>
export type Draft = z.infer<typeof draftSchema>
export type Version = z.infer<typeof versionSchema>
export type Run = z.infer<typeof runSchema>
export type Artifact = z.infer<typeof artifactSchema>
export const targetSchema = z.object({
  id: z.string(),
  blueprint_id: z.string(),
  version_id: z.string(),
  name: z.string(),
  role_name: z.string(),
  version_number: z.string(),
  model: z.string(),
  eligible: z.boolean(),
  reason: z.string().nullable(),
})
export const targetsSchema = z.object({
  ...scope,
  items: z.array(targetSchema),
  next: z.string().nullable(),
  permissions: z.record(z.string(), z.boolean()),
})
export type Target = z.infer<typeof targetSchema>
export type Targets = z.infer<typeof targetsSchema>
export const pageSchema = <T extends z.ZodType>(item: T) =>
  z.object({ items: z.array(item), next: z.string().nullable() })
export const base = (project: string) => '/api/projects/' + encodeURIComponent(project)
export function scoped<T extends { organization_id: string; project_id: string }>(
  value: T,
  organization: string,
  project: string,
): T {
  if (value.organization_id !== organization || value.project_id !== project)
    throw new ApiError(502, 'errors.scope')
  return value
}
export class WorkflowError extends ApiError {
  constructor(
    status: number,
    public readonly issues: Issue[] = [],
  ) {
    super(
      status,
      status === 409 ? 'errors.conflict' : status === 403 ? 'errors.forbidden' : 'errors.generic',
    )
  }
}
export async function write<T>(
  url: string,
  body: unknown,
  schema: z.ZodType<T>,
  csrf: string,
  asynchronous = false,
): Promise<T> {
  let response: Response
  try {
    response = await fetch(url, {
      method: 'POST',
      credentials: 'same-origin',
      headers: {
        Accept: 'application/json',
        'Content-Type': 'application/json',
        'X-CSRF-Token': csrf,
        ...(asynchronous ? { Prefer: 'respond-async' } : {}),
      },
      body: JSON.stringify(body),
    })
  } catch {
    throw new WorkflowError(0)
  }
  const data: unknown = await response.json().catch(() => null)
  if (!response.ok) {
    const parsed = z
      .object({
        error_code: z.literal('workflow_graph_rejected'),
        issues: z.array(issueSchema).max(32),
      })
      .safeParse(data)
    throw new WorkflowError(response.status, parsed.success ? parsed.data.issues : [])
  }
  const parsed = schema.safeParse(data)
  if (!parsed.success) throw new WorkflowError(502)
  return parsed.data
}
export { request }
