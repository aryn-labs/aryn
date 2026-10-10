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
  const shell = useShell()
  const workspace = useWorkspace()
  const { context, project } = workspace
  const [panel, setPanel] = useState<Panel>(null)
  const returnFocus = useRef<HTMLButtonElement | null>(null)
  function openPanel(value: Exclude<Panel, null>, trigger = 'Account menu') {
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
        aria-label="Open navigation"
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
            aria-label="Switch workspace"
            aria-describedby="workspace-current-selection"
            title={
              context
                ? `${context.organization.name} / ${project?.name ?? 'No accessible projects'}`
                : undefined
            }
          >
            <Folder size={18} aria-hidden="true" />
            <span id="workspace-current-selection" className="workspace-switcher-text">
              <span className="workspace-organization">
                {context?.organization.name ?? 'ARYN Studio'}
              </span>
              <strong className="workspace-project">
                {project?.name ??
                  (context
                    ? 'No accessible projects'
                    : workspace.loading
                      ? 'Loading workspace…'
                      : workspace.signedOut
                        ? 'Signed out'
                        : 'Workspace unavailable')}
              </strong>
            </span>
            <ChevronDown size={14} aria-hidden="true" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent className="workspace-menu" align="start">
          <DropdownMenuLabel className="workspace-menu-organization">
            <Building2 size={19} aria-hidden="true" />
            <span>
              <small>Organization</small>
              <strong>{context?.organization.name}</strong>
            </span>
          </DropdownMenuLabel>
          <p className="menu-note">Organization switching unavailable.</p>
          <DropdownMenuSeparator className="menu-separator" />
          <DropdownMenuLabel>Projects</DropdownMenuLabel>
          {context?.projects.length ? (
            <DropdownMenuRadioGroup
              value={project?.id ?? ''}
              aria-label="Projects"
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
            <p className="menu-note">No accessible projects.</p>
          )}
        </DropdownMenuContent>
      </DropdownMenu>
      <button
        className="global-search-trigger"
        onClick={() => shell.setSearchOpen(true)}
        aria-label="Global search"
        aria-keyshortcuts="Control+k Meta+k"
      >
        <Search size={17} />
        <span>Search workspace…</span>
        <kbd>Ctrl K</kbd>
      </button>
      <div className="topbar-actions">
        <Button
          variant="ghost"
          size="icon"
          onClick={() => openPanel('notifications', 'Notifications')}
          aria-label="Notifications"
        >
          <Bell size={19} />
        </Button>
        <DropdownMenu modal={false}>
          <DropdownMenuTrigger asChild>
            <Button
              variant="ghost"
              size="icon"
              className="account-trigger"
              aria-label="Account menu"
              title={context?.user.name ?? 'Account unavailable'}
            >
              <span className="avatar" aria-hidden="true">
                {initials || <UserRound size={17} />}
              </span>
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuLabel>{context?.user.name ?? 'Account unavailable'}</DropdownMenuLabel>
            <DropdownMenuItem onSelect={() => openPanel('account')}>
              <UserRound size={16} />
              Account details
            </DropdownMenuItem>
            <DropdownMenuItem onSelect={shell.toggleTheme}>
              {shell.theme === 'dark' ? <Sun size={16} /> : <Moon size={16} />}Use{' '}
              {shell.theme === 'dark' ? 'light' : 'dark'} theme
            </DropdownMenuItem>
            {context?.mode === 'hosted' && (
              <>
                <DropdownMenuSeparator className="menu-separator" />
                <DropdownMenuItem onSelect={() => openPanel('account')}>
                  <LogOut size={16} />
                  Sign out…
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
          <DialogTitle>{panel === 'notifications' ? 'Notifications' : 'Your account'}</DialogTitle>
          <DialogDescription>
            {panel === 'notifications'
              ? 'Notifications for your workspace.'
              : 'Your identity is managed by ARYN.'}
          </DialogDescription>
          {panel === 'notifications' && (
            <DataState
              kind="unavailable"
              title="Notifications unavailable"
              description="The current API does not expose a notification feed or unread count."
            />
          )}
          {panel === 'account' && (
            <>
              {context ? (
                <dl className="detail-list">
                  <dt>Name</dt>
                  <dd>{context.user.name}</dd>
                  <dt>Role</dt>
                  <dd>{context.user.role}</dd>
                  <dt>Organization</dt>
                  <dd>{context.organization.name}</dd>
                  <dt>Authentication</dt>
                  <dd>
                    {context.mode === 'hosted'
                      ? 'Server session · OIDC'
                      : context.mode === 'development'
                        ? 'Local development session'
                        : 'Isolated test session'}
                  </dd>
                </dl>
              ) : (
                <DataState
                  kind="unavailable"
                  description="Account details require an authenticated workspace."
                />
              )}
              {context?.mode === 'hosted' && (
                <Button variant="secondary" onClick={() => void signOut()} disabled={loggingOut}>
                  {loggingOut && <LoaderCircle size={16} className="animate-spin" />}Sign out
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
