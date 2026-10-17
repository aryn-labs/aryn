import { z } from '@/lib/types/validation'
import { request, ApiError } from '@/lib/api/client'

export const nodeTypeSchema = z.enum([
  'input',
  'agent',
  'output',
  'constraints',
  'tool-policy',
  'budget',
  'evaluation',
])
export type NodeType = z.infer<typeof nodeTypeSchema>
export const graphSchema = z.object({
  schema_version: z.literal('1.0.0'),
  nodes: z.array(
    z.object({ id: nodeTypeSchema, type: nodeTypeSchema, x: z.number(), y: z.number() }),
  ),
  connections: z.array(
    z.object({
      source: nodeTypeSchema,
      source_port: z.enum(['text', 'result', 'policy']),
      target: nodeTypeSchema,
      target_port: z.enum(['input', 'result', 'policy']),
    }),
  ),
})
export type Graph = z.infer<typeof graphSchema>
export type CanvasNode = Graph['nodes'][number]
export type Connection = Graph['connections'][number]
export const viewportSchema = z.object({
  x: z.number(),
  y: z.number(),
  zoom: z.number().min(0.1).max(4),
})
export type Viewport = z.infer<typeof viewportSchema>
export const draftSchema = z.object({
  version_number: z
    .string()
    .regex(/^[0-9]+\.[0-9]+\.[0-9]+(?:-[a-z0-9.-]+)?$/)
    .max(32),
  system_prompt: z.string().min(20).max(12000),
  model: z.string().min(1).max(128),
  temperature: z.number().min(0).max(2),
  max_tokens: z.number().int().min(128).max(4096),
  tool_grants: z
    .array(z.string().regex(/^aryn_(?:native|mcp|https|github)_[a-z0-9_]{1,48}$/))
    .max(32),
  schema_version: z.literal('1.0.0'),
  role: z.string().min(1).max(64),
  objective: z.string().max(4000),
  owner: z.string().max(64).nullable(),
  metadata: z.record(z.string(), z.unknown()),
  output_contract: z.object({
    format: z.enum(['text', 'markdown', 'json']),
    schema_definition: z.record(z.string(), z.unknown()).nullable(),
    required_sections: z.array(z.string()),
    description: z.string().nullable(),
    strict: z.boolean(),
  }),
  constraints: z.object({
    disallowed_actions: z.array(z.string()),
    operational_rules: z.array(z.string()),
    require_evidence_citation: z.boolean(),
    max_execution_time_seconds: z.number().int().min(1).max(3600),
  }),
  tool_policy: z.object({
    tool_grants: z
      .array(z.string().regex(/^aryn_(?:native|mcp|https|github)_[a-z0-9_]{1,48}$/))
      .max(32),
    forbidden_tools: z.array(z.string()),
    deny_by_default: z.literal(true),
    network_access: z.literal(false),
    file_write_access: z.literal(false),
    code_execution: z.literal(false),
  }),
  model_policy: z.object({
    primary_model: z.string(),
    provider: z.string(),
    allowed_models: z.array(z.string()),
    temperature: z.number(),
    max_tokens: z.number(),
    allow_fallback: z.literal(false),
    stop_sequences: z.array(z.string()),
  }),
  budget_policy: z.object({
    max_tokens_per_run: z.number().int().min(1).max(100000),
    max_turns: z.number().int().min(1).max(100),
    max_cost_usd: z.number().min(0),
    timeout_seconds: z.number().int().min(1).max(3600),
  }),
  evaluation_reference: z.object({
    suite_id: z.string(),
    evaluation_version: z.string(),
    min_score_threshold: z.number().min(0).max(1),
    required_scenarios: z.array(z.string()),
    evaluation_id: z.string().nullable(),
  }),
})
export type Draft = z.infer<typeof draftSchema>
export const workingSchema = z.object({
  organization_id: z.string(),
  project_id: z.string(),
  blueprint_id: z.string(),
  generation: z.number().int(),
  definition: draftSchema.nullable(),
  source_version_id: z.string().nullable(),
  updated_at: z.string().nullable(),
})
export type WorkingCopy = z.infer<typeof workingSchema>
export const layoutSchema = z.object({
  generation: z.number().int(),
  positions: z.array(z.object({ id: z.string(), x: z.number(), y: z.number() })),
  viewport: viewportSchema,
  graph: graphSchema.nullable().default(null),
})
export type Layout = z.infer<typeof layoutSchema>
export const blueprintSchema = z.object({
  id: z.string(),
  organization_id: z.string(),
  project_id: z.string(),
  name: z.string(),
  slug: z.string(),
  objective: z.string().nullable().optional(),
  role: z.string().nullable().optional(),
  owner: z.string().nullable().optional(),
  description: z.string().nullable().optional(),
})
export const versionSchema = z
  .object({
    id: z.string(),
    blueprint_id: z.string(),
    version_number: z.string(),
    status: z.string(),
    payload_hash: z.string(),
    model: z.string(),
    configuration_loaded: z.boolean().optional(),
    integrity_valid: z.boolean().optional(),
    bench_eligible: z.boolean().optional(),
    governance_valid: z.boolean().optional(),
    evaluation_id: z.string().nullable().optional(),
    registry: z.object({ rollback_eligible: z.boolean() }).passthrough().optional(),
    regression: z
      .object({ promotion_blocked: z.boolean(), reason: z.string() })
      .passthrough()
      .nullable()
      .optional(),
  })
  .passthrough()
export type Version = z.infer<typeof versionSchema>
export const lifecycleSchema = z.object({
  organization_id: z.string(),
  project_id: z.string(),
  blueprints: z.array(blueprintSchema),
  versions: z.array(versionSchema),
  assignments: z.array(
    z
      .object({
        id: z.string(),
        blueprint_id: z.string(),
        version_id: z.string(),
        role_name: z.string(),
        status: z.string(),
        activation_verified: z.boolean(),
      })
      .passthrough(),
  ),
  evaluations: z.array(
    z
      .object({
        id: z.string(),
        version_id: z.string(),
        passed: z
          .union([z.boolean(), z.literal(0), z.literal(1)])
          .transform((value) => value === true || value === 1),
        score: z.number(),
        verified: z.boolean(),
        passed_scenarios: z.number().optional(),
        total_scenarios: z.number().optional(),
        evaluated_at: z.string().optional(),
        evaluation_version: z.string().optional(),
      })
      .passthrough(),
  ),
  evaluation_suites: z.array(
    z.object({ suite_id: z.string(), evaluation_version: z.string().optional() }).passthrough(),
  ),
  accepted_baselines: z.array(
    z.object({ baseline_id: z.string(), blueprint_id: z.string() }).passthrough(),
  ),
  permissions: z.record(z.string(), z.boolean()),
})
export type Lifecycle = z.infer<typeof lifecycleSchema>
export const capabilitiesSchema = z.object({
  organization_id: z.string(),
  project_id: z.string(),
  models: z.array(
    z.object({
      model_id: z.string(),
      display_name: z.string(),
      provider: z.string().optional(),
      availability: z.string().optional(),
    }),
  ),
  draft_defaults: draftSchema.nullable(),
  tools: z.array(z.unknown()),
  toolsets: z.array(z.object({ name: z.string(), tools: z.array(z.string()) })).optional(),
  skills: z
    .array(
      z.object({ name: z.string(), description: z.string(), content_hash: z.string().nullable() }),
    )
    .optional(),
  telemetry: z.literal('core_lifecycle_only'),
})
export type Capabilities = z.infer<typeof capabilitiesSchema>
export const previewSchema = z.object({
  organization_id: z.string(),
  project_id: z.string(),
  blueprint_id: z.string(),
  working_copy_generation: z.number(),
  definition_hash: z.string(),
  input: z.string(),
  result: z.object({
    run_id: z.string(),
    status: z.enum([
      'queued',
      'started',
      'running',
      'stopping',
      'completed',
      'failed',
      'cancelled',
      'outcome_unknown',
    ]),
    output: z.string(),
    model: z.string(),
    actual_model: z.string().nullable(),
    provider: z.string().nullable(),
    created_at: z.number(),
    completed_at: z.number().nullable(),
    error_message: z.string().nullable(),
    error_code: z.string().nullable(),
    execution_claim_verified: z.boolean(),
    output_reference: z.string().nullable(),
    usage: z.object({
      availability: z.enum(['measured', 'unavailable']),
      input_tokens: z.number(),
      output_tokens: z.number(),
      total_tokens: z.number(),
      cost_usd: z.number().nullable(),
    }),
  }),
  events: z.array(
    z.object({
      id: z.string(),
      sequence: z.number(),
      occurred_at: z.string(),
      type: z.enum([
        'input.accepted',
        'agent.dispatched',
        'run.completed',
        'run.failed',
        'run.outcome_unknown',
        'run.cancelled',
        'run.stopping',
      ]),
      source: z.literal('core_audit'),
    }),
  ),
  telemetry: z.literal('core_lifecycle_only'),
  cancellation_supported: z.boolean(),
})
export type Preview = z.infer<typeof previewSchema>
export const terminal = (status?: string) =>
  ['completed', 'failed', 'cancelled', 'outcome_unknown'].includes(status ?? '')
export const basePath = (project: string, blueprint?: string) =>
  `/api/projects/${encodeURIComponent(project)}${blueprint ? '/blueprints/' + encodeURIComponent(blueprint) : ''}`
export function scoped<T extends { organization_id: string; project_id: string }>(
  data: T,
  organization: string,
  project: string,
) {
  if (data.organization_id !== organization || data.project_id !== project)
    throw new ApiError(502, 'errors.scope')
  return data
}
export function post<T>(path: string, schema: z.ZodType<T>, csrf: string, body: unknown) {
  return request(path, schema, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf },
    body: JSON.stringify(body),
  })
}
