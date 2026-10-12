import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from 'react'
import { Search, X } from 'lucide-react'
import { Button } from '@/components/ui/button'

/** Nonmodal so the same panel supports library-to-canvas drag and drop. */
export function StudioLibrary({
  anchor,
  label,
  onClose,
  children,
}: {
  anchor: HTMLElement | null
  label: string
  onClose: (restoreFocus: boolean) => void
  children: ReactNode
}) {
  const ref = useRef<HTMLDivElement>(null)
  const [position, setPosition] = useState({ left: 68, top: 84 })
  useLayoutEffect(() => {
    function place() {
      const rect = anchor?.getBoundingClientRect()
      const width = ref.current?.offsetWidth ?? 320
      const height = ref.current?.offsetHeight ?? 600
      const left = rect ? (rect.left < 60 ? rect.right + 12 : rect.left) : 68
      const top = rect
        ? rect.top > window.innerHeight / 2
          ? rect.top - height - 10
          : rect.bottom + 10
        : 84
      setPosition({
        left: Math.max(12, Math.min(left, window.innerWidth - width - 12)),
        top: Math.max(76, Math.min(top, window.innerHeight - height - 12)),
      })
    }
    place()
    ref.current?.querySelector<HTMLInputElement>('input')?.focus()
    window.addEventListener('resize', place)
    return () => window.removeEventListener('resize', place)
  }, [anchor])
  useEffect(() => {
    function outside(event: PointerEvent) {
      if (!ref.current?.contains(event.target as Node) && !anchor?.contains(event.target as Node))
        onClose(false)
    }
    function escape(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        event.preventDefault()
        event.stopPropagation()
        onClose(true)
      }
    }
    // Canvas pointer handlers stop bubbling while panning/dragging.
    document.addEventListener('pointerdown', outside, true)
    document.addEventListener('keydown', escape)
    return () => {
      document.removeEventListener('pointerdown', outside, true)
      document.removeEventListener('keydown', escape)
    }
  }, [anchor, onClose])
  return (
    <div
      id="studio-node-library"
      ref={ref}
      className="studio-library"
      role="dialog"
      aria-modal="false"
      aria-label={label}
      style={position}
    >
      {children}
    </div>
  )
}

export function StudioLibrarySearch({
  title,
  closeLabel,
  searchLabel,
  search,
  onSearch,
  categories,
  category,
  onCategory,
  onClose,
}: {
  title: string
  closeLabel: string
  searchLabel: string
  search: string
  onSearch: (value: string) => void
  categories: { id: string; label: string }[]
  category: string
  onCategory: (value: string) => void
  onClose: () => void
}) {
  return (
    <>
      <header>
        <div>
          <span className="af-kicker">ARYN</span>
          <h2>{title}</h2>
        </div>
        <Button variant="ghost" size="icon" onClick={onClose} aria-label={closeLabel}>
          <X size={17} />
        </Button>
      </header>
      <label className="af-search">
        <Search size={15} />
        <input
          aria-label={searchLabel}
          placeholder={searchLabel}
          value={search}
          onChange={(event) => onSearch(event.target.value)}
        />
      </label>
      <div className="af-library-filters">
        {categories.map((item) => (
          <button
            key={item.id}
            aria-pressed={category === item.id}
            onClick={() => onCategory(item.id)}
          >
            {item.label}
          </button>
        ))}
      </div>
    </>
  )
}
