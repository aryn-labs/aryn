import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Link } from '@tanstack/react-router'
import { useTranslation } from 'react-i18next'
import { useWorkspace } from '@/app/providers/WorkspaceProvider'
import { OperationsDrawer, Facts, Status, Tabs } from '@/components/operations/OperationsUI'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogTitle, DialogDescription } from '@/components/ui/dialog'
import { DataState, QueryError } from '@/components/feedback/DataState'
import { base, scoped, request, write, detailSchema, type Detail } from './api'
import { WorkflowRunGraph } from './WorkflowRunGraph'
import { checkpointTasks } from '@/features/workflows/registry'
import { ArtifactPanel } from '@/features/workflows/WorkflowRunPanel'
import '@/features/workflows/workflows.css'
export function RunDrawer({
  project,
  kind,
  id,
  onClose,
}: {
  project: string
  kind: 'agent' | 'workflow'
  id: string
  onClose: () => void
}) {
  const workspace = useWorkspace(),
    cache = useQueryClient(),
    { t } = useTranslation(),
    [tab, setTab] = useState('summary'),
    [confirm, setConfirm] = useState(false),
    [busy, setBusy] = useState(false),
    [failed, setFailed] = useState(false)
  const root = base(project) + '/executions/' + kind + '/' + encodeURIComponent(id)
  const query = useQuery<Detail>({
    queryKey: [
      'execution-detail',
      workspace.context?.user.id,
      workspace.context?.organization.id,
      project,
      kind,
      id,
    ],
    enabled: !!workspace.context?.projects.some((p) => p.id === project),
    retry: false,
    refetchInterval: (q) =>
      q.state.error
        ? false
        : ['queued', 'started', 'running', 'stopping', 'waiting_review'].includes(
              q.state.data?.status ?? '',
            )
          ? 2000
          : false,
    queryFn: async ({ signal }) => {
      const value = scoped(
        await request(root, detailSchema, { signal }),
        workspace.context!.organization.id,
        project,
      )
      if (value.id !== id || value.kind !== kind) throw new Error('Execution identity differs')
      return value
    },
  })
  const data = !query.error ? query.data : undefined
  const timeline =
    data?.workflow_run && data.workflow_version
      ? checkpointTasks(data.workflow_version.graph, data.workflow_run)
      : (data?.timeline ?? [])
  async function stop() {
    if (!workspace.csrf || busy || !data?.permissions['run:cancel']) return
    setBusy(true)
    setFailed(false)
    try {
      const result = scoped(
        await write(root + '/stop', {}, detailSchema, workspace.csrf),
        workspace.context!.organization.id,
        project,
      )
      if (result.id !== id) throw new Error('Stop identity differs')
      setConfirm(false)
      await Promise.all([
        query.refetch(),
        cache.invalidateQueries({
          predicate: (q) =>
            q.queryKey[0] === 'execution-catalog' &&
            q.queryKey[1] === workspace.context?.user.id &&
            q.queryKey[2] === workspace.context?.organization.id,
        }),
      ])
    } catch {
      setFailed(true)
    } finally {
      setBusy(false)
    }
  }
  const ref = (name: string) =>
    typeof data?.references[name] === 'string' ? (data.references[name] as string) : undefined
  return (
    <OperationsDrawer
      title={data?.name ?? t('operations.runs')}
      description={project + ' · ' + id}
      onClose={onClose}
    >
      {workspace.error ? (
        <QueryError error={workspace.error} retry={workspace.retry} />
      ) : !workspace.context?.projects.some((p) => p.id === project) ? (
        <DataState kind="unavailable" />
      ) : query.error ? (
        <QueryError error={query.error} retry={() => void query.refetch()} />
      ) : !data ? (
        <DataState kind="loading" />
      ) : (
        <>
          <Tabs
            value={tab}
            onChange={setTab}
            items={['summary', 'timeline', 'io', 'evidence'].map((value) => [
              value,
              t('operations.' + value),
            ])}
          />
          {data.status === 'outcome_unknown' && (
            <p className="op-note">{t('operations.unknown')}</p>
          )}
          {tab === 'summary' && (
            <>
              <Facts
                values={[
                  [t('operations.status'), <Status value={data.status} />],
                  [t('operations.source'), t('operations.sources.' + data.source)],
                  [t('operations.time'), data.created_at],
                  [
                    t('operations.duration'),
                    data.duration_seconds == null
                      ? t('operations.unavailable')
                      : data.duration_seconds.toFixed(2) + ' s',
                  ],
                  [
                    t('operations.project'),
                    workspace.context?.projects.find((p) => p.id === project)?.name,
                  ],
                  [
                    t('operations.version'),
                    ref('version_id') ?? ref('agent_version_id') ?? t('operations.unavailable'),
                  ],
                ]}
              />
              {data.workflow_run && data.workflow_version && (
                <WorkflowRunGraph run={data.workflow_run} version={data.workflow_version} />
              )}
            </>
          )}
          {tab === 'timeline' && (
            <>
              <p className="op-note">{t('operations.noTelemetry')}</p>
              <ol className="op-timeline">
                {timeline.map((entry, i) => {
                  const event = entry as Record<string, unknown>
                  return (
                    <li key={String(event.id ?? event.node_id ?? i)}>
                      <strong>{String(event.event ?? event.node_id ?? '')}</strong>{' '}
                      <Status value={String(event.status ?? '')} />
                      {event.occurred_at != null && <small>{String(event.occurred_at)}</small>}
                      {event.core_run_id != null && (
                        <small>
                          <code>{String(event.core_run_id)}</code>
                        </small>
                      )}
                    </li>
                  )
                })}
              </ol>
            </>
          )}
          {tab === 'io' && (
            <>
              <h3>{t('operations.input')}</h3>
              <pre className="op-code">{data.io?.input ?? t('operations.unavailable')}</pre>
              <h3>{t('operations.output')}</h3>
              {data.workflow_run?.artifact_id ? (
                <div className="wf-panel">
                  <ArtifactPanel
                    organization={data.organization_id}
                    project={project}
                    workflow={data.workflow_run.workflow_id}
                    run={data.workflow_run}
                    id={data.workflow_run.artifact_id}
                    user={workspace.context!.user.id}
                    canReview={false}
                    onRefresh={() => void query.refetch()}
                  />
                </div>
              ) : (
                <pre className="op-code">{data.io?.output ?? t('operations.unavailable')}</pre>
              )}
            </>
          )}
          {tab === 'evidence' && (
            <>
              <p>{t(data.verified ? 'operations.verified' : 'operations.notVerified')}</p>
              <Facts
                values={[
                  [t('operations.runId'), id],
                  ...['requestedModel', 'model', 'provider', 'runtime']
                    .map((label, i): [string, unknown] => [
                      t('operations.' + label),
                      data.references[
                        ['requested_model', 'actual_model', 'provider', 'runtime'][i]!
                      ],
                    ])
                    .map(([label, value]): [string, string] => [
                      label,
                      value == null ? t('operations.unavailable') : String(value),
                    ]),
                  [
                    t('operations.tokens'),
                    data.usage?.availability === 'measured'
                      ? String(data.usage.total_tokens)
                      : t('operations.unavailable'),
                  ],
                  [
                    t('operations.cost'),
                    data.usage?.cost_usd == null
                      ? t('operations.unavailable')
                      : String(data.usage.cost_usd),
                  ],
                ]}
              />
              <Facts
                values={Object.entries(data.references)
                  .filter(([, v]) => v != null)
                  .map(([k, v]) => [k, String(v)])}
              />
            </>
          )}
          <div className="op-actions">
            <Button variant="secondary" asChild>
              <Link
                to="/brief"
                search={{
                  project,
                  tab: 'linked',
                  kind: kind === 'workflow' ? 'workflow_run' : 'run',
                  ref: id,
                }}
              >
                {t('intelligence.linked')} · Brief
              </Link>
            </Button>
            {ref('workflow_id') && (
              <Button variant="secondary" asChild>
                <Link
                  to="/workflows/$projectId/$workflowId"
                  params={{ projectId: project, workflowId: ref('workflow_id')! }}
                  search={{ run: id }}
                >
                  {t('operations.workflowStudio')}
                </Link>
              </Button>
            )}
            {ref('blueprint_id') && (
              <Button variant="secondary" asChild>
                <Link
                  to="/agents/$projectId/$blueprintId"
                  params={{ projectId: project, blueprintId: ref('blueprint_id')! }}
                >
                  {t('operations.agentFactory')}
                </Link>
              </Button>
            )}
            {ref('automation_id') && (
              <Button variant="secondary" asChild>
                <Link to="/automations" search={{ project, automation: ref('automation_id') }}>
                  {t('operations.sourceAutomation')}
                </Link>
              </Button>
            )}
            <Button variant="secondary" asChild>
              <Link to="/projects/$projectId/results" params={{ projectId: project }}>
                {t('operations.results')}
              </Link>
            </Button>
            {['running', 'started', 'queued', 'stopping', 'waiting_review'].includes(data.status) &&
              data.permissions['run:cancel'] && (
                <Button onClick={() => setConfirm(true)}>{t('operations.stop')}</Button>
              )}
          </div>
          {failed && (
            <p role="alert" className="op-error">
              {t('operations.error')}
            </p>
          )}
          <Dialog
            open={confirm}
            onOpenChange={(value) => {
              if (!busy) setConfirm(value)
            }}
          >
            <DialogContent closeDisabled={busy}>
              <DialogTitle>{t('operations.stop')}</DialogTitle>
              <DialogDescription>{t('operations.stopHelp')}</DialogDescription>
              <div className="op-actions">
                <Button variant="secondary" disabled={busy} onClick={() => setConfirm(false)}>
                  {t('operations.cancel')}
                </Button>
                <Button disabled={busy} onClick={() => void stop()}>
                  {t('operations.confirm')}
                </Button>
              </div>
            </DialogContent>
          </Dialog>
        </>
      )}
    </OperationsDrawer>
  )
}
