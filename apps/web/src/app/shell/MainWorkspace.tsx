import { labelText, translate as tr } from '@/i18n'
import { useTranslation } from 'react-i18next'
import type { ReactNode } from 'react'
export function MainWorkspace({
  title,
  children,
  layout = 'standard',
  explorer,
}: {
  title: string
  children: ReactNode
  layout?: 'standard' | 'explorer' | 'canvas'
  explorer?: ReactNode
}) {
  useTranslation()

  return (
    <main
      id="main-content"
      tabIndex={-1}
      className={`main-workspace layout-${layout}`}
      aria-label={labelText(title)}
    >
      <div className="workspace-body">
        {layout === 'explorer' && explorer && (
          <aside className="explorer-pane" aria-label={tr('ui.explorer')}>
            {explorer}
          </aside>
        )}
        <div className="workspace-content">{children}</div>
      </div>
    </main>
  )
}
export function StandardLayout(props: { title: string; children: ReactNode }) {
  useTranslation()

  return <MainWorkspace {...props} />
}
export function ExplorerLayout(props: { title: string; children: ReactNode; explorer: ReactNode }) {
  useTranslation()

  return <MainWorkspace {...props} layout="explorer" />
}
export function CanvasLayout(props: { title: string; children: ReactNode }) {
  useTranslation()

  return <MainWorkspace {...props} layout="canvas" />
}
