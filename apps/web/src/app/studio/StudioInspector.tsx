import { useEffect, useRef, type ReactNode } from 'react'
import { X } from 'lucide-react'
import { Button } from '@/components/ui/button'

const focusable =
  'button:not(:disabled), input:not(:disabled), textarea:not(:disabled), select:not(:disabled), a[href], [tabindex="0"]'
export function StudioInspector({
  open,
  drawer,
  title,
  closeLabel,
  onClose,
  tabs,
  children,
}: {
  open: boolean
  drawer: boolean
  title: string
  closeLabel: string
  onClose: () => void
  tabs: ReactNode
  children: ReactNode
}) {
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!open || !drawer) return
    const previous = document.activeElement as HTMLElement | null
    const frame = requestAnimationFrame(() => ref.current?.focus())
    return () => {
      cancelAnimationFrame(frame)
      if (previous?.isConnected) previous.focus({ preventScroll: true })
    }
  }, [open, drawer])
  return (
    <>
      {open && drawer && (
        <button
          className="studio-drawer-backdrop"
          tabIndex={-1}
          aria-label={closeLabel}
          onClick={onClose}
        />
      )}
      <div
        ref={ref}
        id="studio-inspector"
        className="studio-inspector"
        hidden={!open}
        role={drawer && open ? 'dialog' : 'complementary'}
        aria-modal={drawer && open ? true : undefined}
        aria-label={title}
        tabIndex={-1}
        onKeyDown={(event) => {
          if (event.key === 'Escape' && !event.defaultPrevented) {
            event.preventDefault()
            onClose()
          }
          if (drawer && event.key === 'Tab') {
            const items = [...(ref.current?.querySelectorAll<HTMLElement>(focusable) ?? [])].filter(
              (element) => element.getClientRects().length,
            )
            const first = items[0],
              last = items[items.length - 1]
            if (
              event.shiftKey &&
              (document.activeElement === first || document.activeElement === ref.current)
            ) {
              event.preventDefault()
              last?.focus()
            } else if (
              !event.shiftKey &&
              (document.activeElement === last || document.activeElement === ref.current)
            ) {
              event.preventDefault()
              first?.focus()
            }
          }
        }}
      >
        <div className="studio-inspector-header">
          <div className="af-inspector-tabs">{tabs}</div>
          <Button variant="ghost" size="icon" aria-label={closeLabel} onClick={onClose}>
            <X size={16} />
          </Button>
        </div>
        <div className="studio-inspector-scroll">{children}</div>
      </div>
    </>
  )
}
