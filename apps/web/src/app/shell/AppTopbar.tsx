import { translate as tr } from '@/i18n'
import { useTranslation } from 'react-i18next'
import { useRef, useState } from 'react'
import {
  Building2,
  Folder,
  Search,
  ChevronDown,
  Bell,
  Menu,
  Sun,
  Moon,
  LogOut,
  UserRound,
  LoaderCircle,
} from 'lucide-react'
import { Brand } from '@/components/navigation/Brand'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
} from '@/components/ui/dropdown-menu'
import { Dialog, DialogContent, DialogTitle, DialogDescription } from '@/components/ui/dialog'
import { DataState, QueryError } from '@/components/feedback/DataState'
import { useShell } from '@/app/providers/ShellProvider'
import { useWorkspace } from '@/app/providers/WorkspaceProvider'
import { logout } from '@/lib/auth/session'
type Panel = 'notifications' | 'account' | null
export function AppTopbar() {
  useTranslation()

  const shell = useShell()
  const workspace = useWorkspace()
  const { context, project } = workspace
  const [panel, setPanel] = useState<Panel>(null)
  const returnFocus = useRef<HTMLButtonElement | null>(null)
  function openPanel(value: Exclude<Panel, null>, trigger = tr('ui.account_menu')) {
    returnFocus.current = document.querySelector<HTMLButtonElement>(`[aria-label="${trigger}"]`)
    setPanel(value)
  }
  const [loggingOut, setLoggingOut] = useState(false)
  const [logoutError, setLogoutError] = useState<Error | null>(null)
  const initials = context?.user.name
    .trim()
    .split(/\s+/)
    .slice(0, 2)
    .map((part) => part[0])
    .join('')
    .toUpperCase()
  async function signOut() {
    if (!workspace.csrf) return
    setLoggingOut(true)
    setLogoutError(null)
    try {
      await logout(workspace.csrf)
      workspace.clearSession()
      setPanel(null)
    } catch (error) {
      setLogoutError(error instanceof Error ? error : new Error('Sign out failed. Try again.'))
    } finally {
      setLoggingOut(false)
    }
  }
  return (
    <header className="app-topbar">
      <Button
        variant="ghost"
        size="icon"
        className="mobile-menu"
        onClick={() => shell.setMobileOpen(true)}
        aria-label={tr('ui.open_navigation')}
      >
        <Menu size={20} />
      </Button>
      <div className="topbar-brand">
        <Brand />
      </div>
      <DropdownMenu modal={false}>
        <DropdownMenuTrigger asChild>
          <Button
            variant="ghost"
            className="workspace-switcher"
            disabled={!context}
            aria-label={tr('ui.switch_workspace')}
            aria-describedby="workspace-current-selection"
            title={
              context
                ? `${context.organization.name} / ${project?.name ?? tr('ui.no_accessible_projects')}`
                : undefined
            }
          >
            <Folder size={18} aria-hidden="true" />
            <span id="workspace-current-selection" className="workspace-switcher-text">
              <span className="workspace-organization">
                {context?.organization.name ?? tr('ui.aryn_studio')}
              </span>
              <strong className="workspace-project">
                {project?.name ??
                  (context
                    ? tr('ui.no_accessible_projects')
                    : workspace.loading
                      ? tr('ui.loading_workspace_59')
                      : workspace.signedOut
                        ? tr('ui.signed_out')
                        : tr('ui.workspace_unavailable'))}
              </strong>
            </span>
            <ChevronDown size={14} aria-hidden="true" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent className="workspace-menu" align="start">
          <DropdownMenuLabel className="workspace-menu-organization">
            <Building2 size={19} aria-hidden="true" />
            <span>
              <small>{tr('ui.workspace')}</small>
              <strong>{context?.organization.name}</strong>
            </span>
          </DropdownMenuLabel>
          <DropdownMenuSeparator className="menu-separator" />
          <DropdownMenuLabel>{tr('ui.projects')}</DropdownMenuLabel>
          {context?.projects.length ? (
            <DropdownMenuRadioGroup
              value={project?.id ?? ''}
              aria-label={tr('ui.projects')}
              onValueChange={(id) => {
                workspace.selectProject(id)
                shell.inspect(null)
              }}
            >
              {context.projects.map((item) => (
                <DropdownMenuRadioItem key={item.id} value={item.id}>
                  <Folder size={16} aria-hidden="true" />
                  <span>{item.name}</span>
                </DropdownMenuRadioItem>
              ))}
            </DropdownMenuRadioGroup>
          ) : (
            <p className="menu-note">{tr('ui.no_accessible_projects_70')}</p>
          )}
        </DropdownMenuContent>
      </DropdownMenu>
      <button
        className="global-search-trigger"
        onClick={() => shell.setSearchOpen(true)}
        aria-label={tr('ui.global_search')}
        aria-keyshortcuts="Control+k Meta+k"
      >
        <Search size={17} />
        <span>{tr('ui.search_workspace_124')}</span>
        <kbd>{tr('ui.ctrl_k')}</kbd>
      </button>
      <div className="topbar-actions">
        <Button
          variant="ghost"
          size="icon"
          onClick={() => openPanel('notifications', tr('ui.notifications'))}
          aria-label={tr('ui.notifications')}
        >
          <Bell size={19} />
        </Button>
        <DropdownMenu modal={false}>
          <DropdownMenuTrigger asChild>
            <Button
              variant="ghost"
              size="icon"
              className="account-trigger"
              aria-label={tr('ui.account_menu')}
              title={context?.user.name ?? tr('ui.account_unavailable')}
            >
              <span className="avatar" aria-hidden="true">
                {initials || <UserRound size={17} />}
              </span>
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuLabel>
              {context?.user.name ?? tr('ui.account_unavailable')}
            </DropdownMenuLabel>
            <DropdownMenuItem onSelect={() => openPanel('account')}>
              <UserRound size={16} />
              {tr('ui.account_details')}
            </DropdownMenuItem>
            <DropdownMenuItem onSelect={shell.toggleTheme}>
              {shell.theme === 'dark' ? <Sun size={16} /> : <Moon size={16} />}
              {tr('ui.use')} {shell.theme === 'dark' ? tr('ui.light') : tr('ui.dark')}{' '}
              {tr('ui.theme')}
            </DropdownMenuItem>
            {context?.mode === 'hosted' && (
              <>
                <DropdownMenuSeparator className="menu-separator" />
                <DropdownMenuItem onSelect={() => openPanel('account')}>
                  <LogOut size={16} />
                  {tr('ui.sign_out_134')}
                </DropdownMenuItem>
              </>
            )}
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
      <Dialog
        open={panel !== null}
        onOpenChange={(open) => {
          if (!open) setPanel(null)
        }}
      >
        <DialogContent
          onCloseAutoFocus={(event) => {
            event.preventDefault()
            returnFocus.current?.focus()
          }}
        >
          <DialogTitle>
            {panel === 'notifications' ? tr('ui.notifications') : tr('ui.your_account')}
          </DialogTitle>
          <DialogDescription>
            {panel === 'notifications'
              ? tr('ui.notifications_for_your_workspace')
              : tr('ui.your_identity_is_managed_by_aryn')}
          </DialogDescription>
          {panel === 'notifications' && (
            <DataState
              kind="unavailable"
              title={tr('ui.notifications_unavailable')}
              description={tr(
                'ui.the_current_api_does_not_expose_a_notification_feed_or_unread_count',
              )}
            />
          )}
          {panel === 'account' && (
            <>
              {context ? (
                <dl className="detail-list">
                  <dt>{tr('ui.name')}</dt>
                  <dd>{context.user.name}</dd>
                  <dt>{tr('ui.role')}</dt>
                  <dd>{context.user.role}</dd>
                  <dt>{tr('ui.organization')}</dt>
                  <dd>{context.organization.name}</dd>
                  <dt>{tr('ui.authentication')}</dt>
                  <dd>
                    {context.mode === 'hosted'
                      ? tr('ui.server_session_oidc')
                      : context.mode === 'development'
                        ? tr('ui.local_development_session')
                        : tr('ui.isolated_test_session')}
                  </dd>
                </dl>
              ) : (
                <DataState
                  kind="unavailable"
                  description={tr('ui.account_details_require_an_authenticated_workspace')}
                />
              )}
              {context?.mode === 'hosted' && (
                <Button variant="secondary" onClick={() => void signOut()} disabled={loggingOut}>
                  {loggingOut && <LoaderCircle size={16} className="animate-spin" />}
                  {tr('ui.sign_out')}
                </Button>
              )}
              {logoutError && <QueryError error={logoutError} retry={() => void signOut()} />}
            </>
          )}
        </DialogContent>
      </Dialog>
    </header>
  )
}
