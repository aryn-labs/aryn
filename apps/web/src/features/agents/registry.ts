import {
  ArrowDownToLine,
  ArrowUpFromLine,
  Bot,
  ShieldCheck,
  Wallet,
  FlaskConical,
  LockKeyhole,
  type LucideIcon,
} from 'lucide-react'
import {
  draftSchema,
  type Connection,
  type Draft,
  type Graph,
  type NodeType,
  type Preview,
} from './api'

export type Port = {
  id: Connection['source_port'] | Connection['target_port']
  direction: 'in' | 'out'
  dataType: 'text' | 'response' | 'policy'
  multiple?: boolean
}
export type NodeDefinition = {
  type: NodeType
  label: string
  description: string
  icon: LucideIcon
  category: 'core' | 'policy'
  ports: Port[]
  configurationSchema: typeof draftSchema | null
  inspector: 'input' | 'agent' | 'output' | 'constraints' | 'tools' | 'budget' | 'evaluation'
  capabilityRequirements: string[]
  permissionRequirements: string[]
  runtimeEvents: Preview['events'][number]['type'][]
  validate: (draft: Draft | null) => string[]
}
const policy = (
  type: NodeType,
  icon: LucideIcon,
  inspector: NodeDefinition['inspector'],
): NodeDefinition => ({
  type,
  label: type,
  description: `${type}Description`,
  icon,
  category: 'policy',
  ports: [{ id: 'policy', direction: 'out', dataType: 'policy' }],
  configurationSchema: draftSchema,
  inspector,
  capabilityRequirements: [],
  permissionRequirements: ['version:create'],
  runtimeEvents: [],
  validate: () => [],
})
export const nodeRegistry: Record<NodeType, NodeDefinition> = {
  input: {
    type: 'input',
    label: 'input',
    description: 'inputDescription',
    icon: ArrowUpFromLine,
    category: 'core',
    ports: [{ id: 'text', direction: 'out', dataType: 'text' }],
    configurationSchema: null,
    inspector: 'input',
    capabilityRequirements: ['text_preview'],
    permissionRequirements: ['version:create'],
    runtimeEvents: ['input.accepted'],
    validate: () => [],
  },
  agent: {
    type: 'agent',
    label: 'agent',
    description: 'agentDescription',
    icon: Bot,
    category: 'core',
    ports: [
      { id: 'input', direction: 'in', dataType: 'text' },
      { id: 'policy', direction: 'in', dataType: 'policy', multiple: true },
      { id: 'result', direction: 'out', dataType: 'response' },
    ],
    configurationSchema: draftSchema,
    inspector: 'agent',
    capabilityRequirements: ['text_preview'],
    permissionRequirements: ['version:create'],
    runtimeEvents: ['agent.dispatched'],
    validate: (draft) => (draftSchema.safeParse(draft).success ? [] : ['invalidDefinition']),
  },
  output: {
    type: 'output',
    label: 'output',
    description: 'outputDescription',
    icon: ArrowDownToLine,
    category: 'core',
    ports: [{ id: 'result', direction: 'in', dataType: 'response' }],
    configurationSchema: draftSchema,
    inspector: 'output',
    capabilityRequirements: ['text_preview'],
    permissionRequirements: ['version:create'],
    runtimeEvents: ['run.completed'],
    validate: () => [],
  },
  constraints: policy('constraints', ShieldCheck, 'constraints'),
  'tool-policy': policy('tool-policy', LockKeyhole, 'tools'),
  budget: policy('budget', Wallet, 'budget'),
  evaluation: policy('evaluation', FlaskConical, 'evaluation'),
}
export const initialGraph = (): Graph => ({
  schema_version: '1.0.0',
  nodes: [
    { id: 'input', type: 'input', x: 65, y: 225 },
    { id: 'agent', type: 'agent', x: 395, y: 195 },
    { id: 'output', type: 'output', x: 755, y: 225 },
  ],
  connections: [
    { source: 'input', source_port: 'text', target: 'agent', target_port: 'input' },
    { source: 'agent', source_port: 'result', target: 'output', target_port: 'result' },
  ],
})
export function connectionError(graph: Graph, edge: Connection): string | null {
  const from = graph.nodes.find((node) => node.id === edge.source),
    to = graph.nodes.find((node) => node.id === edge.target)
  const source =
    from &&
    nodeRegistry[from.type].ports.find(
      (port) => port.id === edge.source_port && port.direction === 'out',
    )
  const target =
    to &&
    nodeRegistry[to.type].ports.find(
      (port) => port.id === edge.target_port && port.direction === 'in',
    )
  if (!source || !target || source.dataType !== target.dataType || edge.source === edge.target)
    return 'invalidConnection'
  if (
    graph.connections.some(
      (item) =>
        item.source === edge.source &&
        item.source_port === edge.source_port &&
        item.target === edge.target &&
        item.target_port === edge.target_port,
    )
  )
    return 'duplicateConnection'
  if (
    !target.multiple &&
    graph.connections.some(
      (item) => item.target === edge.target && item.target_port === edge.target_port,
    )
  )
    return 'occupiedPort'
  return null
}
export function graphErrors(graph: Graph): string[] {
  const pairs = graph.connections.map((edge) => `${edge.source}:${edge.target}`)
  return pairs.includes('input:agent') && pairs.includes('agent:output') ? [] : ['incompletePath']
}
export function nodeState(type: NodeType, preview?: Preview): string {
  if (!preview?.result.execution_claim_verified || nodeRegistry[type].runtimeEvents.length === 0)
    return 'idle'
  const events = new Set(preview.events.map((event) => event.type))
  if (type === 'input') return events.has('input.accepted') ? 'completed' : 'idle'
  if (type === 'output')
    return preview.result.status === 'completed' && events.has('run.completed')
      ? 'completed'
      : 'idle'
  if (!events.has('agent.dispatched'))
    return terminalState(preview.result.status) ? preview.result.status : 'queued'
  return preview.result.status === 'started' ? 'queued' : preview.result.status
}
const terminalState = (state: string) => ['failed', 'cancelled', 'outcome_unknown'].includes(state)
export function edgeState(edge: Connection, preview?: Preview): string {
  if (!preview?.result.execution_claim_verified) return 'idle'
  if (
    edge.source === 'input' &&
    edge.target === 'agent' &&
    preview.events.some((event) => event.type === 'agent.dispatched')
  )
    return terminalState(preview.result.status)
      ? 'idle'
      : preview.result.status === 'running'
        ? 'running'
        : 'completed'
  if (
    edge.source === 'agent' &&
    edge.target === 'output' &&
    preview.result.status === 'completed' &&
    preview.events.some((event) => event.type === 'run.completed')
  )
    return 'completed'
  return 'idle'
}
