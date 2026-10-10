import { translate as tr, labelText } from '@/i18n'
import { useTranslation } from 'react-i18next'
import { Outlet, useLocation } from '@tanstack/react-router'
import { useEffect, useRef } from 'react'
import { AppTopbar } from './AppTopbar'
import { AppSidebar } from './AppSidebar'
import { MobileNavigation } from './MobileNavigation'
import { GlobalSearch } from '@/components/overlays/GlobalSearch'
import { ResourceDetailsDialog } from '@/components/overlays/ResourceDetailsDialog'
import { useShell } from '@/app/providers/ShellProvider'
import { useWorkspace } from '@/app/providers/WorkspaceProvider'
import { navigation } from '@/components/navigation/items'
export function AppShell() {
  useTranslation()

  const { collapsed } = useShell()
  const { pathname } = useLocation()
  const previous = useRef(pathname)
  const { context, loading, error } = useWorkspace()
  const label = pathname.startsWith('/chat/')
    ? tr('chat.assistant')
    : labelText(navigation.find((item) => item.path === pathname)?.label ?? 'Page not found')
  useEffect(() => {
    document.title = `${label} · ARYN Studio`
    if (previous.current !== pathname) {
      previous.current = pathname
      const frame = requestAnimationFrame(() =>
        document.getElementById('main-content')?.focus({ preventScroll: true }),
      )
      return () => cancelAnimationFrame(frame)
    }
  }, [pathname, label])
  return (
    <div className={`app-shell ${collapsed ? 'is-sidebar-collapsed' : ''}`}>
      <a className="skip-link" href="#main-content">
        {tr('ui.skip_to_workspace')}
      </a>
      <AppTopbar />
      <div className="shell-panels">
        <AppSidebar />
        <div className="main-column">
          <Outlet />
          <footer className="workspace-footer">
            <span className="footer-brand">{tr('ui.aryn_studio')}</span>
            <span>
              <span className={`status-dot ${context ? 'status-completed' : 'status-unknown'}`} />
              {error
                ? tr('ui.workspace_unavailable')
                : loading
                  ? tr('ui.loading_workspace')
                  : context
                    ? tr('ui.workspace_loaded')
                    : tr('ui.no_session')}
              <span className="footer-divider" />
              {tr('ui.v1_0_0')}
            </span>
          </footer>
        </div>
      </div>
      <MobileNavigation />
      <GlobalSearch />
      <ResourceDetailsDialog />
      <div className="sr-only" role="status" aria-live="polite">
        {label}
      </div>
    </div>
  )
}
