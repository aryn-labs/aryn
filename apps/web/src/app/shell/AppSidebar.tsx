import { labelText } from '@/i18n'
import { translate as tr } from '@/i18n'
import { useTranslation } from 'react-i18next'
import { Link } from '@tanstack/react-router'
import { ChevronsLeft, ChevronsRight } from 'lucide-react'
import { navigation } from '@/components/navigation/items'
import { Tooltip } from '@/components/ui/tooltip'
import { Button } from '@/components/ui/button'
import { useShell } from '@/app/providers/ShellProvider'
export function SidebarNavigation({
  compact = false,
  onNavigate,
}: {
  compact?: boolean
  onNavigate?: () => void
}) {
  useTranslation()

  return (
    <nav aria-label={tr('ui.primary_navigation')} className="sidebar-nav">
      {navigation.map((item, index) => {
        const heading = item.group && item.group !== navigation[index - 1]?.group
        const link = (
          <Link
            to={item.path}
            activeOptions={{ exact: item.path !== '/projects' }}
            activeProps={{ className: 'nav-link active', 'aria-current': 'page' }}
            className="nav-link"
            onClick={onNavigate}
            aria-label={compact ? labelText(item.label) : undefined}
          >
            <item.icon size={19} strokeWidth={1.7} />
            <span>{labelText(item.label)}</span>
          </Link>
        )
        return (
          <div key={item.path}>
            {heading && (
              <div className={`nav-group ${item.group === 'Support' ? 'support-group' : ''}`}>
                <span>{labelText(item.group)}</span>
              </div>
            )}
            {compact ? <Tooltip label={labelText(item.label)}>{link}</Tooltip> : link}
          </div>
        )
      })}
    </nav>
  )
}
export function AppSidebar() {
  useTranslation()

  const { collapsed, toggleSidebar } = useShell()
  return (
    <aside
      className={`app-sidebar ${collapsed ? 'is-collapsed' : ''}`}
      aria-label={tr('ui.workspace_sidebar')}
    >
      <div className="expanded-navigation">
        <SidebarNavigation compact={collapsed} />
      </div>
      <div className="tablet-navigation">
        <SidebarNavigation compact />
      </div>
      <Button
        variant="ghost"
        onClick={toggleSidebar}
        className="collapse-button"
        aria-label={collapsed ? tr('ui.expand_sidebar') : tr('ui.collapse_sidebar')}
        aria-expanded={!collapsed}
      >
        {collapsed ? <ChevronsRight size={18} /> : <ChevronsLeft size={18} />}
        <span>{collapsed ? labelText('Expand') : labelText('Collapse')}</span>
      </Button>
    </aside>
  )
}
