import type { ReactNode } from 'react'
import { Moon, Sun, type LucideIcon } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useShell } from '@/app/providers/ShellProvider'
import { Button } from '@/components/ui/button'
import { Tooltip } from '@/components/ui/tooltip'
import arynLogo from '@/assets/aryn-logo.png'

export function StudioWorkspace({
  header,
  navigation,
  notices,
  children,
}: {
  header: ReactNode
  navigation: ReactNode
  notices?: ReactNode
  children: ReactNode
}) {
  return (
    <div className="studio-workspace">
      {header}
      <div className="studio-workspace-body">
        {navigation}
        <div className="studio-workspace-content">
          {notices}
          {children}
        </div>
      </div>
    </div>
  )
}

export type StudioNavigationItem = {
  id: string
  label: string
  icon: LucideIcon
  active?: boolean
  disabled?: boolean
  controls?: string
  expanded?: boolean
  onClick: (trigger: HTMLButtonElement) => void
}
export function StudioNavigation({
  items,
  inert = false,
}: {
  items: StudioNavigationItem[]
  inert?: boolean
}) {
  const { t } = useTranslation()
  const { theme, toggleTheme } = useShell()
  const ThemeIcon = theme === 'dark' ? Sun : Moon
  return (
    <nav className="studio-navigation" aria-label={t('studio.navigation')} inert={inert}>
      <span className="brand-symbol studio-rail-mark" aria-hidden="true">
        <img src={arynLogo} alt="" width={858} height={707} />
      </span>
      <div className="studio-navigation-items">
        {items.map(({ id, label, icon: Icon, active, disabled, controls, expanded, onClick }) => (
          <Tooltip label={label} key={id}>
            <Button
              id={id}
              variant="ghost"
              size="icon"
              aria-label={label}
              aria-pressed={active}
              aria-controls={controls}
              aria-expanded={expanded}
              disabled={disabled}
              onClick={(event) => onClick(event.currentTarget)}
            >
              <Icon size={19} strokeWidth={1.7} />
            </Button>
          </Tooltip>
        ))}
      </div>
      <Tooltip label={t(theme === 'dark' ? 'studio.lightMode' : 'studio.darkMode')}>
        <Button
          className="studio-theme"
          variant="ghost"
          size="icon"
          onClick={toggleTheme}
          aria-label={t(theme === 'dark' ? 'studio.lightMode' : 'studio.darkMode')}
        >
          <ThemeIcon size={18} />
        </Button>
      </Tooltip>
    </nav>
  )
}
