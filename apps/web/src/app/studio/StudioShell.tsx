import { Outlet, useLocation } from '@tanstack/react-router'
import { useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import './studio.css'

/** Route layout only. Session, project, locale and theme providers stay above both shells. */
export function StudioShell() {
  const { t } = useTranslation()
  const { pathname } = useLocation()
  useEffect(() => {
    document.title = `ARYN Studio · ${t(pathname.startsWith('/workflows/') ? 'workflows.builder' : 'agents.factory')}`
    const frame = requestAnimationFrame(() =>
      document.getElementById('main-content')?.focus({ preventScroll: true }),
    )
    return () => cancelAnimationFrame(frame)
  }, [pathname, t])
  return (
    <div className="studio-shell">
      <a className="skip-link" href="#main-content">
        {t('ui.skip_to_workspace')}
      </a>
      <main id="main-content" className="studio-main" tabIndex={-1} aria-label="ARYN Studio">
        <Outlet />
      </main>
    </div>
  )
}
