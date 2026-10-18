import { labelText } from '@/i18n'
import { useTranslation } from 'react-i18next'
import type { ReactNode } from 'react'
export function MainWorkspace({ title, children }: { title: string; children: ReactNode }) {
  useTranslation()

  return (
    <main
      id="main-content"
      tabIndex={-1}
      className="main-workspace layout-standard"
      aria-label={labelText(title)}
    >
      <div className="workspace-body">
        <div className="workspace-content">{children}</div>
      </div>
    </main>
  )
}
export function StandardLayout(props: { title: string; children: ReactNode }) {
  useTranslation()

  return <MainWorkspace {...props} />
}
