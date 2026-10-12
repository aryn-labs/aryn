import {
  ArrowDownToLine,
  Bot,
  GitBranch,
  ArrowRightLeft,
  ShieldCheck,
  Flag,
  type LucideIcon,
} from 'lucide-react'
import {
  nodeSchema,
  type Draft,
  type Edge,
  type Graph,
  type Issue,
  type Node,
  type Run,
} from './api'
import type { CanvasPort } from '@/app/studio/StudioCanvas'
const definitions: Record<
  Node['kind'],
  {
    icon: LucideIcon
    category: 'execution' | 'control'
    singleton: boolean
    inputs: boolean
    outputs: string[]
    inspector: Node['kind']
    permission: string
    runtime: string
  }
> = {
  start: {
    icon: ArrowDownToLine,
    category: 'control',
    singleton: true,
    inputs: false,
    outputs: ['value'],
    inspector: 'start',
    permission: 'version:create',
    runtime: 'Core input artifact',
  },
  agent: {
    icon: Bot,
    category: 'execution',
    singleton: false,
    inputs: true,
    outputs: ['value'],
    inspector: 'agent',
    permission: 'run:create',
    runtime: 'governed assignment or static-document-v1',
  },
  condition: {
    icon: GitBranch,
    category: 'control',
    singleton: false,
    inputs: true,
    outputs: ['yes', 'no'],
    inspector: 'condition',
    permission: 'version:create',
    runtime: 'typed Core predicate',
  },
  handoff: {
    icon: ArrowRightLeft,
    category: 'control',
    singleton: false,
    inputs: true,
    outputs: ['value'],
    inspector: 'handoff',
    permission: 'version:create',
    runtime: 'verified artifact handoff',
  },
  review: {
    icon: ShieldCheck,
    category: 'control',
    singleton: true,
    inputs: true,
    outputs: ['value'],
    inspector: 'review',
    permission: 'version:approve',
    runtime: 'exact artifact digest review',
  },
  end: {
    icon: Flag,
    category: 'control',
    singleton: true,
    inputs: true,
    outputs: [],
    inspector: 'end',
    permission: 'version:create',
    runtime: 'Core terminal checkpoint',
  },
}
function nodeIssues(node: Node): Issue[] {
  const issues: Issue[] = [],
    add = (code: string) => issues.push({ subject: node.id, code })
  if (!nodeSchema.safeParse(node).success) add('invalid_node_configuration')
  if (
    node.input_schema === 'website' &&
    (node.kind === 'condition' || (node.kind === 'agent' && !node.renderer))
  )
    add('text_envelope_required')
  if (
    node.kind === 'agent' &&
    (node.renderer
      ? node.input_schema !== 'content' ||
        node.output_schema !== 'website' ||
        !!node.assignment_id ||
        !!node.agent_version_id
      : !node.assignment_id || !node.agent_version_id || node.output_schema === 'website')
  )
    add('invalid_node_configuration')
  if (
    node.kind !== 'agent' &&
    (node.input_schema !== node.output_schema ||
      node.assignment_id ||
      node.agent_version_id ||
      node.renderer)
  )
    add('incompatible_schema')
  if ((node.kind === 'condition') !== !!node.predicate) add('invalid_node_configuration')
  return issues
}
export const registry = Object.fromEntries(
  Object.entries(definitions).map(([type, definition]) => [
    type,
    {
      ...definition,
      type,
      labelKey: 'workflows.' + type,
      configurationSchema: nodeSchema.refine((node) => node.kind === type),
      validate: nodeIssues,
      capabilityRequirements:
        type === 'agent'
          ? ['governed-assignment-or-static-renderer']
          : type === 'review'
            ? ['human-review']
            : [],
      permissionRequirements: [definition.permission],
      runtimeEventMapping: 'signed-workflow-task-checkpoint',
      ports: (node: Node): CanvasPort[] => [
        ...(definition.inputs
          ? [{ id: 'value', direction: 'in' as const, dataType: node.input_schema, y: 72 }]
          : []),
        ...definition.outputs.map((port, index) => ({
          id: port,
          direction: 'out' as const,
          dataType: node.output_schema,
          y: definition.outputs.length === 2 ? 54 + index * 44 : 72,
        })),
      ],
    },
  ]),
) as Record<
  Node['kind'],
  (typeof definitions)[Node['kind']] & {
    type: string
    labelKey: string
    configurationSchema: typeof nodeSchema
    validate: typeof nodeIssues
    capabilityRequirements: string[]
    permissionRequirements: string[]
    runtimeEventMapping: string
    ports: (node: Node) => CanvasPort[]
  }
>
export function makeNode(
  kind: Node['kind'],
  label: string,
  id = kind + '_' + crypto.randomUUID().replaceAll('-', '').slice(0, 12),
): Node {
  return {
    id,
    label,
    kind,
    input_schema: 'text',
    output_schema: 'text',
    assignment_id: null,
    agent_version_id: null,
    renderer: null,
    predicate: kind === 'condition' ? { operator: 'nonempty', literal: '' } : null,
  }
}
export function initialDraft(name: string, labels: Record<string, string>): Draft {
  const nodes = (['start', 'agent', 'review', 'end'] as const).map((kind) =>
    makeNode(kind, labels[kind] ?? kind, kind),
  )
  return {
    name,
    graph: {
      nodes,
      edges: nodes.slice(0, -1).map((node, i) => ({
        id: 'edge_' + i,
        source: node.id,
        target: nodes[i + 1]!.id,
        source_port: 'value',
        target_port: 'value',
      })),
    },
    positions: nodes.map((node, i) => ({ id: node.id, x: 60 + i * 300, y: 220 })),
  }
}
export function connectionIssue(graph: Graph, edge: Omit<Edge, 'id'>): string | null {
  const from = graph.nodes.find((n) => n.id === edge.source),
    to = graph.nodes.find((n) => n.id === edge.target)
  if (
    !from ||
    !to ||
    from.id === to.id ||
    !registry[from.kind].outputs.includes(edge.source_port) ||
    !registry[to.kind].inputs ||
    edge.target_port !== 'value'
  )
    return 'invalid_port'
  if (from.output_schema !== to.input_schema) return 'incompatible_schema'
  if (graph.edges.some((e) => e.source === edge.source && e.source_port === edge.source_port))
    return 'bounded_ports_required'
  if (graph.edges.length >= 32) return 'edge_limit'
  const pending = [to.id],
    seen = new Set<string>()
  while (pending.length) {
    const id = pending.pop()!
    if (id === from.id) return 'cycle'
    if (seen.has(id)) continue
    seen.add(id)
    pending.push(...graph.edges.filter((e) => e.source === id).map((e) => e.target))
  }
  return null
}
export function graphIssues(graph: Graph): Issue[] {
  const issues: Issue[] = [],
    add = (subject: string, code: string) => issues.push({ subject, code })
  if (
    new Set(graph.nodes.map((n) => n.id)).size !== graph.nodes.length ||
    new Set(graph.edges.map((e) => e.id)).size !== graph.edges.length
  )
    add('graph', 'duplicate_identity')
  for (const kind of ['start', 'review', 'end'])
    if (graph.nodes.filter((n) => n.kind === kind).length !== 1)
      add('graph', 'one_start_end_review_required')
  const tasks = graph.nodes.filter((n) => n.kind === 'agent')
  if (tasks.length < 1 || tasks.length > 8) add('graph', 'task_count_limit')
  for (const n of graph.nodes) {
    issues.push(...registry[n.kind].validate(n))
    const out = graph.edges.filter((e) => e.source === n.id)
    if (
      out
        .map((e) => e.source_port)
        .sort()
        .join(',') !== [...registry[n.kind].outputs].sort().join(',')
    )
      add(n.id, 'bounded_ports_required')
    if (
      n.kind === 'start'
        ? graph.edges.some((e) => e.target === n.id)
        : !graph.edges.some((e) => e.target === n.id)
    )
      add(n.id, 'orphan_or_invalid_start')
    if (
      n.kind === 'review' &&
      out.some((e) => graph.nodes.find((v) => v.id === e.target)?.kind !== 'end')
    )
      add(n.id, 'review_must_precede_end')
    if (n.kind === 'start' && n.output_schema !== 'text') add(n.id, 'input_requires_text')
  }
  for (const edge of graph.edges) {
    const code = connectionIssue(
      { ...graph, edges: graph.edges.filter((e) => e.id !== edge.id) },
      edge,
    )
    if (code) add(edge.id, code)
  }
  const seen = new Set<string>(),
    active = new Set<string>()
  function walk(id: string, reviewed: boolean) {
    if (active.has(id)) {
      add(id, 'cycle')
      return
    }
    const n = graph.nodes.find((node) => node.id === id)
    if (!n) {
      add(id, 'missing_node')
      return
    }
    seen.add(id)
    active.add(id)
    if (n.kind === 'end' && !reviewed) add(id, 'review_bypass')
    for (const edge of graph.edges.filter((e) => e.source === id))
      walk(edge.target, reviewed || n.kind === 'review')
    active.delete(id)
  }
  const start = graph.nodes.find((n) => n.kind === 'start')
  if (start) walk(start.id, false)
  if (graph.nodes.some((n) => !seen.has(n.id))) add('graph', 'unreachable_node')
  return issues.filter(
    (issue, i, all) =>
      all.findIndex((v) => v.code === issue.code && v.subject === issue.subject) === i,
  )
}
export function edgeState(edge: Edge, run?: Run): string {
  const source = run?.tasks.find((t) => t.node_id === edge.source),
    target = run?.tasks.find((t) => t.node_id === edge.target)
  if (
    !run?.traversed_edges.includes(edge.id) ||
    !source ||
    !target ||
    source.status !== 'completed' ||
    ['pending', 'skipped'].includes(target.status)
  )
    return 'idle'
  return ['completed', 'waiting_review'].includes(target.status) ? 'completed' : target.status
}
export function checkpointTasks(graph: Graph | undefined, run: Run): Run['tasks'] {
  if (!graph || !run.traversed_edges.length) return run.tasks
  const order: string[] = []
  for (const id of run.traversed_edges) {
    const edge = graph.edges.find((item) => item.id === id)
    if (edge) {
      if (!order.includes(edge.source)) order.push(edge.source)
      if (!order.includes(edge.target)) order.push(edge.target)
    }
  }
  return [...run.tasks].sort(
    (a, b) =>
      (order.includes(a.node_id) ? order.indexOf(a.node_id) : order.length) -
      (order.includes(b.node_id) ? order.indexOf(b.node_id) : order.length),
  )
}
