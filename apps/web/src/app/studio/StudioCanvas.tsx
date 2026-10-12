/* eslint-disable jsx-a11y/no-noninteractive-element-interactions, jsx-a11y/no-noninteractive-tabindex -- Canvas application surface; nodes and ports expose semantic keyboard buttons. */
import { useEffect, useRef, useState, type PointerEvent, type ReactNode } from 'react'
import {
  AlertCircle,
  Check,
  GripVertical,
  LoaderCircle,
  Plus,
  X,
  type LucideIcon,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { CanvasControls } from './CanvasControls'
import './canvas.css'

export type CanvasViewport = { x: number; y: number; zoom: number }
export type CanvasPort = { id: string; direction: 'in' | 'out'; dataType: string; y: number }
export type StudioNode = {
  id: string
  type: string
  label: string
  title: string
  icon: LucideIcon
  x: number
  y: number
  width: number
  height: number
  ports: CanvasPort[]
  body: ReactNode
  footer: string
  state: string
  invalid?: boolean
}
export type StudioEdge = {
  id: string
  source: string
  target: string
  source_port: string
  target_port: string
  state?: string
  policy?: boolean
}
const point = (node: StudioNode, port: string, direction: 'in' | 'out') => ({
  x: node.x + (direction === 'out' ? node.width : 0),
  y: node.y + (node.ports.find((p) => p.id === port && p.direction === direction)?.y ?? 72),
})
const curve = (a: { x: number; y: number }, b: { x: number; y: number }) => {
  const bend = Math.max(65, Math.abs(b.x - a.x) * 0.45)
  return `M${a.x},${a.y} C${a.x + bend},${a.y} ${b.x - bend},${b.y} ${b.x},${b.y}`
}
const bounded = (value: number) => Math.max(-10000, Math.min(10000, value))
export function StudioCanvas({
  nodes,
  edges,
  viewport,
  selected,
  readOnly,
  labels,
  canUndo,
  canRedo,
  onMove,
  onDelete,
  onConnect,
  onViewport,
  onSelect,
  onLibrary,
  onAdd,
  onUndo,
  onRedo,
}: {
  nodes: StudioNode[]
  edges: StudioEdge[]
  viewport: CanvasViewport
  selected: string | null
  readOnly: boolean
  canUndo: boolean
  canRedo: boolean
  labels: {
    canvas: string
    subtitle: string
    select: string
    connect: string
    add: string
    undo: string
    redo: string
    zoomIn: string
    zoomOut: string
    fit: string
    minimap: string
    empty: string
    connectionHint: string
    cancel: string
  }
  onMove: (id: string, position: { x: number; y: number }) => void
  onDelete: (id: string) => void
  onConnect: (edge: Omit<StudioEdge, 'id'>) => void
  onViewport: (viewport: CanvasViewport) => void
  onSelect: (id: string) => void
  onLibrary: (trigger: HTMLButtonElement) => void
  onAdd: (type: string, position: { x: number; y: number }) => void
  onUndo: () => void
  onRedo: () => void
}) {
  const board = useRef<HTMLDivElement>(null)
  const drag = useRef<{ id?: string; startX: number; startY: number; x: number; y: number } | null>(
    null,
  )
  const [moving, setMoving] = useState<{ id: string; x: number; y: number } | null>(null)
  const [connecting, setConnecting] = useState<{ node: string; port: string } | null>(null)
  const [cursor, setCursor] = useState({ x: 0, y: 0 })
  const visible = nodes.map((node) => (moving?.id === node.id ? { ...node, ...moving } : node))
  const bounds = visible.reduce(
    (v, n) => ({
      x: Math.min(v.x, n.x),
      y: Math.min(v.y, n.y),
      right: Math.max(v.right, n.x + n.width),
      bottom: Math.max(v.bottom, n.y + n.height),
    }),
    { x: 0, y: 0, right: 1040, bottom: 570 },
  )
  function fit() {
    if (!board.current || !nodes.length) return
    const left = Math.min(...nodes.map((n) => n.x)),
      top = Math.min(...nodes.map((n) => n.y))
    const right = Math.max(...nodes.map((n) => n.x + n.width)),
      bottom = Math.max(...nodes.map((n) => n.y + n.height))
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
  function zoomTo(value: number, cx?: number, cy?: number) {
    const zoom = Math.max(0.25, Math.min(2, value)),
      x = cx ?? (board.current?.clientWidth ?? 600) / 2,
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
          x: bounded(viewport.x - event.deltaX),
          y: bounded(viewport.y - event.deltaY),
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
  function begin(event: PointerEvent<HTMLElement>, node?: StudioNode) {
    if (event.button !== 0 || (node && readOnly) || (!node && event.target !== event.currentTarget))
      return
    event.preventDefault()
    event.stopPropagation()
    // Selection opens inspectors on click, after a touch drag has finished.
    drag.current = {
      id: node?.id,
      startX: event.clientX,
      startY: event.clientY,
      x: node?.x ?? viewport.x,
      y: node?.y ?? viewport.y,
    }
    event.currentTarget.setPointerCapture(event.pointerId)
  }
  function move(event: PointerEvent) {
    if (connecting) setCursor(local(event))
    const active = drag.current
    if (!active) return
    const x = bounded(active.x + (event.clientX - active.startX) / (active.id ? viewport.zoom : 1)),
      y = bounded(active.y + (event.clientY - active.startY) / (active.id ? viewport.zoom : 1))
    if (active.id) setMoving({ id: active.id, x, y })
    else onViewport({ ...viewport, x, y })
  }
  function port(node: StudioNode, item: CanvasPort) {
    if (readOnly) return
    if (item.direction === 'out') {
      setConnecting({ node: node.id, port: item.id })
      setCursor(point(node, item.id, 'out'))
      return
    }
    if (!connecting) return
    onConnect({
      source: connecting.node,
      source_port: connecting.port,
      target: node.id,
      target_port: item.id,
    })
    setConnecting(null)
  }
  return (
    <div
      className="af-board"
      ref={board}
      role="application"
      aria-label={labels.canvas}
      tabIndex={0}
      style={{
        backgroundPosition: `${viewport.x}px ${viewport.y}px`,
        backgroundSize: `${24 * viewport.zoom}px ${24 * viewport.zoom}px`,
      }}
      onPointerDown={(e) => begin(e)}
      onPointerMove={move}
      onPointerUp={() => {
        if (drag.current && moving) onMove(moving.id, moving)
        drag.current = null
        setMoving(null)
      }}
      onPointerCancel={() => {
        drag.current = null
        setMoving(null)
      }}
      onDragOver={(e) => {
        if (!readOnly) e.preventDefault()
      }}
      onDrop={(e) => {
        e.preventDefault()
        if (!readOnly) onAdd(e.dataTransfer.getData('application/aryn-node'), local(e))
      }}
      onKeyDown={(e) => {
        if (e.key === 'Escape') setConnecting(null)
        if (
          e.target === e.currentTarget &&
          ['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight'].includes(e.key)
        ) {
          e.preventDefault()
          onViewport({
            ...viewport,
            x: bounded(
              viewport.x + (e.key === 'ArrowLeft' ? 40 : e.key === 'ArrowRight' ? -40 : 0),
            ),
            y: bounded(viewport.y + (e.key === 'ArrowUp' ? 40 : e.key === 'ArrowDown' ? -40 : 0)),
          })
        }
        if (
          e.target === e.currentTarget &&
          (e.ctrlKey || e.metaKey) &&
          e.key.toLowerCase() === 'z' &&
          !readOnly
        ) {
          e.preventDefault()
          if (e.shiftKey) onRedo()
          else onUndo()
        }
      }}
    >
      <div className="af-board-heading">
        <span>
          <span className="af-live-dot" />
          {labels.canvas}
        </span>
        <small>{labels.subtitle}</small>
      </div>
      <div
        className="af-stage"
        style={{ transform: `translate(${viewport.x}px, ${viewport.y}px) scale(${viewport.zoom})` }}
      >
        <svg className="af-connections" aria-hidden="true">
          {edges.map((edge) => {
            const from = visible.find((n) => n.id === edge.source),
              to = visible.find((n) => n.id === edge.target)
            return from && to ? (
              <path
                key={edge.id}
                data-testid={`edge-${edge.source}-${edge.target}`}
                data-port={edge.source_port}
                data-state={edge.state ?? 'idle'}
                className={`af-edge ${edge.policy ? 'af-policy-edge' : ''}`}
                d={curve(point(from, edge.source_port, 'out'), point(to, edge.target_port, 'in'))}
              />
            ) : null
          })}
          {connecting && visible.some((n) => n.id === connecting.node) && (
            <path
              className="af-edge af-connecting"
              d={curve(
                point(
                  visible.find((n) => n.id === connecting.node)!,
                  connecting.port,
                  'out',
                ),
                cursor,
              )}
            />
          )}
        </svg>
        {visible.map((node) => {
          const Icon = node.icon
          return (
            <div
              key={node.id}
              className={`af-node af-node-${node.type} ${selected === node.id ? 'is-selected' : ''}`}
              data-testid={`node-${node.id}`}
              data-state={node.state}
              data-invalid={node.invalid || undefined}
              style={{ left: node.x, top: node.y, width: node.width, minHeight: node.height }}
            >
              <button
                className="af-node-head"
                aria-label={`${labels.select} ${node.label}`}
                aria-pressed={selected === node.id}
                onClick={() => onSelect(node.id)}
                onPointerDown={(e) => begin(e, node)}
                onKeyDown={(e) => {
                  if (
                    readOnly ||
                    ![
                      'ArrowUp',
                      'ArrowDown',
                      'ArrowLeft',
                      'ArrowRight',
                      'Delete',
                      'Backspace',
                    ].includes(e.key)
                  )
                    return
                  e.preventDefault()
                  if (e.key === 'Delete' || e.key === 'Backspace') onDelete(node.id)
                  else
                    onMove(node.id, {
                      x: bounded(
                        node.x + (e.key === 'ArrowRight' ? 20 : e.key === 'ArrowLeft' ? -20 : 0),
                      ),
                      y: bounded(
                        node.y + (e.key === 'ArrowDown' ? 20 : e.key === 'ArrowUp' ? -20 : 0),
                      ),
                    })
                }}
              >
                <span className="af-node-icon">
                  <Icon size={18} />
                </span>
                <span>
                  <small>{node.label}</small>
                  <strong>{node.title}</strong>
                </span>
                {!readOnly && <GripVertical size={14} className="af-grip" />}
              </button>
              <div className="af-node-body">{node.body}</div>
              <div className="af-node-footer">
                <span>{node.footer}</span>
                {node.state === 'completed' ? (
                  <Check size={13} />
                ) : node.state === 'running' ? (
                  <LoaderCircle className="af-spin" size={13} />
                ) : node.invalid || ['failed', 'outcome_unknown'].includes(node.state) ? (
                  <AlertCircle size={13} />
                ) : (
                  <span className="af-small-dot" />
                )}
              </div>
              {node.ports.map((item) => (
                <button
                  key={`${item.direction}:${item.id}`}
                  className={`af-port af-port-${item.direction} ${item.dataType === 'policy' ? 'af-port-policy' : ''} ${connecting?.node === node.id && connecting.port === item.id ? 'is-connecting' : ''}`}
                  style={{ top: item.y }}
                  disabled={readOnly}
                  aria-label={`${labels.connect} ${node.id} ${item.id} ${item.direction}`}
                  title={`${item.id} · ${item.dataType}`}
                  onPointerDown={(e) => {
                    e.stopPropagation()
                    if (item.direction === 'out') port(node, item)
                  }}
                  onPointerUp={(e) => {
                    e.stopPropagation()
                    if (item.direction === 'in' && connecting) port(node, item)
                  }}
                  onClick={() => port(node, item)}
                />
              ))}
            </div>
          )
        })}
      </div>
      {!nodes.length && (
        <div className="af-empty-canvas">
          {labels.empty}
          <Button onClick={(e) => onLibrary(e.currentTarget)} disabled={readOnly}>
            <Plus size={16} />
            {labels.add}
          </Button>
        </div>
      )}
      <CanvasControls
        labels={labels}
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
      <button className="af-minimap" onClick={fit} aria-label={labels.minimap}>
        <svg
          viewBox={`${bounds.x - 30} ${bounds.y - 30} ${bounds.right - bounds.x + 60} ${bounds.bottom - bounds.y + 60}`}
          aria-hidden="true"
        >
          {visible.map((n) => (
            <rect
              key={n.id}
              x={n.x}
              y={n.y}
              width={n.width}
              height={n.height}
              className={selected === n.id ? 'selected' : ''}
            />
          ))}
        </svg>
      </button>
      {connecting && (
        <div className="af-connection-hint" role="status">
          {labels.connectionHint}
          <button onClick={() => setConnecting(null)} aria-label={labels.cancel}>
            <X size={15} />
          </button>
        </div>
      )}
    </div>
  )
}
