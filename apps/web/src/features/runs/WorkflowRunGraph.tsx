import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { StudioCanvas } from '@/app/studio/StudioCanvas'
import { registry, edgeState } from '@/features/workflows/registry'
import type { Run, Version } from '@/features/workflows/api'
import '@/features/agents/agents.css'
const noop = () => {}
export function WorkflowRunGraph({ run, version }: { run: Run; version: Version }) {
  const { t } = useTranslation(),
    [viewport, setViewport] = useState({ x: 20, y: 55, zoom: 0.32 })
  return (
    <div className="op-readgraph">
      <StudioCanvas
        nodes={version.graph.nodes.map((node, i) => ({
          id: node.id,
          type: node.kind,
          label: t('workflows.' + node.kind),
          title: node.label,
          icon: registry[node.kind].icon,
          x: i * 270,
          y: 60,
          width: 236,
          height: 142,
          ports: registry[node.kind].ports(node),
          body: (
            <p>
              {node.input_schema} → {node.output_schema}
            </p>
          ),
          footer: t(
            'operations.states.' +
              (run.tasks.find((task) => task.node_id === node.id)?.status ?? 'pending'),
          ),
          state: run.tasks.find((task) => task.node_id === node.id)?.status ?? 'pending',
        }))}
        edges={version.graph.edges.map((edge) => ({ ...edge, state: edgeState(edge, run) }))}
        viewport={viewport}
        onViewport={setViewport}
        selected={null}
        readOnly
        canUndo={false}
        canRedo={false}
        labels={{
          canvas: t('operations.readGraph'),
          subtitle: '',
          select: t('agents.select'),
          connect: t('agents.connect'),
          add: t('agents.addNode'),
          undo: t('agents.undo'),
          redo: t('agents.redo'),
          zoomIn: t('agents.zoomIn'),
          zoomOut: t('agents.zoomOut'),
          fit: t('agents.fit'),
          minimap: t('agents.minimap'),
          empty: t('operations.unavailable'),
          connectionHint: '',
          cancel: t('operations.cancel'),
        }}
        onMove={noop}
        onDelete={noop}
        onConnect={noop}
        onSelect={noop}
        onLibrary={noop}
        onAdd={noop}
        onUndo={noop}
        onRedo={noop}
      />
    </div>
  )
}
