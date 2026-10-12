/* eslint-disable jsx-a11y/no-noninteractive-element-interactions, jsx-a11y/no-noninteractive-tabindex -- A graph editor is an application surface with pan, zoom and keyboard navigation; individual nodes and ports remain semantic buttons. */
import { useEffect, useRef, useState, type PointerEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { Plus, GripVertical, Check, LoaderCircle, AlertCircle, X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { CanvasControls } from '@/app/studio/CanvasControls'
import type { CanvasNode, Connection, Draft, Graph, NodeType, Preview, Viewport } from './api'
import { connectionError, edgeState, nodeRegistry, nodeState } from './registry'

const width = 236
const height = (node: CanvasNode) => (node.type === 'agent' ? 200 : 142)
function point(node: CanvasNode, port: string, direction: 'in' | 'out') {
  return {
    x: node.x + (direction === 'out' ? width : 0),
    y: node.y + (node.type === 'agent' ? (port === 'policy' ? 155 : 95) : 72),
  }
}
const curve = (a: { x: number; y: number }, b: { x: number; y: number }) => {
  const bend = Math.max(65, Math.abs(b.x - a.x) * 0.45)
  return `M${a.x},${a.y} C${a.x + bend},${a.y} ${b.x - bend},${b.y} ${b.x},${b.y}`
}
type Props = {
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
}
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
}: Props) {
  const { t } = useTranslation()
  const board = useRef<HTMLDivElement>(null)
  const drag = useRef<{
    id?: NodeType
    startX: number
    startY: number
    x: number
    y: number
    pointer: number
  } | null>(null)
  const [moving, setMoving] = useState<{ id: NodeType; x: number; y: number } | null>(null)
  const [connecting, setConnecting] = useState<{
    node: NodeType
    port: Connection['source_port']
  } | null>(null)
  const [cursor, setCursor] = useState({ x: 0, y: 0 })
  const visible = moving
    ? {
        ...graph,
        nodes: graph.nodes.map((node) =>
          node.id === moving.id ? { ...node, x: moving.x, y: moving.y } : node,
        ),
      }
    : graph
  const bounds = visible.nodes.reduce(
    (value, node) => ({
      x: Math.min(value.x, node.x),
      y: Math.min(value.y, node.y),
      right: Math.max(value.right, node.x + width),
      bottom: Math.max(value.bottom, node.y + height(node)),
    }),
    { x: 0, y: 0, right: 1040, bottom: 570 },
  )
  function fit() {
    if (!board.current || !graph.nodes.length) return
    const left = Math.min(...graph.nodes.map((node) => node.x)),
      top = Math.min(...graph.nodes.map((node) => node.y))
    const right = Math.max(...graph.nodes.map((node) => node.x + width)),
      bottom = Math.max(...graph.nodes.map((node) => node.y + height(node)))
    const zoom = Math.max(
      0.25,
      Math.min(
        1.2,
        (board.current.clientWidth - 100) / (right - left),
        (board.current.clientHeight - 160) / (bottom - top),
      ),
    )
    onViewport({
      x: (board.current.clientWidth - (right + left) * zoom) / 2,
      y: (board.current.clientHeight - (bottom + top) * zoom) / 2,
      zoom,
    })
  }
  function zoomTo(zoom: number, cx?: number, cy?: number) {
    zoom = Math.max(0.25, Math.min(2, zoom))
    const x = cx ?? (board.current?.clientWidth ?? 600) / 2,
      y = cy ?? (board.current?.clientHeight ?? 500) / 2
    onViewport({
      zoom,
      x: x - ((x - viewport.x) * zoom) / viewport.zoom,
      y: y - ((y - viewport.y) * zoom) / viewport.zoom,
    })
  }
  useEffect(() => {
    const element = board.current
    if (!element) return
    function wheel(event: WheelEvent) {
      event.preventDefault()
      const rect = element!.getBoundingClientRect()
      if (event.ctrlKey || event.metaKey)
        zoomTo(
          viewport.zoom * Math.exp(-event.deltaY * 0.002),
          event.clientX - rect.left,
          event.clientY - rect.top,
        )
      else
        onViewport({
          ...viewport,
          x: Math.max(-10000, Math.min(10000, viewport.x - event.deltaX)),
          y: Math.max(-10000, Math.min(10000, viewport.y - event.deltaY)),
        })
    }
    element.addEventListener('wheel', wheel, { passive: false })
    return () => element.removeEventListener('wheel', wheel)
  })
  function local(event: { clientX: number; clientY: number }) {
    const rect = board.current!.getBoundingClientRect()
    return {
      x: (event.clientX - rect.left - viewport.x) / viewport.zoom,
      y: (event.clientY - rect.top - viewport.y) / viewport.zoom,
    }
  }
  function begin(event: PointerEvent<HTMLElement>, node?: CanvasNode) {
    if (event.button !== 0 || (node && readOnly)) return
    if (!node && event.target !== event.currentTarget) return
    event.preventDefault()
    event.stopPropagation()
    if (node) onSelect(node.id)
    drag.current = {
      id: node?.id,
      startX: event.clientX,
      startY: event.clientY,
      x: node?.x ?? viewport.x,
      y: node?.y ?? viewport.y,
      pointer: event.pointerId,
    }
    event.currentTarget.setPointerCapture(event.pointerId)
  }
  function move(event: PointerEvent) {
    if (connecting) setCursor(local(event))
    const active = drag.current
    if (!active) return
    const x = active.x + (event.clientX - active.startX) / (active.id ? viewport.zoom : 1),
      y = active.y + (event.clientY - active.startY) / (active.id ? viewport.zoom : 1)
    if (active.id)
      setMoving({
        id: active.id,
        x: Math.max(-10000, Math.min(10000, x)),
        y: Math.max(-10000, Math.min(10000, y)),
      })
    else
      onViewport({
        ...viewport,
        x: Math.max(-10000, Math.min(10000, x)),
        y: Math.max(-10000, Math.min(10000, y)),
      })
  }
  function finish() {
    if (drag.current && moving) onGraph(visible)
    drag.current = null
    setMoving(null)
  }
  function port(node: CanvasNode, id: string, direction: 'in' | 'out') {
    if (readOnly) return
    if (direction === 'out') {
      setConnecting({ node: node.id, port: id as Connection['source_port'] })
      setCursor(point(node, id, 'out'))
      return
    }
    if (!connecting) return
    const edge: Connection = {
      source: connecting.node,
      source_port: connecting.port,
      target: node.id,
      target_port: id as Connection['target_port'],
    }
    const error = connectionError(graph, edge)
    if (error) onMessage(error)
    else onGraph({ ...graph, connections: [...graph.connections, edge] })
    setConnecting(null)
  }
  return (
    <div
      className="af-board"
      ref={board}
      role="application"
      aria-label={t('agents.blueprint')}
      tabIndex={0}
      style={{
        backgroundPosition: `${viewport.x}px ${viewport.y}px`,
        backgroundSize: `${24 * viewport.zoom}px ${24 * viewport.zoom}px`,
      }}
      onPointerDown={(event) => begin(event)}
      onPointerMove={move}
      onPointerUp={finish}
      onPointerCancel={() => {
        drag.current = null
        setMoving(null)
      }}
      onDragOver={(event) => {
        if (!readOnly) event.preventDefault()
      }}
      onDrop={(event) => {
        event.preventDefault()
        const type = event.dataTransfer.getData('application/aryn-node')
        if (!readOnly && type in nodeRegistry) onAdd(type as NodeType, local(event))
      }}
      onKeyDown={(event) => {
        if (event.key === 'Escape') setConnecting(null)
        if (
          event.target === event.currentTarget &&
          ['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight'].includes(event.key)
        ) {
          event.preventDefault()
          onViewport({
            ...viewport,
            x: viewport.x + (event.key === 'ArrowLeft' ? 40 : event.key === 'ArrowRight' ? -40 : 0),
            y: viewport.y + (event.key === 'ArrowUp' ? 40 : event.key === 'ArrowDown' ? -40 : 0),
          })
        }
        if (
          event.target === event.currentTarget &&
          (event.ctrlKey || event.metaKey) &&
          event.key === 'z'
        ) {
          event.preventDefault()
          if (!readOnly) {
            if (event.shiftKey) onRedo()
            else onUndo()
          }
        }
      }}
    >
      <div className="af-board-heading">
        <span>
          <span className="af-live-dot" />
          {t('agents.factory')}
        </span>
        <small>{t('agents.addPolicy')}</small>
      </div>
      <div
        className="af-stage"
        style={{ transform: `translate(${viewport.x}px, ${viewport.y}px) scale(${viewport.zoom})` }}
      >
        <svg className="af-connections" aria-hidden="true">
          {visible.connections.map((edge) => {
            const from = visible.nodes.find((node) => node.id === edge.source)!,
              to = visible.nodes.find((node) => node.id === edge.target)!
            return (
              <path
                key={`${edge.source}:${edge.target}`}
                data-testid={`edge-${edge.source}-${edge.target}`}
                data-state={edgeState(edge, preview)}
                className={`af-edge ${edge.source_port === 'policy' ? 'af-policy-edge' : ''}`}
                d={curve(point(from, edge.source_port, 'out'), point(to, edge.target_port, 'in'))}
              />
            )
          })}
          {connecting && visible.nodes.some((node) => node.id === connecting.node) && (
            <path
              className="af-edge af-connecting"
              d={curve(
                point(
                  visible.nodes.find((node) => node.id === connecting.node)!,
                  connecting.port,
                  'out',
                ),
                cursor,
              )}
            />
          )}
        </svg>
        {visible.nodes.map((node) => {
          const definition = nodeRegistry[node.type],
            Icon = definition.icon,
            state = nodeState(node.type, preview)
          return (
            <div
              key={node.id}
              className={`af-node af-node-${node.type} ${selected === node.id ? 'is-selected' : ''}`}
              data-testid={`node-${node.id}`}
              data-state={state}
              style={{ left: node.x, top: node.y, width, minHeight: height(node) }}
            >
              <button
                className="af-node-head"
                aria-label={`${t('agents.select')} ${t('agents.' + definition.label)}`}
                aria-pressed={selected === node.id}
                onClick={() => onSelect(node.id)}
                onPointerDown={(event) => begin(event, node)}
                onKeyDown={(event) => {
                  if (
                    !readOnly &&
                    [
                      'ArrowUp',
                      'ArrowDown',
                      'ArrowLeft',
                      'ArrowRight',
                      'Delete',
                      'Backspace',
                    ].includes(event.key)
                  ) {
                    event.preventDefault()
                    if (event.key === 'Delete' || event.key === 'Backspace')
                      onGraph({
                        ...graph,
                        nodes: graph.nodes.filter((item) => item.id !== node.id),
                        connections: graph.connections.filter(
                          (edge) => edge.source !== node.id && edge.target !== node.id,
                        ),
                      })
                    else
                      onGraph({
                        ...graph,
                        nodes: graph.nodes.map((item) =>
                          item.id === node.id
                            ? {
                                ...item,
                                x: Math.max(
                                  -10000,
                                  Math.min(
                                    10000,
                                    item.x +
                                      (event.key === 'ArrowRight'
                                        ? 20
                                        : event.key === 'ArrowLeft'
                                          ? -20
                                          : 0),
                                  ),
                                ),
                                y: Math.max(
                                  -10000,
                                  Math.min(
                                    10000,
                                    item.y +
                                      (event.key === 'ArrowDown'
                                        ? 20
                                        : event.key === 'ArrowUp'
                                          ? -20
                                          : 0),
                                  ),
                                ),
                              }
                            : item,
                        ),
                      })
                  }
                }}
              >
                <span className="af-node-icon">
                  <Icon size={18} />
                </span>
                <span>
                  <small>{t('agents.' + definition.label)}</small>
                  <strong>{node.type === 'agent' ? name : t('agents.' + definition.label)}</strong>
                </span>
                {!readOnly && <GripVertical size={14} className="af-grip" />}
              </button>
              <div className="af-node-body">
                {node.type === 'agent' ? (
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
                )}
              </div>
              <div className="af-node-footer">
                <span>
                  {definition.category === 'policy'
                    ? t('agents.configurationOnly')
                    : t('agents.' + state)}
                </span>
                {state === 'completed' ? (
                  <Check size={13} />
                ) : state === 'running' ? (
                  <LoaderCircle className="af-spin" size={13} />
                ) : ['failed', 'outcome_unknown'].includes(state) ? (
                  <AlertCircle size={13} />
                ) : (
                  <span className="af-small-dot" />
                )}
              </div>
              {definition.ports.map((item) => {
                const position = point(node, item.id, item.direction)
                return (
                  <button
                    key={`${item.direction}:${item.id}`}
                    className={`af-port af-port-${item.direction} ${item.dataType === 'policy' ? 'af-port-policy' : ''} ${connecting?.node === node.id && connecting.port === item.id ? 'is-connecting' : ''}`}
                    style={{ top: position.y - node.y }}
                    disabled={readOnly}
                    aria-label={`${t('agents.connect')} ${node.id} ${item.id} ${item.direction}`}
                    title={`${item.id} · ${item.dataType}`}
                    onPointerDown={(event) => {
                      event.stopPropagation()
                      if (item.direction === 'out') port(node, item.id, item.direction)
                    }}
                    onPointerUp={(event) => {
                      event.stopPropagation()
                      if (item.direction === 'in' && connecting) port(node, item.id, item.direction)
                    }}
                    onClick={() => port(node, item.id, item.direction)}
                  />
                )
              })}
            </div>
          )
        })}
      </div>
      {!graph.nodes.length && (
        <div className="af-empty-canvas">
          {t('agents.noNodes')}
          <Button onClick={(event) => onLibrary(event.currentTarget)} disabled={readOnly}>
            <Plus size={16} />
            {t('agents.add')}
          </Button>
        </div>
      )}
      <CanvasControls
        labels={{
          canvas: t('agents.blueprint'),
          add: t('agents.add'),
          undo: t('agents.undo'),
          redo: t('agents.redo'),
          zoomIn: t('agents.zoomIn'),
          zoomOut: t('agents.zoomOut'),
          fit: t('agents.fit'),
        }}
        readOnly={readOnly}
        canUndo={canUndo}
        canRedo={canRedo}
        zoom={viewport.zoom}
        onLibrary={onLibrary}
        onUndo={onUndo}
        onRedo={onRedo}
        onZoom={zoomTo}
        onFit={fit}
      />
      <button className="af-minimap" onClick={fit} aria-label={t('agents.minimap')}>
        <svg
          viewBox={`${bounds.x - 30} ${bounds.y - 30} ${bounds.right - bounds.x + 60} ${bounds.bottom - bounds.y + 60}`}
          aria-hidden="true"
        >
          {visible.nodes.map((node) => (
            <rect
              key={node.id}
              x={node.x}
              y={node.y}
              width={width}
              height={height(node)}
              className={selected === node.id ? 'selected' : ''}
            />
          ))}
        </svg>
      </button>
      {connecting && (
        <div className="af-connection-hint" role="status">
          {t('agents.connectionHint')}
          <button onClick={() => setConnecting(null)} aria-label={t('agents.cancel')}>
            <X size={14} />
          </button>
        </div>
      )}
    </div>
  )
}
