import { z } from '@/lib/types/validation'
export { request } from '@/lib/api/client'
export { base, scoped, write, pageSchema } from '@/features/workflows/api'
const scope = {
  id: z.string(),
  organization_id: z.string(),
  project_id: z.string(),
  created_at: z.string(),
}
export const evidenceStates = [
  'SUPPORTED',
  'CONFLICTING',
  'INSUFFICIENT_EVIDENCE',
  'NOT_FOUND',
] as const
export const incidentStates = [
  'OPEN',
  'INVESTIGATING',
  'PROPOSED',
  'EXECUTING',
  'DEGRADED',
  'RECOVERED',
  'CLOSED',
  'OUTCOME_UNKNOWN',
] as const
export const contextSchema = z.object({
  organization_id: z.string(),
  project_id: z.string(),
  permissions: z.record(z.string(), z.boolean()),
})
export const sourceSchema = z.object({
  ...scope,
  title: z.string(),
  source_ref: z.object({
    kind: z.enum(['artifact', 'run', 'demo_observation', 'document']),
    id: z.string(),
  }),
  source_digest: z.string(),
  digest: z.string(),
  observed_at: z.string(),
  collected_at: z.string(),
  quality: z.string(),
  sanitized: z.boolean(),
  max_age_seconds: z.number(),
  integrity: z.enum(['VERIFIED', 'UNVERIFIED']),
  freshness: z.enum(['fresh', 'stale', 'unavailable']),
})
export const sourceDetailSchema = sourceSchema.extend({
  content: z.record(z.string(), z.unknown()),
})
export const itemSchema = z.object({
  source_id: z.string(),
  relationship: z.enum(['support', 'conflict', 'neutral']),
  integrity: z.enum(['VERIFIED', 'UNVERIFIED']),
  freshness: z.enum(['fresh', 'stale', 'unavailable']),
  observed_at: z.string().nullable(),
  collected_at: z.string().nullable(),
  excerpt: z.string(),
  reason: z.string(),
})
export const bundleSchema = z.object({
  ...scope,
  title: z.string(),
  hypothesis: z.object({
    question: z.string(),
    predicate: z.enum(['service_healthy', 'contains_text', 'run_completed']),
    text: z.string(),
    minimum_sources: z.number(),
    target_id: z.string().nullable(),
  }),
  source_ids: z.array(z.string()),
  source_digests: z.record(z.string(), z.string()),
  workflow_run_id: z.string().nullable(),
  status: z.enum(evidenceStates),
  abstention: z.string().nullable(),
  digest: z.string(),
  evaluation: z.object({
    status: z.enum(evidenceStates),
    abstention: z.string().nullable(),
    coverage: z.number(),
    required_coverage: z.number(),
    evaluated_at: z.string(),
    items: z.array(itemSchema),
  }),
})
export const linkSchema = z.object({
  ...scope,
  bundle_id: z.string(),
  reference_kind: z.enum(['run', 'artifact', 'workflow_run', 'incident', 'capsule', 'replay']),
  reference_id: z.string(),
})
export const fixtureSchema = z.object({
  ...scope,
  name: z.string(),
  disposable: z.literal(true),
  revision: z.number(),
  running: z.boolean(),
  blocking_fault: z.boolean(),
  updated_at: z.string(),
})
export const incidentSchema = z.object({
  ...scope,
  title: z.string(),
  target_id: z.string(),
  severity: z.string(),
  status: z.enum(incidentStates),
  revision: z.number(),
  owner_id: z.string(),
  updated_at: z.string(),
  bundle_id: z.string().nullable(),
  proposal_id: z.string().nullable(),
  execution_id: z.string().nullable(),
  verification_id: z.string().nullable(),
  capsule_id: z.string().nullable(),
  demo: z.literal(true),
})
export const proposalSchema = z.object({
  id: z.string(),
  action: z.literal('restart_demo'),
  target_id: z.string(),
  target_revision: z.number(),
  bundle_id: z.string(),
  bundle_digest: z.string(),
  payload_hash: z.string(),
  reason: z.string(),
  preconditions: z.string(),
  reversible_intent: z.string(),
  verification: z.object({
    kind: z.string(),
    require_running: z.boolean(),
    require_no_blocking_fault: z.boolean(),
  }),
})
export const capsuleSchema = z.object({
  ...scope,
  incident_id: z.string(),
  bundle_id: z.string(),
  digest: z.string(),
  recovered: z.literal(true),
  snapshot: z.object({ running: z.boolean(), blocking_fault: z.boolean() }),
  scenario_id: z.string(),
  scenario_version: z.string(),
})
export const incidentDetailSchema = incidentSchema.extend({
  fixture: fixtureSchema,
  timeline: z.array(
    z.object({
      id: z.string(),
      sequence: z.number(),
      event: z.string(),
      to_status: z.string(),
      actor_id: z.string(),
      created_at: z.string(),
      reference_id: z.string().nullable(),
    }),
  ),
  proposal: proposalSchema.nullable(),
  bundle: bundleSchema.nullable(),
  approval: z
    .object({
      approval_id: z.string(),
      payload_hash: z.string(),
      approved_by: z.string(),
      created_at: z.string(),
    })
    .nullable(),
  execution: z
    .object({
      id: z.string(),
      status: z.string(),
      payload_hash: z.string(),
      before_revision: z.number(),
      after_revision: z.number().nullable(),
      error_code: z.string().nullable(),
    })
    .nullable(),
  verification: z
    .object({
      id: z.string(),
      recovered: z.boolean(),
      digest: z.string(),
      target_revision: z.number(),
      observation_id: z.string(),
      created_at: z.string(),
    })
    .nullable(),
  capsule: capsuleSchema.nullable(),
})
export const graderSchema = z.object({
  grader_id: z.string(),
  grader_type: z.string(),
  grader_version: z.string(),
  passed: z.boolean(),
  state: z.string(),
  reason: z.string(),
  details: z.record(z.string(), z.unknown()),
})
export const scenarioSchema = z.object({
  scenario_id: z.string(),
  name: z.string(),
  category: z.string(),
  scenario_version: z.string().default('historical'),
  state: z.string().default('unverifiable'),
  passed: z.boolean(),
  score: z.number(),
  actual_output: z.string(),
  failure_reason: z.string().nullable(),
  latency_seconds: z.number(),
  model: z.string().nullable().optional(),
  runtime: z.record(z.string(), z.unknown()).nullable().optional(),
  total_tokens: z.number().default(0),
  grader_results: z.array(graderSchema).default([]),
  execution: z
    .object({
      run_id: z.string().nullable(),
      actual_model: z.string().nullable(),
      provider: z.string().nullable(),
      runtime_backend: z.string().nullable(),
      gateway: z.string().nullable(),
      trace_available: z.boolean(),
      usage: z
        .object({
          input_tokens: z.number(),
          output_tokens: z.number(),
          total_tokens: z.number(),
        })
        .nullable(),
      cost_usd: z.number().nullable(),
      resources: z.record(z.string(), z.number()).nullable(),
    })
    .nullable()
    .optional(),
})
export const evaluationSchema = z.object({
  id: z.string(),
  organization_id: z.string(),
  project_id: z.string(),
  blueprint_id: z.string(),
  blueprint_name: z.string(),
  version_id: z.string(),
  version_number: z.string(),
  version_status: z.string(),
  passed: z.boolean(),
  verified: z.boolean(),
  score: z.number(),
  total_scenarios: z.number(),
  passed_scenarios: z.number(),
  evaluated_at: z.string(),
  suite_id: z.string(),
  evaluation_version: z.string().nullable(),
  requested_model: z.string().nullable(),
  regression: z
    .object({ state: z.string(), reason: z.string(), promotion_blocked: z.boolean() })
    .nullable(),
})
export const regressionSchema = z.object({
  state: z.string(),
  reason: z.string(),
  promotion_blocked: z.boolean(),
  baseline_id: z.string().nullable(),
  candidate_score: z.number().nullable(),
  baseline_score: z.number().nullable(),
  score_delta: z.number().nullable(),
  critical_regressions: z.array(z.record(z.string(), z.unknown())),
  regressions: z.array(z.record(z.string(), z.unknown())),
  scenarios: z.array(
    z.object({
      scenario_id: z.string(),
      scenario_version: z.string(),
      baseline_state: z.string(),
      candidate_state: z.string(),
      candidate_reason: z.string().nullable(),
      regression: z.boolean(),
      critical: z.boolean(),
      graders: z.array(
        z.object({
          grader_id: z.string(),
          grader_type: z.string(),
          grader_version: z.string(),
          baseline_state: z.string(),
          candidate_state: z.string(),
          candidate_reason: z.string(),
          regression: z.boolean(),
          critical: z.boolean(),
        }),
      ),
    }),
  ),
  metrics: z.record(
    z.string(),
    z.object({
      state: z.enum(['comparable', 'unavailable', 'invalid']),
      baseline: z.number().nullable(),
      candidate: z.number().nullable(),
      delta: z.number().nullable(),
    }),
  ),
  provenance_differences: z.record(z.string(), z.unknown()),
  limitations: z.array(z.string()),
})
export const evaluationDetailSchema = evaluationSchema.extend({
  scenarios: z.array(scenarioSchema),
  provenance: z.record(z.string(), z.unknown()),
  regression: regressionSchema.nullable(),
  baseline: z
    .object({
      baseline_id: z.string(),
      evaluation: z.object({
        evaluation_id: z.string(),
        version_id: z.string(),
        version_number: z.string(),
        payload_hash: z.string(),
      }),
      suite_id: z.string(),
      suite_hash: z.string(),
      accepted_at: z.string(),
      accepted_by: z.string(),
      reason: z.string(),
      generation: z.number(),
    })
    .nullable(),
  current_evaluation: z.boolean(),
  promotion_eligible: z.boolean(),
})
export const replaySchema = z.object({
  ...scope,
  capsule_id: z.string(),
  capsule_digest: z.string(),
  scenario_id: z.string(),
  backend: z.literal('deterministic_in_memory'),
  model: z.null(),
  provider: z.null(),
  live_write_calls: z.literal(0),
  promotion_evidence: z.literal(false),
  passed: z.boolean(),
  graders: z.array(graderSchema),
  digest: z.string(),
})
export const replayDetailSchema = replaySchema.extend({ capsule: capsuleSchema })
export const suitesSchema = z.object({
  items: z.array(
    z.object({
      suite_id: z.string(),
      evaluation_version: z.string(),
      name: z.string(),
      description: z.string(),
      scenarios: z.array(
        z.object({
          scenario_id: z.string(),
          scenario_version: z.string(),
          name: z.string(),
          category: z.string(),
          graders: z.array(z.object({ grader_id: z.string(), type: z.string() })),
        }),
      ),
    }),
  ),
})
export type Source = z.infer<typeof sourceSchema>
export type Bundle = z.infer<typeof bundleSchema>
export type Incident = z.infer<typeof incidentDetailSchema>
export type Evaluation = z.infer<typeof evaluationDetailSchema>
export type Replay = z.infer<typeof replayDetailSchema>
