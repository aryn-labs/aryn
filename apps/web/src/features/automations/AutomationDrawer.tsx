import { useState, useRef, useEffect } from 'react'
import { useQuery, useInfiniteQuery, useQueryClient } from '@tanstack/react-query'
import { Link } from '@tanstack/react-router'
import { useTranslation } from 'react-i18next'
import { useWorkspace } from '@/app/providers/WorkspaceProvider'
import { useSummary } from '@/hooks/use-workspace-queries'
import { OperationsDrawer, Facts, Status, Tabs, Field } from '@/components/operations/OperationsUI'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogTitle, DialogDescription } from '@/components/ui/dialog'
import { DataState, QueryError } from '@/components/feedback/DataState'
import { z } from '@/lib/types/validation'
import {
  request,
  base,
  scoped,
  write,
  pageSchema,
  definitionSchema,
  occurrenceSchema,
  eventSchema,
  triggerSchema,
  type Occurrence,
} from './api'
export function AutomationDrawer({
  project,
  id,
  onClose,
}: {
  project: string
  id: string
  onClose: () => void
}) {
  const workspace = useWorkspace(),
    cache = useQueryClient(),
    { t, i18n } = useTranslation(),
    summary = useSummary(project),
    [tab, setTab] = useState('configuration'),
    [action, setAction] = useState(''),
    [reason, setReason] = useState(''),
    [ack, setAck] = useState(false),
    [selected, setSelected] = useState<Occurrence | null>(null),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(false),
    [secret, setSecret] = useState<{ secret: string; url: string } | null>(null),
    [uncertain, setUncertain] = useState(false)
  const key = [
      'aryn-automation-manual',
      workspace.context?.user.id,
      workspace.context?.organization.id,
      project,
      id,
    ].join(':'),
    intent = useRef<{ key: string; revision: number } | null>(null),
    lock = useRef(false)
  useEffect(() => {
    try {
      const value: unknown = JSON.parse(sessionStorage.getItem(key) ?? 'null')
      if (
        value &&
        typeof value === 'object' &&
        'key' in value &&
        typeof value.key === 'string' &&
        /^[a-f0-9-]{36}$/.test(value.key) &&
        'revision' in value &&
        typeof value.revision === 'number' &&
        Number.isSafeInteger(value.revision) &&
        value.revision > 0
      ) {
        intent.current = { key: value.key, revision: value.revision }
        setUncertain(true)
      }
    } catch {
      /* Optional local intent storage. */
    }
  }, [key])
  const root = base(project) + '/automations/' + encodeURIComponent(id),
    scopeKey = [workspace.context?.user.id, workspace.context?.organization.id, project, id],
    allowed = !!workspace.context?.projects.some((p) => p.id === project)
  const query = useQuery({
    queryKey: ['automation-detail', ...scopeKey],
    enabled: allowed,
    retry: false,
    queryFn: async ({ signal }) => {
      const value = scoped(
        await request(root, definitionSchema, { signal }),
        workspace.context!.organization.id,
        project,
      )
      if (value.id !== id) throw new Error('Automation identity differs')
      return value
    },
  })
  const capability = useQuery({
    queryKey: ['automation-triggers', ...scopeKey.slice(0, 3)],
    enabled: allowed,
    retry: false,
    queryFn: async ({ signal }) =>
      scoped(
        await request(base(project) + '/automation-triggers', triggerSchema, { signal }),
        workspace.context!.organization.id,
        project,
      ),
  })
  const history = useInfiniteQuery({
    queryKey: ['automation-occurrences', ...scopeKey],
    enabled: allowed,
    initialPageParam: '',
    retry: false,
    refetchInterval: tab === 'occurrences' ? 2500 : false,
    queryFn: async ({ signal, pageParam }) => {
      const page = await request(
        root + '/occurrences?' + new URLSearchParams({ limit: '25', after: pageParam }),
        pageSchema(occurrenceSchema),
        { signal },
      )
      page.items.forEach((item) => {
        scoped(item, workspace.context!.organization.id, project)
        if (item.automation_id !== id) throw new Error('Occurrence identity differs')
      })
      return page
    },
    getNextPageParam: (last) => last.next ?? undefined,
  })
  const events = useInfiniteQuery({
    queryKey: ['automation-events', ...scopeKey],
    enabled: allowed && tab === 'activity',
    initialPageParam: '',
    retry: false,
    queryFn: async ({ signal, pageParam }) => {
      const page = await request(
        root + '/events?' + new URLSearchParams({ limit: '25', after: pageParam }),
        pageSchema(eventSchema),
        { signal },
      )
      page.items.forEach((item) => {
        scoped(item, workspace.context!.organization.id, project)
        if (item.automation_id !== id) throw new Error('Activity identity differs')
      })
      return page
    },
    getNextPageParam: (last) => last.next ?? undefined,
  })
  const data = !query.error ? query.data : undefined,
    canManage =
      !!data &&
      data.owner_actor_id === workspace.context?.user.id &&
      summary.data?.permissions['version:approve'] === true
  async function mutate() {
    if (!data || !workspace.csrf || !canManage || lock.current) return
    lock.current = true
    setBusy(true)
    setError(false)
    try {
      if (action === 'approve')
        await write(
          root + '/approve',
          { expected_revision: data.revision, payload_hash: data.payload_hash, reason },
          z.object({ approval_id: z.string() }),
          workspace.csrf,
        )
      else if (action === 'enable' || action === 'pause')
        await write(
          root + '/state',
          { expected_revision: data.revision, enabled: action === 'enable' },
          definitionSchema,
          workspace.csrf,
        )
      else if (action === 'manual') {
        const value = intent.current ?? { key: crypto.randomUUID(), revision: data.revision }
        intent.current = value
        try {
          sessionStorage.setItem(key, JSON.stringify(value))
        } catch {
          /* Intent retained in memory. */
        }
        const receipt = await write(
          root + '/run',
          { expected_revision: value.revision, idempotency_key: value.key },
          occurrenceSchema,
          workspace.csrf,
          true,
        )
        scoped(receipt, workspace.context!.organization.id, project)
        if (receipt.automation_id !== id) throw new Error('Manual occurrence identity differs')
        intent.current = null
        setUncertain(false)
        try {
          sessionStorage.removeItem(key)
        } catch {
          /* Optional. */
        }
        setTab('occurrences')
      } else if (action === 'reconcile' && selected)
        await write(
          root + '/occurrences/' + encodeURIComponent(selected.id) + '/reconcile',
          { reason, acknowledge_no_retry: true },
          occurrenceSchema,
          workspace.csrf,
        )
      else if (action === 'rotate' || action === 'revoke') {
        const receipt = await write(
          root + '/webhook',
          { expected_revision: data.revision, action },
          z.object({ id: z.string(), secret: z.string().nullable(), url: z.string() }),
          workspace.csrf,
        )
        if (receipt.secret) setSecret({ secret: receipt.secret, url: receipt.url })
      }
      setAction('')
      setReason('')
      setAck(false)
      await Promise.all([
        query.refetch(),
        history.refetch(),
        events.refetch(),
        cache.invalidateQueries({
          predicate: (q) =>
            q.queryKey[0] === 'automation-catalog' &&
            q.queryKey[1] === workspace.context?.user.id &&
            q.queryKey[2] === workspace.context?.organization.id,
        }),
      ])
    } catch {
      setError(true)
      if (action === 'manual') setUncertain(true)
    } finally {
      lock.current = false
      setBusy(false)
    }
  }
  const rows = history.data?.pages.flatMap((page) => page.items) ?? [],
    label = t('operations.' + action)
  return (
    <OperationsDrawer
      title={data?.title ?? t('operations.automations')}
      description={project + ' · ' + id}
      onClose={onClose}
    >
      {workspace.error ? (
        <QueryError error={workspace.error} retry={workspace.retry} />
      ) : !allowed ? (
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
            items={['configuration', 'occurrences', 'activity'].map((value) => [
              value,
              t('operations.' + value),
            ])}
          />
          {tab === 'configuration' && (
            <>
              <Status value={data.status} />
              <p>
                {t(data.approval_verified ? 'operations.approved' : 'operations.needsApproval')}
              </p>
              <Facts
                values={[
                  [t('operations.target'), data.target_label ?? data.configuration.target.id],
                  [t('operations.targetKind'), data.configuration.target.kind],
                  [t('operations.version'), data.configuration.target.version_id],
                  [t('operations.targetHash'), data.configuration.target.payload_hash],
                  [t('operations.hash'), data.payload_hash],
                  [t('operations.trigger'), t('operations.' + data.configuration.schedule.kind)],
                  [t('operations.timezone'), data.configuration.schedule.timezone],
                  [t('operations.start'), data.configuration.schedule.start_at],
                  [t('operations.cronExpression'), data.configuration.schedule.cron_expression],
                  [
                    t('operations.localTime'),
                    ['daily', 'weekly'].includes(data.configuration.schedule.kind)
                      ? data.configuration.schedule.local_time
                      : null,
                  ],
                  [
                    t('operations.intervalMinutes'),
                    data.configuration.schedule.kind === 'interval'
                      ? data.configuration.schedule.interval_minutes
                      : null,
                  ],
                  [
                    t('operations.weekdays'),
                    data.configuration.schedule.kind === 'weekly'
                      ? data.configuration.schedule.weekdays
                          .map((day) =>
                            new Intl.DateTimeFormat(i18n.language, {
                              weekday: 'short',
                              timeZone: 'UTC',
                            }).format(new Date(Date.UTC(2026, 9, 12 + day))),
                          )
                          .join(', ')
                      : null,
                  ],
                  [
                    t('operations.nextRun'),
                    data.configuration.schedule.kind === 'webhook'
                      ? t('operations.noEventSchedule')
                      : data.status === 'enabled'
                        ? data.next_run_at
                        : t('operations.states.paused'),
                  ],
                  [
                    t('operations.lastOccurrence'),
                    data.last_occurrence_id ?? t('operations.unavailable'),
                  ],
                  [t('operations.owner'), data.owner_actor_id],
                  [
                    t('operations.environment'),
                    capability.data
                      ? t('operations.' + capability.data.mode)
                      : t('operations.unavailable'),
                  ],
                  [t('operations.scheduler'), capability.data?.scheduler.authority],
                  [t('operations.lastTick'), capability.data?.scheduler.last_tick_at],
                  [t('operations.schedulerError'), capability.data?.scheduler.error_code],
                ]}
              />
              <h3>{t('operations.configuration')}</h3>
              <Facts
                values={Object.entries(data.configuration.policy).map(([key, value]) => [
                  t('operations.' + key),
                  typeof value === 'string' ? t('operations.' + value) : String(value),
                ])}
              />
              <p className="op-note">{t('operations.localBoundary')}</p>
              <p className="op-note">{t('operations.retryHelp')}</p>
              <div className="op-actions">
                {canManage && (
                  <Button variant="secondary" asChild>
                    <Link to="/automations/new" search={{ project, edit: id }}>
                      {t('operations.edit')}
                    </Link>
                  </Button>
                )}
                {canManage && !data.approval_verified && (
                  <Button onClick={() => setAction('approve')}>{t('operations.approve')}</Button>
                )}
                {canManage && (
                  <Button
                    variant="secondary"
                    disabled={data.status === 'paused' && !data.approval_verified}
                    onClick={() => setAction(data.status === 'enabled' ? 'pause' : 'enable')}
                  >
                    {t(data.status === 'enabled' ? 'operations.pause' : 'operations.enable')}
                  </Button>
                )}
                {canManage && data.status === 'enabled' && data.approval_verified && (
                  <Button onClick={() => setAction('manual')}>
                    {t(uncertain ? 'operations.retrySame' : 'operations.manual')}
                  </Button>
                )}
              </div>
              {data.configuration.schedule.kind === 'webhook' && (
                <section>
                  <h3>{t('operations.webhook')}</h3>
                  <p className="op-note">{t('operations.webhookAuth')}</p>
                  <p className="op-note">{t('operations.credentialHelp')}</p>
                  <code>{data.webhook?.url ?? t('operations.webhookUnavailable')}</code>
                  {canManage && data.approval_verified && capability.data?.webhook_available && (
                    <div className="op-actions">
                      <Button onClick={() => setAction('rotate')}>{t('operations.rotate')}</Button>
                      {data.webhook && (
                        <Button variant="secondary" onClick={() => setAction('revoke')}>
                          {t('operations.revoke')}
                        </Button>
                      )}
                    </div>
                  )}
                </section>
              )}
            </>
          )}
          {tab === 'occurrences' &&
            (history.error ? (
              <QueryError error={history.error} retry={() => void history.refetch()} />
            ) : (
              <>
                <p className="op-note">{t('operations.unknown')}</p>
                {!rows.length ? (
                  <p>{t('operations.noOccurrences')}</p>
                ) : (
                  <div className="op-table-wrap">
                    <table className="op-table">
                      <thead>
                        <tr>
                          {['time', 'status', 'attempts', 'runLink'].map((value) => (
                            <th scope="col" key={value}>
                              {t('operations.' + value)}
                            </th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {rows.map((row) => (
                          <tr key={row.id}>
                            <td>
                              <time dateTime={row.scheduled_at}>{row.scheduled_at}</time>
                              <small>
                                {row.admitted_at && (
                                  <>
                                    <br />
                                    {t('operations.admitted')}: {row.admitted_at}
                                  </>
                                )}
                              </small>
                              <br />
                              <code>{row.error_code}</code>
                            </td>
                            <td>
                              <Status value={row.status} />
                              {row.status === 'outcome_unknown' && canManage && (
                                <Button
                                  variant="secondary"
                                  onClick={() => {
                                    setSelected(row)
                                    setAction('reconcile')
                                  }}
                                >
                                  {t('operations.reconcile')}
                                </Button>
                              )}
                            </td>
                            <td>
                              {row.attempts}
                              {row.retry_at && <small>{row.retry_at}</small>}
                            </td>
                            <td>
                              {row.run_id ? (
                                <Link
                                  to="/runs"
                                  search={{ project, run: row.run_id, runKind: row.run_kind }}
                                >
                                  {row.run_id}
                                </Link>
                              ) : (
                                t('operations.unavailable')
                              )}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
                {history.hasNextPage && (
                  <Button
                    onClick={() => void history.fetchNextPage()}
                    disabled={history.isFetchingNextPage}
                  >
                    {t('operations.more')}
                  </Button>
                )}
              </>
            ))}
          {tab === 'activity' &&
            (events.error ? (
              <QueryError error={events.error} retry={() => void events.refetch()} />
            ) : (
              <>
                <ol className="op-timeline">
                  {events.data?.pages
                    .flatMap((page) => page.items)
                    .map((event) => (
                      <li key={event.id}>
                        <strong>{event.event}</strong>
                        <small>{event.created_at}</small>
                      </li>
                    ))}
                </ol>
                {!events.data?.pages[0]?.items.length && <p>{t('operations.noEvents')}</p>}
                {events.hasNextPage && (
                  <Button onClick={() => void events.fetchNextPage()}>
                    {t('operations.more')}
                  </Button>
                )}
              </>
            ))}
          {uncertain && (
            <p role="alert" className="op-note">
              {t('operations.pendingManual')}
            </p>
          )}
          {error && (
            <p role="alert" className="op-error">
              {t('operations.error')}
            </p>
          )}
          <Dialog
            open={!!action}
            onOpenChange={(open) => {
              if (!open && !busy) setAction('')
            }}
          >
            <DialogContent closeDisabled={busy}>
              <DialogTitle>{label}</DialogTitle>
              <DialogDescription>
                {t(
                  action === 'manual'
                    ? 'operations.manualHelp'
                    : action === 'reconcile'
                      ? 'operations.reconcileHelp'
                      : 'operations.saveHelp',
                )}
              </DialogDescription>
              <Facts
                values={[
                  [t('operations.hash'), data.payload_hash],
                  [t('operations.version'), data.configuration.target.version_id],
                ]}
              />
              {['approve', 'reconcile'].includes(action) && (
                <Field label={t('operations.reason')}>
                  <textarea
                    aria-label={t('operations.reason')}
                    minLength={5}
                    maxLength={500}
                    value={reason}
                    onChange={(e) => setReason(e.target.value)}
                  />
                </Field>
              )}
              {action === 'reconcile' && (
                <label className="op-check">
                  <input type="checkbox" checked={ack} onChange={(e) => setAck(e.target.checked)} />
                  {t('operations.acknowledge')}
                </label>
              )}
              <div className="op-actions">
                <Button variant="secondary" disabled={busy} onClick={() => setAction('')}>
                  {t('operations.cancel')}
                </Button>
                <Button
                  onClick={() => void mutate()}
                  disabled={
                    busy ||
                    (['approve', 'reconcile'].includes(action) && reason.trim().length < 5) ||
                    (action === 'reconcile' && !ack)
                  }
                >
                  {t('operations.confirm')}
                </Button>
              </div>
            </DialogContent>
          </Dialog>
          <Dialog
            open={!!secret}
            onOpenChange={(open) => {
              if (!open) setSecret(null)
            }}
          >
            <DialogContent>
              <DialogTitle>{t('operations.secret')}</DialogTitle>
              <DialogDescription>{t('operations.oneTime')}</DialogDescription>
              <code>{secret?.url}</code>
              <pre className="op-code">{secret?.secret}</pre>
              <Button onClick={() => setSecret(null)}>{t('operations.secretDismiss')}</Button>
            </DialogContent>
          </Dialog>
        </>
      )}
    </OperationsDrawer>
  )
}
