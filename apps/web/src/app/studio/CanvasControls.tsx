import { Plus, Minus, Maximize, Undo2, Redo2 } from 'lucide-react'
import { Button } from '@/components/ui/button'

/** Presentation shared by editors; graph/viewport history belongs to the domain's canvas. */
export function CanvasControls({
  labels,
  readOnly,
  canUndo,
  canRedo,
  zoom,
  onLibrary,
  onUndo,
  onRedo,
  onZoom,
  onFit,
}: {
  labels: {
    canvas: string
    add: string
    undo: string
    redo: string
    zoomIn: string
    zoomOut: string
    fit: string
  }
  readOnly: boolean
  canUndo: boolean
  canRedo: boolean
  zoom: number
  onLibrary: (trigger: HTMLButtonElement) => void
  onUndo: () => void
  onRedo: () => void
  onZoom: (zoom: number) => void
  onFit: () => void
}) {
  return (
    <>
      <div className="af-canvas-tools" role="group" aria-label={labels.canvas}>
        <Button
          variant="secondary"
          size="icon"
          onClick={(event) => onLibrary(event.currentTarget)}
          disabled={readOnly}
          aria-label={labels.add}
          aria-haspopup="dialog"
          aria-controls="studio-node-library"
        >
          <Plus size={18} />
        </Button>
        <span className="af-tool-divider" />
        <Button
          variant="ghost"
          size="icon"
          onClick={onUndo}
          disabled={!canUndo || readOnly}
          aria-label={labels.undo}
        >
          <Undo2 size={16} />
        </Button>
        <Button
          variant="ghost"
          size="icon"
          onClick={onRedo}
          disabled={!canRedo || readOnly}
          aria-label={labels.redo}
        >
          <Redo2 size={16} />
        </Button>
      </div>
      <div className="af-zoom-tools">
        <Button
          variant="ghost"
          size="icon"
          onClick={() => onZoom(zoom - 0.1)}
          aria-label={labels.zoomOut}
        >
          <Minus size={15} />
        </Button>
        <output>{Math.round(zoom * 100)}%</output>
        <Button
          variant="ghost"
          size="icon"
          onClick={() => onZoom(zoom + 0.1)}
          aria-label={labels.zoomIn}
        >
          <Plus size={15} />
        </Button>
        <Button variant="ghost" size="icon" onClick={onFit} aria-label={labels.fit}>
          <Maximize size={16} />
        </Button>
      </div>
    </>
  )
}
