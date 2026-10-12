import { useState, useDeferredValue } from 'react'
import { useInfiniteQuery } from '@tanstack/react-query'
import { Link, useNavigate, useSearch } from '@tanstack/react-router'
import { useTranslation } from 'react-i18next'
import { Clock, Plus } from 'lucide-react'
import { useWorkspace } from '@/app/providers/WorkspaceProvider'
import { useSummary } from '@/hooks/use-workspace-queries'
import { StandardLayout } from '@/app/shell/MainWorkspace'
import { Button } from '@/components/ui/button'
import { Field, Status, OperationsBoundary } from '@/components/operations/OperationsUI'
import { DataState, QueryError } from '@/components/feedback/DataState'
import { request, base, scoped, pageSchema, definitionSchema } from './api'
import { AutomationDrawer } from './AutomationDrawer'
export function AutomationsPage() {
  const workspace = useWorkspace(),
    { t } = useTranslation(),
    navigate = useNavigate(),
    search = useSearch({ strict: false }),
    summary = useSummary(),
    [q, setQ] = useState(''),
    [filter, setFilter] = useState<string | null>(null),
    [status, setStatus] = useState(''),
    [trigger, setTrigger] = useState('')
  const project =
      filter ??
      ('project' in search ? String(search.project ?? '') : (workspace.project?.id ?? '')),
    term = useDeferredValue(q.trim()),
    projects = workspace.context?.projects.filter((p) => !project || p.id === project) ?? []
  const query = useInfiniteQuery({
    queryKey: [
      'automation-catalog',
      workspace.context?.user.id,
      workspace.context?.organization.id,
      project,
      term,
      status,
      trigger,
    ],
    enabled: !!projects.length,
    retry: false,
    initialPageParam: null as Record<string, string> | null,
    queryFn: async ({ signal, pageParam }) => {
      const pages = await Promise.all(
        projects
          .filter((p) => !pageParam || pageParam[p.id])
          .map(async (p) => {
            const page = await request(
              base(p.id) +
                '/automations?' +
                new URLSearchParams({
                  q: term,
                  status,
                  trigger,
                  after: pageParam?.[p.id] ?? '',
                  limit: '25',
                }),
              pageSchema(definitionSchema),
              { signal },
            )
            page.items.forEach((item) => scoped(item, workspace.context!.organization.id, p.id))
            return { ...page, project: p.id }
          }),
      )
      return {
        items: pages.flatMap((p) => p.items),
        cursors: Object.fromEntries(pages.filter((p) => p.next).map((p) => [p.project, p.next!])),
      }
    },
    getNextPageParam: (last) => (Object.keys(last.cursors).length ? last.cursors : undefined),
  })
  const items = query.data?.pages.flatMap((p) => p.items) ?? [],
    id = 'automation' in search ? String(search.automation ?? '') : '',
    owner = 'project' in search ? String(search.project ?? '') : ''
  return (
    <StandardLayout title={t('operations.automations')}>
      <div className="op-page">
        <header className="op-header">
          <div>
            <h1>{t('operations.automations')}</h1>
            <p>{t('operations.automationsDescription')}</p>
          </div>
          <div className="op-actions">
            <OperationsBoundary />
            {summary.data?.permissions['version:approve'] ? (
              <Button asChild>
                <Link to="/automations/new" search={{ project: workspace.project?.id }}>
                  <Plus size={16} />
                  {t('operations.create')}
                </Link>
              </Button>
            ) : (
              <Button disabled>
                <Plus size={16} />
                {t('operations.create')}
              </Button>
            )}
          </div>
        </header>
        <div className="op-filters">
          <Field label={t('operations.searchAutomations')}>
            <input
              aria-label={t('operations.searchAutomations')}
              value={q}
              maxLength={160}
              onChange={(e) => setQ(e.target.value)}
            />
          </Field>
          <Field label={t('operations.project')}>
            <select
              aria-label={t('operations.project')}
              value={project}
              onChange={(e) => setFilter(e.target.value)}
            >
              <option value="">{t('operations.allProjects')}</option>
              {workspace.context?.projects.map((p) => (
                <option value={p.id} key={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
          </Field>
          <Field label={t('operations.status')}>
            <select
              aria-label={t('operations.status')}
              value={status}
              onChange={(e) => setStatus(e.target.value)}
            >
              <option value="">{t('operations.allStatuses')}</option>
              {['paused', 'enabled'].map((value) => (
                <option key={value} value={value}>
                  {t('operations.states.' + value)}
                </option>
              ))}
            </select>
          </Field>
          <Field label={t('operations.trigger')}>
            <select
              aria-label={t('operations.trigger')}
              value={trigger}
              onChange={(e) => setTrigger(e.target.value)}
            >
              <option value="">{t('operations.allKinds')}</option>
              {['interval', 'daily', 'weekly', 'cron', 'webhook'].map((kind) => (
                <option key={kind} value={kind}>
                  {t('operations.' + kind)}
                </option>
              ))}
            </select>
          </Field>
        </div>
        <p className="op-summary">
          <Clock size={16} />
          {t('operations.loaded', { count: items.length })}
        </p>
        {workspace.error ? (
          <QueryError error={workspace.error} retry={workspace.retry} />
        ) : query.error ? (
          <QueryError error={query.error} retry={() => void query.refetch()} />
        ) : !workspace.loading && !projects.length ? (
          <DataState kind="unavailable" />
        ) : workspace.loading || query.isPending ? (
          <DataState kind="loading" />
        ) : !items.length ? (
          <div className="op-empty">
            <h2>{t('operations.emptyAutomations')}</h2>
            <p>{t('operations.emptyAutomationsHelp')}</p>
          </div>
        ) : (
          <div className="op-table-wrap">
            <table className="op-table">
              <thead>
                <tr>
                  {['automations', 'status', 'trigger', 'nextRun', 'project'].map((value) => (
                    <th key={value} scope="col">
                      {t('operations.' + value)}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {items.map((item) => (
                  <tr key={item.id}>
                    <td>
                      <button
                        className="op-name"
                        onClick={() =>
                          void navigate({
                            to: '/automations',
                            search: { project: item.project_id, automation: item.id },
                          })
                        }
                      >
                        <span className="op-item-icon">
                          <Clock size={18} />
                        </span>
                        <span>
                          <strong>{item.title}</strong>
                          <small>
                            {item.target_label ?? item.configuration.target.id} ·{' '}
                            {item.configuration.target.kind} ·{' '}
                            {item.configuration.target.version_id}
                          </small>
                        </span>
                      </button>
                    </td>
                    <td>
                      <Status value={item.status} />
                      <small>
                        <br />
                        {t(
                          item.approval_verified
                            ? 'operations.approved'
                            : 'operations.needsApproval',
                        )}
                      </small>
                    </td>
                    <td>
                      {t('operations.' + item.configuration.schedule.kind)}
                      <small>
                        <br />
                        {item.configuration.schedule.timezone}
                      </small>
                    </td>
                    <td>
                      {item.configuration.schedule.kind === 'webhook'
                        ? t('operations.noEventSchedule')
                        : item.status === 'enabled'
                          ? item.next_run_at
                          : t('operations.states.paused')}
                    </td>
                    <td>
                      {workspace.context?.projects.find((p) => p.id === item.project_id)?.name}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {query.hasNextPage && (
          <Button
            variant="secondary"
            onClick={() => void query.fetchNextPage()}
            disabled={query.isFetchingNextPage}
          >
            {t('operations.more')}
          </Button>
        )}
        <p className="op-note">{t('operations.saveHelp')}</p>
        {id && owner && workspace.context && (
          <AutomationDrawer
            key={owner + ':' + id}
            project={owner}
            id={id}
            onClose={() => void navigate({ to: '/automations', search: { project: owner } })}
          />
        )}
      </div>
    </StandardLayout>
  )
}
