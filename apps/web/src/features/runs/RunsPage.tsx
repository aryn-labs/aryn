import { useDeferredValue, useState } from 'react'
import { useInfiniteQuery } from '@tanstack/react-query'
import { useNavigate, useSearch } from '@tanstack/react-router'
import { useTranslation } from 'react-i18next'
import { Activity, Bot, Workflow, RefreshCw } from 'lucide-react'
import { useWorkspace } from '@/app/providers/WorkspaceProvider'
import { StandardLayout } from '@/app/shell/MainWorkspace'
import { Button } from '@/components/ui/button'
import { DataState, QueryError } from '@/components/feedback/DataState'
import { Field, Status, OperationsBoundary } from '@/components/operations/OperationsUI'
import { request, base, scoped, catalogSchema } from './api'
import { RunDrawer } from './RunDrawer'
export function RunsPage() {
  const workspace = useWorkspace(),
    { t, i18n } = useTranslation(),
    navigate = useNavigate(),
    search = useSearch({ strict: false })
  const [filter, setFilter] = useState<string | null>(null),
    [q, setQ] = useState(''),
    [kind, setKind] = useState(''),
    [status, setStatus] = useState(''),
    [order, setOrder] = useState('desc'),
    [since, setSince] = useState(''),
    [until, setUntil] = useState('')
  const project = filter ?? ('project' in search ? String(search.project ?? '') : ''),
    term = useDeferredValue(q.trim())
  const projects = workspace.context?.projects.filter((p) => !project || p.id === project) ?? []
  const query = useInfiniteQuery({
    queryKey: [
      'execution-catalog',
      workspace.context?.user.id,
      workspace.context?.organization.id,
      project,
      term,
      kind,
      status,
      order,
      since,
      until,
    ],
    enabled: !!projects.length,
    initialPageParam: null as Record<string, string> | null,
    retry: false,
    queryFn: async ({ signal, pageParam }) => {
      const pages = await Promise.all(
        projects
          .filter((p) => !pageParam || pageParam[p.id])
          .map(async (p) => {
            const args = new URLSearchParams({
              q: term,
              kind,
              status,
              order,
              limit: '25',
              after: pageParam?.[p.id] ?? '',
              since: since ? since + 'T00:00:00+00:00' : '',
              until: until ? until + 'T23:59:59+00:00' : '',
            })
            const page = scoped(
              await request(base(p.id) + '/executions?' + args, catalogSchema, { signal }),
              workspace.context!.organization.id,
              p.id,
            )
            return { ...page, project: p.id }
          }),
      )
      return {
        items: pages.flatMap((p) => p.items),
        cursors: Object.fromEntries(
          pages.filter((p) => p.next_cursor).map((p) => [p.project, p.next_cursor!]),
        ),
      }
    },
    getNextPageParam: (last) => (Object.keys(last.cursors).length ? last.cursors : undefined),
  })
  const items =
    query.data?.pages
      .flatMap((p) => p.items)
      .sort((a, b) => (order === 'desc' ? -1 : 1) * a.created_at.localeCompare(b.created_at)) ?? []
  const selectedProject = 'project' in search ? String(search.project ?? '') : '',
    run = 'run' in search ? String(search.run ?? '') : '',
    runKind = 'runKind' in search && search.runKind === 'workflow' ? 'workflow' : 'agent'
  function open(id: string, owner: string, type: 'agent' | 'workflow') {
    void navigate({ to: '/runs', search: { project: owner, run: id, runKind: type } })
  }
  return (
    <StandardLayout title={t('operations.runs')}>
      <div className="op-page">
        <header className="op-header">
          <div>
            <h1>{t('operations.runs')}</h1>
            <p>{t('operations.runsDescription')}</p>
          </div>
          <div className="op-actions">
            <OperationsBoundary />
            <Button
              variant="secondary"
              onClick={() => void query.refetch()}
              disabled={query.isFetching}
            >
              <RefreshCw size={16} />
              {t('operations.refresh')}
            </Button>
          </div>
        </header>
        <div className="op-filters">
          <Field label={t('operations.searchRuns')}>
            <input
              aria-label={t('operations.searchRuns')}
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
          <Field label={t('operations.kind')}>
            <select
              aria-label={t('operations.kind')}
              value={kind}
              onChange={(e) => setKind(e.target.value)}
            >
              <option value="">{t('operations.allKinds')}</option>
              <option value="agent">Agent</option>
              <option value="workflow">Workflow</option>
            </select>
          </Field>
          <Field label={t('operations.status')}>
            <select
              aria-label={t('operations.status')}
              value={status}
              onChange={(e) => setStatus(e.target.value)}
            >
              <option value="">{t('operations.allStatuses')}</option>
              {[
                'queued',
                'started',
                'running',
                'stopping',
                'waiting_review',
                'completed',
                'failed',
                'cancelled',
                'outcome_unknown',
                'rejected',
              ].map((value) => (
                <option key={value} value={value}>
                  {t('operations.states.' + value)}
                </option>
              ))}
            </select>
          </Field>
          <Field label={t('operations.order')}>
            <select
              aria-label={t('operations.order')}
              value={order}
              onChange={(e) => setOrder(e.target.value)}
            >
              <option value="desc">{t('operations.newest')}</option>
              <option value="asc">{t('operations.oldest')}</option>
            </select>
          </Field>
          <Field label={t('operations.since')}>
            <input
              aria-label={t('operations.since')}
              type="date"
              value={since}
              onChange={(e) => setSince(e.target.value)}
            />
          </Field>
          <Field label={t('operations.until')}>
            <input
              aria-label={t('operations.until')}
              type="date"
              value={until}
              onChange={(e) => setUntil(e.target.value)}
            />
          </Field>
        </div>
        <p className="op-summary">
          <Activity size={16} />
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
            <h2>{t('operations.emptyRuns')}</h2>
            <p>{t('operations.emptyRunsHelp')}</p>
          </div>
        ) : (
          <div className="op-table-wrap">
            <table className="op-table">
              <thead>
                <tr>
                  {['runs', 'status', 'project', 'time', 'duration'].map((key) => (
                    <th key={key} scope="col">
                      {t('operations.' + key)}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {items.map((item) => (
                  <tr key={item.project_id + item.id}>
                    <td>
                      <button
                        className="op-name"
                        onClick={() => open(item.id, item.project_id, item.kind)}
                      >
                        <span className="op-item-icon">
                          {item.kind === 'agent' ? <Bot size={18} /> : <Workflow size={18} />}
                        </span>
                        <span>
                          <strong>{item.name}</strong>
                          <small>
                            {item.kind} · {t('operations.sources.' + item.source)} · {item.id}
                          </small>
                        </span>
                      </button>
                    </td>
                    <td>
                      <Status value={item.status} />
                    </td>
                    <td>
                      {workspace.context?.projects.find((p) => p.id === item.project_id)?.name}
                    </td>
                    <td>
                      <time dateTime={item.created_at}>
                        {new Date(item.created_at).toLocaleString(i18n.language)}
                      </time>
                    </td>
                    <td>
                      {item.duration_seconds == null
                        ? t('operations.unavailable')
                        : item.duration_seconds.toFixed(1) + ' s'}
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
            disabled={query.isFetchingNextPage}
            onClick={() => void query.fetchNextPage()}
          >
            {t('operations.more')}
          </Button>
        )}
        <p className="op-note">{t('operations.observation')}</p>
        {run && selectedProject && workspace.context && (
          <RunDrawer
            key={selectedProject + ':' + runKind + ':' + run}
            project={selectedProject}
            kind={runKind}
            id={run}
            onClose={() => {
              void navigate({ to: '/runs', search: { project: selectedProject } })
            }}
          />
        )}
      </div>
    </StandardLayout>
  )
}
