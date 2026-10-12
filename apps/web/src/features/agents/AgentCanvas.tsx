import { useTranslation } from 'react-i18next'
import { StudioCanvas } from '@/app/studio/StudioCanvas'
import type { Connection, Draft, Graph, NodeType, Preview, Viewport } from './api'
import { connectionError, edgeState, nodeRegistry, nodeState } from './registry'

export function AgentCanvas({
  graph,
  viewport,
  selected,
  draft,
  name,
  preview,
  readOnly,
  canUndo,
  canRedo,
  onGraph,
  onViewport,
  onSelect,
  onLibrary,
  onAdd,
  onUndo,
  onRedo,
  onMessage,
}: {
  graph: Graph
  viewport: Viewport
  selected: NodeType | null
  draft: Draft | null
  name: string
  preview?: Preview
  readOnly: boolean
  canUndo: boolean
  canRedo: boolean
  onGraph: (graph: Graph) => void
  onViewport: (viewport: Viewport) => void
  onSelect: (type: NodeType) => void
  onLibrary: (trigger: HTMLButtonElement) => void
  onAdd: (type: NodeType, position: { x: number; y: number }) => void
  onUndo: () => void
  onRedo: () => void
  onMessage: (key: string) => void
}) {
  const { t } = useTranslation()
  return (
    <StudioCanvas
      nodes={graph.nodes.map((node) => {
        const definition = nodeRegistry[node.type],
          state = nodeState(node.type, preview)
        return {
          ...node,
          width: 236,
          height: node.type === 'agent' ? 200 : 142,
          icon: definition.icon,
          label: t('agents.' + definition.label),
          title: node.type === 'agent' ? name : t('agents.' + definition.label),
          state,
          ports: definition.ports.map((p) => ({
            ...p,
            y: node.type === 'agent' ? (p.id === 'policy' ? 155 : 95) : 72,
          })),
          footer:
            definition.category === 'policy' ? t('agents.configurationOnly') : t('agents.' + state),
          body:
            node.type === 'agent' ? (
              <>
                <span className="af-model-label">
                  <span className="af-live-dot" />
                  {draft?.model || t('agents.notRecorded')}
                </span>
                <p>{draft?.objective || t('agents.agentDescription')}</p>
                <span className="af-node-chip">
                  {draft?.output_contract.format ?? 'text'} · {t('agents.draft')}
                </span>
              </>
            ) : (
              <p>{t('agents.' + definition.description)}</p>
            ),
        }
      })}
      edges={graph.connections.map((edge) => ({
        ...edge,
        id: `${edge.source}:${edge.source_port}:${edge.target}`,
        state: edgeState(edge, preview),
        policy: edge.source_port === 'policy',
      }))}
      viewport={viewport}
      selected={selected}
      readOnly={readOnly}
      canUndo={canUndo}
      canRedo={canRedo}
      labels={{
        canvas: t('agents.blueprint'),
        subtitle: t('agents.addPolicy'),
        select: t('agents.select'),
        connect: t('agents.connect'),
        add: t('agents.add'),
        undo: t('agents.undo'),
        redo: t('agents.redo'),
        zoomIn: t('agents.zoomIn'),
        zoomOut: t('agents.zoomOut'),
        fit: t('agents.fit'),
        minimap: t('agents.minimap'),
        empty: t('agents.noNodes'),
        connectionHint: t('agents.connectionHint'),
        cancel: t('agents.cancel'),
      }}
      onMove={(id, position) =>
        onGraph({
          ...graph,
          nodes: graph.nodes.map((n) => (n.id === id ? { ...n, x: position.x, y: position.y } : n)),
        })
      }
      onDelete={(id) =>
        onGraph({
          ...graph,
          nodes: graph.nodes.filter((n) => n.id !== id),
          connections: graph.connections.filter((e) => e.source !== id && e.target !== id),
        })
      }
      onConnect={(value) => {
        const edge = value as Connection
        const error = connectionError(graph, edge)
        if (error) onMessage(error)
        else onGraph({ ...graph, connections: [...graph.connections, edge] })
      }}
      onViewport={onViewport}
      onSelect={(id) => onSelect(id as NodeType)}
      onLibrary={onLibrary}
      onAdd={(type, position) => {
        if (type in nodeRegistry) onAdd(type as NodeType, position)
      }}
      onUndo={onUndo}
      onRedo={onRedo}
    />
  )
}
