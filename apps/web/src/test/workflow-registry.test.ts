import { describe, expect, it } from 'vitest'
import { draftSnapshot } from '@/features/workflows/editor-state'
import { draftSchema, runSchema, type Graph } from '@/features/workflows/api'
import {
  connectionIssue,
  checkpointTasks,
  edgeState,
  graphIssues,
  initialDraft,
  makeNode,
  registry,
} from '@/features/workflows/registry'
function executable() {
  const draft = initialDraft('Isolated workflow', {
    start: 'Start',
    agent: 'Agent',
    review: 'Review',
    end: 'End',
  })
  draft.graph.nodes[1] = {
    ...draft.graph.nodes[1]!,
    assignment_id: 'test-assignment',
    agent_version_id: 'test-published-version',
  }
  return draft
}
describe('Workflow domain graph', () => {
  it('detects actual edits without false unsaved changes after API serialization or layout ordering', () => {
    const draft = executable()
    const restored = {
      ...draft,
      positions: [...draft.positions].reverse(),
      graph: {
        ...draft.graph,
        edges: draft.graph.edges.map((edge) => ({
          target_port: edge.target_port,
          source_port: edge.source_port,
          target: edge.target,
          source: edge.source,
          id: edge.id,
        })),
      },
    }
    expect(draftSnapshot(restored)).toBe(draftSnapshot(draft))
    restored.positions[0] = { ...restored.positions[0]!, x: restored.positions[0]!.x + 1 }
    expect(draftSnapshot(restored)).not.toBe(draftSnapshot(draft))
  })
  it('saves incomplete drafts but requires a pinned assignment before execution', () => {
    const draft = initialDraft('Draft', {})
    expect(draftSchema.safeParse(draft).success).toBe(true)
    expect(graphIssues(draft.graph)).toContainEqual({
      subject: 'agent',
      code: 'invalid_node_configuration',
    })
    expect(graphIssues(executable().graph)).toEqual([])
    expect(
      draftSchema.safeParse({ name: 'Blank', graph: { nodes: [], edges: [] }, positions: [] })
        .success,
    ).toBe(true)
  })
  it('exposes only the six Core kinds and keeps condition ports typed', () => {
    expect(Object.keys(registry)).toEqual([
      'start',
      'agent',
      'condition',
      'handoff',
      'review',
      'end',
    ])
    expect(registry.condition.outputs).toEqual(['yes', 'no'])
    expect(makeNode('condition', 'Branch').predicate).toEqual({ operator: 'nonempty', literal: '' })
    expect(registry.handoff.runtime).toBe('verified artifact handoff')
    const condition = {
      ...makeNode('condition', 'Branch'),
      input_schema: 'brief' as const,
      output_schema: 'brief' as const,
    }
    expect(registry.condition.ports(condition).map((port) => [port.id, port.dataType])).toEqual([
      ['value', 'brief'],
      ['yes', 'brief'],
      ['no', 'brief'],
    ])
    expect(registry.agent.configurationSchema.safeParse(condition).success).toBe(false)
    expect(registry.agent.validate(makeNode('agent', 'Unconfigured'))).toContainEqual(
      expect.objectContaining({ code: 'invalid_node_configuration' }),
    )
  })
  it('rejects HTML input for text-only Agent and Condition handlers', () => {
    for (const kind of ['agent', 'condition'] as const) {
      const node = { ...makeNode(kind, 'HTML consumer'), input_schema: 'website' as const }
      expect(registry[kind].validate(node)).toContainEqual({
        subject: node.id,
        code: 'text_envelope_required',
      })
    }
  })
  it('rejects occupied, reversed, mismatched and cyclic connections', () => {
    const graph = executable().graph
    const invalid = (source: string, target: string) => ({
      source,
      target,
      source_port: 'value' as const,
      target_port: 'value' as const,
    })
    expect(connectionIssue(graph, invalid('start', 'review'))).toBe('bounded_ports_required')
    expect(connectionIssue(graph, invalid('end', 'agent'))).toBe('invalid_port')
    const changed: Graph = {
      ...graph,
      nodes: graph.nodes.map((n) =>
        n.id === 'review' ? { ...n, input_schema: 'brief', output_schema: 'brief' } : n,
      ),
      edges: graph.edges.filter((e) => e.source !== 'agent'),
    }
    expect(connectionIssue(changed, invalid('agent', 'review'))).toBe('incompatible_schema')
    const noAgentOutput = { ...graph, edges: graph.edges.filter((e) => e.source !== 'review') }
    expect(connectionIssue(noAgentOutput, invalid('review', 'agent'))).toBe('cycle')
  })
  it('does not admit review bypasses, orphans, duplicate identities, or invalid renderer targets', () => {
    const graph = executable().graph
    const bypass = {
      ...graph,
      edges: graph.edges.map((e) => (e.source === 'agent' ? { ...e, target: 'end' } : e)),
    }
    expect(graphIssues(bypass).some((i) => i.code === 'review_bypass')).toBe(true)
    expect(
      graphIssues({ ...graph, nodes: [...graph.nodes, makeNode('handoff', 'Orphan')] }).some(
        (i) => i.code === 'unreachable_node',
      ),
    ).toBe(true)
    expect(
      graphIssues({ ...graph, nodes: [...graph.nodes, graph.nodes[0]!] }).some(
        (i) => i.code === 'duplicate_identity',
      ),
    ).toBe(true)
    const renderer = {
      ...graph,
      nodes: graph.nodes.map((n) =>
        n.kind === 'agent' ? { ...n, renderer: 'static-document-v1' as const } : n,
      ),
    }
    expect(graphIssues(renderer).some((i) => i.code === 'invalid_node_configuration')).toBe(true)
  })
  it('requires recorded traversed edges rather than guessing a chosen branch from merged task states', () => {
    const run = runSchema.parse({
      organization_id: 'org',
      project_id: 'project',
      id: 'run',
      workflow_id: 'workflow',
      version_id: 'version',
      status: 'waiting_review',
      artifact_id: 'artifact',
      error_code: null,
      input: 'test',
      cursor: 'review',
      tasks: ['condition', 'review'].map((node_id) => ({
        node_id,
        status: node_id === 'condition' ? 'completed' : 'waiting_review',
        core_run_id: null,
        input_artifact_id: null,
        output_artifact_id: null,
      })),
      traversed_edges: ['edge_no'],
    })
    const yes = {
        id: 'edge_yes',
        source: 'condition',
        target: 'review',
        source_port: 'yes' as const,
        target_port: 'value' as const,
      },
      no = { ...yes, id: 'edge_no', source_port: 'no' as const }
    expect(edgeState(yes, run)).toBe('idle')
    expect(edgeState(no, run)).toBe('completed')
    expect(edgeState(no, { ...run, traversed_edges: [] })).toBe('idle')
    expect(
      checkpointTasks(
        { nodes: [], edges: [yes, no] },
        { ...run, tasks: [...run.tasks].reverse() },
      ).map((task) => task.node_id),
    ).toEqual(['condition', 'review'])
  })
})
