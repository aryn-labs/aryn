import { describe, expect, it } from 'vitest'
import {
  connectionError,
  edgeState,
  graphErrors,
  initialGraph,
  nodeRegistry,
  nodeState,
} from '../registry'
import { draftSchema, lifecycleSchema, type Preview } from '../api'

const preview = (
  status: Preview['result']['status'],
  events: Preview['events'][number]['type'][],
): Preview => ({
  organization_id: 'org',
  project_id: 'project',
  blueprint_id: 'blueprint',
  working_copy_generation: 1,
  definition_hash: 'captured-hash',
  input: 'Isolated fixture',
  telemetry: 'core_lifecycle_only',
  cancellation_supported: false,
  result: {
    run_id: 'run',
    status,
    output: '',
    model: 'test/model',
    actual_model: null,
    provider: null,
    created_at: 1,
    completed_at: null,
    error_message: null,
    error_code: null,
    execution_claim_verified: true,
    output_reference: null,
    usage: {
      input_tokens: 0,
      output_tokens: 0,
      total_tokens: 0,
      availability: 'unavailable',
      cost_usd: null,
    },
  },
  events: events.map((type, sequence) => ({
    id: String(sequence),
    sequence,
    occurred_at: '2026-10-12T00:00:00Z',
    type,
    source: 'core_audit',
  })),
})
describe('agent configuration registry', () => {
  it('accepts the existing Bench integer boolean without accepting arbitrary truthy values', () => {
    const passed = lifecycleSchema.shape.evaluations.element.shape.passed
    expect(passed.parse(1)).toBe(true)
    expect(passed.parse(0)).toBe(false)
    expect(passed.parse(true)).toBe(true)
    expect(passed.safeParse('false').success).toBe(false)
    expect(passed.safeParse(2).success).toBe(false)
  })
  it('requires the minimal path and rejects mismatched, reversed, occupied and duplicate ports', () => {
    const graph = initialGraph()
    expect(graphErrors(graph)).toEqual([])
    expect(graphErrors({ ...graph, connections: [] })).toEqual(['incompletePath'])
    expect(
      connectionError(graph, {
        source: 'input',
        source_port: 'text',
        target: 'output',
        target_port: 'result',
      }),
    ).toBe('invalidConnection')
    expect(connectionError(graph, graph.connections[0]!)).toBe('duplicateConnection')
    expect(
      connectionError(graph, {
        source: 'agent',
        source_port: 'result',
        target: 'input',
        target_port: 'input',
      }),
    ).toBe('invalidConnection')
    const withBudget = {
      ...graph,
      nodes: [...graph.nodes, { id: 'budget', type: 'budget', x: 1, y: 1 } as const],
    }
    expect(
      connectionError(withBudget, {
        source: 'budget',
        source_port: 'policy',
        target: 'agent',
        target_port: 'policy',
      }),
    ).toBeNull()
    expect(
      connectionError(withBudget, {
        source: 'budget',
        source_port: 'policy',
        target: 'agent',
        target_port: 'input',
      }),
    ).toBe('invalidConnection')
  })
  it('does not claim runtime execution for policies or tools', () => {
    const running = preview('running', ['input.accepted', 'agent.dispatched'])
    expect(nodeState('input', running)).toBe('completed')
    expect(nodeState('agent', running)).toBe('running')
    expect(nodeState('output', running)).toBe('idle')
    for (const type of ['constraints', 'budget', 'tool-policy', 'evaluation'] as const) {
      expect(nodeState(type, running)).toBe('idle')
      expect(nodeRegistry[type].runtimeEvents).toEqual([])
    }
    expect('browser' in nodeRegistry).toBe(false)
    expect(
      edgeState(
        { source: 'budget', source_port: 'policy', target: 'agent', target_port: 'policy' },
        running,
      ),
    ).toBe('idle')
  })
  it('requires authenticated completion events before highlighting output', () => {
    expect(nodeState('output', preview('completed', ['input.accepted', 'agent.dispatched']))).toBe(
      'idle',
    )
    expect(
      nodeState(
        'output',
        preview('completed', ['input.accepted', 'agent.dispatched', 'run.completed']),
      ),
    ).toBe('completed')
    expect(nodeState('agent', preview('started', ['input.accepted']))).toBe('queued')
    for (const status of ['failed', 'outcome_unknown', 'cancelled'] as const) {
      expect(
        nodeState(
          'agent',
          preview(status, ['input.accepted', 'agent.dispatched', `run.${status}`]),
        ),
      ).toBe(status)
      expect(
        nodeState(
          'output',
          preview(status, ['input.accepted', 'agent.dispatched', `run.${status}`]),
        ),
      ).toBe('idle')
    }
    const forged = preview('completed', ['run.completed'])
    forged.result.execution_claim_verified = false
    expect(nodeState('output', forged)).toBe('idle')
  })
  it('keeps the draft grant boundary explicit in the client contract', () => {
    expect(draftSchema.shape.tool_grants.safeParse([]).success).toBe(true)
    expect(draftSchema.shape.tool_grants.safeParse(['browser']).success).toBe(false)
    expect(draftSchema.shape.tool_policy.shape.network_access.safeParse(true).success).toBe(false)
    expect(draftSchema.shape.model_policy.shape.allow_fallback.safeParse(true).success).toBe(false)
  })
})
