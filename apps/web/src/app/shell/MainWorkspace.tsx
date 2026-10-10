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
  return (
    <main
      id="main-content"
      tabIndex={-1}
      className={`main-workspace layout-${layout}`}
      aria-label={`${title} workspace`}
    >
      <div className="workspace-body">
        {layout === 'explorer' && explorer && (
          <aside className="explorer-pane" aria-label="Explorer">
            {explorer}
          </aside>
        )}
        <div className="workspace-content">{children}</div>
      </div>
    </main>
  )
}
export function StandardLayout(props: { title: string; children: ReactNode }) {
  return <MainWorkspace {...props} />
}
export function ExplorerLayout(props: { title: string; children: ReactNode; explorer: ReactNode }) {
  return <MainWorkspace {...props} layout="explorer" />
}
export function CanvasLayout(props: { title: string; children: ReactNode }) {
  return <MainWorkspace {...props} layout="canvas" />
}
