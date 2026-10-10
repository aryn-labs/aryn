import { labelText } from '@/i18n'
import { translate as tr } from '@/i18n'
import { useTranslation } from 'react-i18next'
import { Command } from 'cmdk'
import { Search, Bot, CirclePlay, Folder, CornerDownLeft } from 'lucide-react'
import { useNavigate } from '@tanstack/react-router'
import { useState } from 'react'
import { Dialog, DialogContent, DialogTitle, DialogDescription } from '@/components/ui/dialog'
import { useShell } from '@/app/providers/ShellProvider'
import { useWorkspace } from '@/app/providers/WorkspaceProvider'
import { useResources } from '@/hooks/use-workspace-queries'
import { useDebouncedValue } from '@/hooks/use-debounced-value'
import { navigation } from '@/components/navigation/items'
import { Button } from '@/components/ui/button'
export function GlobalSearch() {
  useTranslation()

  const { searchOpen, setSearchOpen, inspect, setMobileOpen } = useShell()
  const { project, context, selectProject } = useWorkspace()
  const [search, setSearch] = useState('')
  const query = useDebouncedValue(search.trim().slice(0, 100))
  const navigate = useNavigate()
  const enabled = searchOpen && query.length >= 2 && !!context
  const agents = useResources('blueprints', query, enabled)
  const runs = useResources('runs', query, enabled)
  const projects = useResources('projects', query, enabled)
  const results = [
    { label: 'Agents', resource: 'blueprints' as const, icon: Bot, result: agents },
    { label: 'Runs', resource: 'runs' as const, icon: CirclePlay, result: runs },
    { label: 'Projects', resource: 'projects' as const, icon: Folder, result: projects },
  ]
  function close() {
    setSearchOpen(false)
    setSearch('')
    setMobileOpen(false)
  }
  const routes = navigation.filter((item) =>
    labelText(item.label).toLowerCase().includes(search.toLowerCase()),
  )
  return (
    <Dialog
      open={searchOpen}
      onOpenChange={(open) => {
        setSearchOpen(open)
        if (!open) setSearch('')
      }}
    >
      <DialogContent
        className="search-dialog"
        onCloseAutoFocus={(event) => {
          event.preventDefault()
          document.querySelector<HTMLButtonElement>('.global-search-trigger')?.focus()
        }}
      >
        <DialogTitle className="sr-only">{tr('ui.global_search')}</DialogTitle>
        <DialogDescription className="sr-only">
          {tr('ui.search_navigation_agents_runs_and_projects_use_arrow_keys_and_enter_to_select')}
        </DialogDescription>
        <Command label={tr('ui.search_workspace')} shouldFilter={false} loop>
          <div className="command-input-row">
            <Search size={20} />
            <Command.Input
              value={search}
              onValueChange={setSearch}
              placeholder={tr('ui.where_would_you_like_to_go')}
              maxLength={100}
              aria-label={tr('ui.search_workspace')}
            />
            <kbd>{tr('ui.esc')}</kbd>
          </div>
          <Command.List className="command-list">
            <Command.Empty>{tr('ui.no_matching_pages_or_resources')}</Command.Empty>
            {routes.length > 0 && (
              <Command.Group heading={tr('ui.navigation')}>
                {routes.map((item) => (
                  <Command.Item
                    key={item.path}
                    value={`nav-${item.path}`}
                    onSelect={() => {
                      close()
                      void navigate({ to: item.path })
                    }}
                  >
                    <item.icon size={18} />
                    <span>{labelText(item.label)}</span>
                    <CornerDownLeft size={14} />
                  </Command.Item>
                ))}
              </Command.Group>
            )}
            {enabled &&
              project &&
              results.map(({ label, resource, icon: Icon, result }) => (
                <Command.Group key={resource} heading={labelText(label)}>
                  {!result.isError &&
                    result.data?.items.map((item) => (
                      <Command.Item
                        key={item.id}
                        value={`${resource}-${item.id}`}
                        onSelect={() => {
                          close()
                          if (resource === 'projects') {
                            selectProject(item.id)
                            inspect(null)
                            void navigate({ to: '/projects' })
                          } else {
                            inspect({ item, resource })
                          }
                        }}
                      >
                        <Icon size={18} />
                        <span>{item.name}</span>
                        <small>{item.status ?? resource}</small>
                      </Command.Item>
                    ))}
                  {result.isSuccess && !result.data.items.length && (
                    <p className="search-note">
                      {tr('ui.no_matching')}
                      {labelText(label).toLowerCase()}.
                    </p>
                  )}
                </Command.Group>
              ))}
          </Command.List>
          {enabled && project && (
            <div aria-live="polite">
              {results.map(({ label, resource, result }) =>
                result.isLoading ? (
                  <p key={resource} className="search-note">
                    {tr('ui.searching')}
                    {labelText(label).toLowerCase()}…
                  </p>
                ) : result.error ? (
                  <div key={resource} className="search-note" role="alert">
                    {label} {tr('ui.search_unavailable')}{' '}
                    <Button variant="ghost" size="sm" onClick={() => void result.refetch()}>
                      {tr('ui.retry')}
                    </Button>
                  </div>
                ) : null,
              )}
            </div>
          )}
          <div className="command-footer">
            <span>
              {project
                ? `Searching in ${project.name}`
                : tr('ui.navigation_only_no_project_available')}
            </span>
            <span>{tr('ui.navigate_open')}</span>
          </div>
        </Command>
      </DialogContent>
    </Dialog>
  )
}
