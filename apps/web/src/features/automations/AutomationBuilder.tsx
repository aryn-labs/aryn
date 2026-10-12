import { useState, useRef } from 'react'
import { useQuery, useInfiniteQuery } from '@tanstack/react-query'
import { Link, useSearch, useNavigate, useBlocker } from '@tanstack/react-router'
import { useTranslation } from 'react-i18next'
import { useWorkspace } from '@/app/providers/WorkspaceProvider'
import { StandardLayout } from '@/app/shell/MainWorkspace'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogTitle, DialogDescription } from '@/components/ui/dialog'
import { DataState, QueryError } from '@/components/feedback/DataState'
import { Field, Facts } from '@/components/operations/OperationsUI'
import { summarySchema as permissionsSchema } from '@/lib/types/workspace'
import {
  request,
  write,
  base,
  scoped,
  definitionSchema,
  configurationSchema,
  targetsSchema,
  checkedTargetSchema,
  triggerSchema,
  previewSchema,
  type Configuration,
  type Definition,
} from './api'
import { triggerAvailable, triggerRegistry } from './triggers'

export function AutomationBuilder() {
  const workspace = useWorkspace(),
    search = useSearch({ strict: false }),
    { t } = useTranslation()
  const project =
      'project' in search && typeof search.project === 'string' && search.project
        ? search.project
        : (workspace.project?.id ?? ''),
    edit = 'edit' in search ? String(search.edit ?? '') : ''
  const initial = useQuery({
    queryKey: [
      'automation-edit',
      workspace.context?.user.id,
      workspace.context?.organization.id,
      project,
      edit,
    ],
    enabled: !!edit && !!workspace.context?.projects.some((p) => p.id === project),
    retry: false,
    refetchOnWindowFocus: false,
    staleTime: Infinity,
    queryFn: async ({ signal }) => {
      const value = scoped(
        await request(
          base(project) + '/automations/' + encodeURIComponent(edit),
          definitionSchema,
          { signal },
        ),
        workspace.context!.organization.id,
        project,
      )
      if (value.id !== edit) throw new Error('Definition identity differs')
      return value
    },
  })
  return (
    <StandardLayout title={t('operations.create')}>
      <div className="op-page">
        {workspace.error ? (
          <QueryError error={workspace.error} retry={workspace.retry} />
        ) : workspace.loading ? (
          <DataState kind="loading" />
        ) : !workspace.context?.projects.some((p) => p.id === project) ? (
          <DataState kind="unavailable" />
        ) : edit && initial.error ? (
          <QueryError error={initial.error} retry={() => void initial.refetch()} />
        ) : edit && !initial.data ? (
          <DataState kind="loading" />
        ) : (
          <LoadedBuilder
            key={project + edit + (initial.data?.revision ?? 0)}
            project={project}
            initial={initial.data}
            onReload={() => void initial.refetch()}
          />
        )}
      </div>
    </StandardLayout>
  )
}
function LoadedBuilder({
  project: initialProject,
  initial,
  onReload,
}: {
  project: string
  initial?: Definition
  onReload: () => void
}) {
  const workspace = useWorkspace(),
    { t, i18n } = useTranslation(),
    navigate = useNavigate(),
    [project, setProject] = useState(initialProject),
    [step, setStep] = useState(0),
    [consent, setConsent] = useState(!!initial),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(false),
    [conflict, setConflict] = useState(false),
    [recover, setRecover] = useState(false),
    [previewBusy, setPreviewBusy] = useState(false)
  const defaultConfig = (): Configuration => ({
    title: '',
    target: { kind: 'agent', id: '', version_id: '', payload_hash: '', activation_id: null },
    input: '',
    allow_remote_model: true,
    schedule: {
      kind: 'daily',
      timezone: 'Asia/Jakarta',
      start_at: new Date(Date.now() + 60000).toISOString(),
      interval_minutes: 60,
      local_time: '09:00',
      weekdays: [0, 1, 2, 3, 4],
      cron_expression: null,
    },
    policy: {
      overlap: 'skip',
      missed: 'skip',
      catch_up_limit: 1,
      max_runs_per_day: 24,
      max_tokens_per_task: 4096,
      max_attempts: 1,
      backoff_seconds: 60,
    },
  })
  const [config, setConfig] = useState<Configuration>(
      () => initial?.configuration ?? defaultConfig(),
    ),
    initialSnapshot = useRef(JSON.stringify(config)),
    saved = useRef(false),
    lock = useRef(false),
    [preview, setPreview] = useState<{
      schedule: string
      instants: { utc: string; local: string }[]
    } | null>(null)
  const dirty = !saved.current && JSON.stringify(config) !== initialSnapshot.current,
    blocker = useBlocker({
      shouldBlockFn: () => !saved.current && (dirty || busy),
      enableBeforeUnload: dirty || busy,
      withResolver: true,
    })
  const org = workspace.context!.organization.id,
    user = workspace.context!.user.id,
    owned = !!workspace.context?.projects.some((p) => p.id === project)
  const permissions = useQuery({
    queryKey: ['automation-builder-permissions', user, org, project],
    enabled: owned,
    retry: false,
    queryFn: async ({ signal }) =>
      scoped(
        await request(base(project) + '/summary', permissionsSchema, { signal }),
        org!,
        project,
      ),
  })
  const canManage =
    permissions.data?.permissions['version:approve'] === true &&
    (!initial || initial.owner_actor_id === user)
  const capabilities = useQuery({
    queryKey: ['automation-triggers', user, org, project],
    enabled: owned,
    retry: false,
    queryFn: async ({ signal }) =>
      scoped(
        await request(base(project) + '/automation-triggers', triggerSchema, { signal }),
        org,
        project,
      ),
  })
  const targets = useInfiniteQuery({
    queryKey: ['automation-targets', user, org, project, config.target.kind],
    enabled: owned && canManage,
    initialPageParam: '',
    retry: false,
    queryFn: async ({ signal, pageParam }) =>
      scoped(
        await request(
          base(project) +
            '/automation-targets?' +
            new URLSearchParams({ kind: config.target.kind, after: pageParam, limit: '25' }),
          targetsSchema,
          { signal },
        ),
        org,
        project,
      ),
    getNextPageParam: (last) => last.next ?? undefined,
  })
  const exactTarget = useQuery({
    queryKey: ['automation-target-check', user, org, project, config.target],
    enabled: owned && canManage && !!workspace.csrf && !!config.target.id,
    retry: false,
    queryFn: async () => {
      const item = scoped(
        await write(
          base(project) + '/automation-targets/check',
          config.target,
          checkedTargetSchema,
          workspace.csrf!,
        ),
        org,
        project,
      )
      if (JSON.stringify(item.target) !== JSON.stringify(config.target)) {
        // Property order is not authority; compare the actual pin fields.
        if (
          item.target.id !== config.target.id ||
          item.target.version_id !== config.target.version_id ||
          item.target.payload_hash !== config.target.payload_hash ||
          item.target.activation_id !== config.target.activation_id
        )
          throw new Error('Target pin differs')
      }
      return item
    },
  })
  const targetItems = [
      ...(targets.data?.pages.flatMap((page) => page.items) ?? []),
      ...(exactTarget.data ? [exactTarget.data] : []),
    ].filter(
      (item, i, all) =>
        all.findIndex(
          (value) =>
            value.target?.version_id === item.target?.version_id &&
            value.target?.id === item.target?.id,
        ) === i,
    ),
    validTarget =
      !!config.target.id &&
      !!config.target.version_id &&
      !exactTarget.error &&
      targetItems.some(
        (item) =>
          item.available &&
          item.target?.version_id === config.target.version_id &&
          item.target.id === config.target.id &&
          item.target.payload_hash === config.target.payload_hash &&
          (item.target.activation_id ?? null) === (config.target.activation_id ?? null),
      )
  const previewValid = preview?.schedule === JSON.stringify(config.schedule),
    instants = previewValid ? preview.instants : []
  function schedule(value: Partial<Configuration['schedule']>) {
    setConfig((c) => ({ ...c, schedule: { ...c.schedule, ...value } }))
  }
  async function checkPreview() {
    if (!workspace.csrf || previewBusy) return
    setPreviewBusy(true)
    setError(false)
    try {
      const result = await write(
        base(project) + '/automation-preview',
        { schedule: config.schedule },
        previewSchema,
        workspace.csrf,
      )
      setPreview({ schedule: JSON.stringify(config.schedule), instants: result.instants })
    } catch {
      setError(true)
    } finally {
      setPreviewBusy(false)
    }
  }
  async function save() {
    if (
      lock.current ||
      !workspace.csrf ||
      !canManage ||
      !consent ||
      !validTarget ||
      !configurationSchema.safeParse(config).success ||
      (!previewValid && config.schedule.kind !== 'webhook') ||
      !triggerAvailable(config.schedule.kind, capabilities.data)
    )
      return
    lock.current = true
    setBusy(true)
    setError(false)
    try {
      const body = { ...config, expected_revision: initial?.revision ?? null }
      const value = scoped(
        await write(
          base(project) + '/automations' + (initial ? '/' + encodeURIComponent(initial.id) : ''),
          body,
          definitionSchema,
          workspace.csrf,
        ),
        org,
        project,
      )
      saved.current = true
      await navigate({ to: '/automations', search: { project, automation: value.id } })
    } catch (failure) {
      if (failure && typeof failure === 'object' && 'status' in failure && failure.status === 409)
        setConflict(true)
      setError(true)
    } finally {
      lock.current = false
      setBusy(false)
    }
  }
  const steps = t('operations.steps', { returnObjects: true }) as string[],
    title = t(initial ? 'operations.edit' : 'operations.create'),
    targetStepValid = !!config.title.trim() && !!config.input.trim() && validTarget,
    triggerStepValid =
      triggerAvailable(config.schedule.kind, capabilities.data) &&
      (config.schedule.kind === 'webhook' || previewValid)
  return (
    <>
      <header className="op-header">
        <div>
          <h1>{title}</h1>
          <p>{t('operations.saveHelp')}</p>
        </div>
        <Button variant="secondary" asChild>
          <Link to="/automations" search={{ project }}>
            {t('operations.return')}
          </Link>
        </Button>
      </header>
      <div className="op-builder">
        <div className="op-builder-main">
          <nav className="op-steps" aria-label={title}>
            {steps.map((label, i) => (
              <button
                key={label}
                aria-current={step === i ? 'step' : undefined}
                onClick={() => setStep(i)}
              >
                {String(i + 1).padStart(2, '0')} — {label}
              </button>
            ))}
          </nav>
          <section className="op-form-surface">
            <h2>
              {String(step + 1).padStart(2, '0')} — {steps[step]}
            </h2>
            {step === 0 && (
              <>
                <Field label={t('operations.name')}>
                  <input
                    aria-label={t('operations.name')}
                    value={config.title}
                    maxLength={160}
                    disabled={busy}
                    onChange={(e) => setConfig((c) => ({ ...c, title: e.target.value }))}
                  />
                </Field>
                <Field label={t('operations.project')}>
                  <select
                    aria-label={t('operations.project')}
                    value={project}
                    disabled={!!initial || busy}
                    onChange={(e) => {
                      setProject(e.target.value)
                      setConfig((c) => ({
                        ...c,
                        target: { ...c.target, id: '', version_id: '', payload_hash: '' },
                      }))
                      setPreview(null)
                    }}
                  >
                    <option value="" disabled>
                      {t('operations.project')}
                    </option>
                    {workspace.context?.projects.map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.name}
                      </option>
                    ))}
                  </select>
                </Field>
                <div className="op-choices">
                  {(['agent', 'workflow'] as const).map((kind) => (
                    <button
                      key={kind}
                      aria-pressed={config.target.kind === kind}
                      onClick={() =>
                        setConfig((c) => ({
                          ...c,
                          target: {
                            kind,
                            id: '',
                            version_id: '',
                            payload_hash: '',
                            activation_id: null,
                          },
                        }))
                      }
                    >
                      {kind === 'agent' ? 'Agent' : 'Workflow'}
                      <small>
                        {t(
                          kind === 'agent'
                            ? 'operations.agentFactory'
                            : 'operations.workflowStudio',
                        )}
                      </small>
                    </button>
                  ))}
                </div>
                {permissions.isPending || (canManage && targets.isPending) ? (
                  <DataState kind="loading" />
                ) : permissions.error ? (
                  <QueryError error={permissions.error} retry={() => void permissions.refetch()} />
                ) : !canManage ? (
                  <DataState kind="unauthorized" />
                ) : targets.error ? (
                  <QueryError error={targets.error} retry={() => void targets.refetch()} />
                ) : (
                  <Field label={t('operations.target')}>
                    <select
                      aria-label={t('operations.target')}
                      value={config.target.version_id}
                      onChange={(e) => {
                        const item = targetItems.find(
                          (item) => item.available && item.target?.version_id === e.target.value,
                        )
                        if (item?.target) setConfig((c) => ({ ...c, target: item.target! }))
                      }}
                    >
                      <option value="">{t('operations.chooseTarget')}</option>
                      {targetItems.map((item, i) => (
                        <option
                          key={item.target?.version_id ?? i}
                          value={item.target?.version_id ?? ''}
                          disabled={!item.available}
                        >
                          {item.label}
                          {!item.available ? ' · ' + t('operations.unavailable') : ''}
                        </option>
                      ))}
                    </select>
                  </Field>
                )}
                {targets.data && canManage && !targets.error && !validTarget && (
                  <p className="op-note">
                    {t(
                      targetItems.some((item) => item.available) && !config.target.id
                        ? 'operations.chooseTarget'
                        : 'operations.targetUnavailable',
                    )}
                  </p>
                )}
                {targets.hasNextPage && (
                  <Button variant="secondary" onClick={() => void targets.fetchNextPage()}>
                    {t('operations.more')}
                  </Button>
                )}
                <Facts
                  values={[
                    [t('operations.version'), config.target.version_id],
                    [t('operations.targetHash'), config.target.payload_hash],
                  ]}
                />
                <Field label={t('operations.input')}>
                  <textarea
                    aria-label={t('operations.input')}
                    value={config.input}
                    maxLength={8000}
                    onChange={(e) => setConfig((c) => ({ ...c, input: e.target.value }))}
                  />
                </Field>
              </>
            )}
            {step === 1 && (
              <>
                <div className="op-choices">
                  {triggerRegistry.map((definition) => {
                    const Icon = definition.icon
                    return (
                      <button
                        key={definition.kind}
                        aria-pressed={config.schedule.kind === definition.kind}
                        disabled={!triggerAvailable(definition.kind, capabilities.data)}
                        onClick={() =>
                          schedule({
                            kind: definition.kind as Configuration['schedule']['kind'],
                            cron_expression: definition.kind === 'cron' ? '0 9 * * 1-5' : null,
                          })
                        }
                      >
                        <Icon size={18} />
                        <strong>{t('operations.' + definition.kind)}</strong>
                        <small>{t('operations.triggerHelp.' + definition.kind)}</small>
                      </button>
                    )
                  })}
                </div>
                {capabilities.error && (
                  <QueryError
                    error={capabilities.error}
                    retry={() => void capabilities.refetch()}
                  />
                )}
                <p className="op-note">{t('operations.webhookUnavailable')}</p>
                {config.schedule.kind === 'webhook' ? (
                  <p className="op-note">{t('operations.webhookAuth')}</p>
                ) : (
                  <>
                    <div className="op-form-grid">
                      <Field label={t('operations.timezone')}>
                        <input
                          aria-label={t('operations.timezone')}
                          value={config.schedule.timezone}
                          maxLength={100}
                          onChange={(e) => schedule({ timezone: e.target.value })}
                        />
                      </Field>
                      <Field label={t('operations.start')}>
                        <input
                          aria-label={t('operations.start')}
                          value={config.schedule.start_at}
                          maxLength={40}
                          onChange={(e) => schedule({ start_at: e.target.value })}
                        />
                      </Field>
                    </div>
                    {config.schedule.kind === 'interval' ? (
                      <Field label={t('operations.intervalMinutes')}>
                        <input
                          aria-label={t('operations.intervalMinutes')}
                          type="number"
                          min={1}
                          max={10080}
                          value={config.schedule.interval_minutes}
                          onChange={(e) => schedule({ interval_minutes: Number(e.target.value) })}
                        />
                      </Field>
                    ) : config.schedule.kind === 'cron' ? (
                      <>
                        <Field label={t('operations.cronExpression')}>
                          <input
                            aria-label={t('operations.cronExpression')}
                            value={config.schedule.cron_expression ?? ''}
                            maxLength={160}
                            onChange={(e) => schedule({ cron_expression: e.target.value })}
                          />
                        </Field>
                        <p className="op-note">{t('operations.cronHelp')}</p>
                      </>
                    ) : (
                      <Field label={t('operations.localTime')}>
                        <input
                          aria-label={t('operations.localTime')}
                          type="time"
                          value={config.schedule.local_time}
                          onChange={(e) => schedule({ local_time: e.target.value })}
                        />
                      </Field>
                    )}
                    {config.schedule.kind === 'weekly' && (
                      <fieldset>
                        <legend>{t('operations.weekdays')}</legend>
                        <div className="op-actions">
                          {[0, 1, 2, 3, 4, 5, 6].map((day) => (
                            <label className="op-check" key={day}>
                              <input
                                type="checkbox"
                                checked={config.schedule.weekdays.includes(day)}
                                onChange={(e) =>
                                  schedule({
                                    weekdays: e.target.checked
                                      ? [...config.schedule.weekdays, day].sort()
                                      : config.schedule.weekdays.filter((value) => value !== day),
                                  })
                                }
                              />
                              {new Intl.DateTimeFormat(i18n.language, {
                                weekday: 'short',
                                timeZone: 'UTC',
                              }).format(new Date(Date.UTC(2026, 9, 12 + day)))}
                            </label>
                          ))}
                        </div>
                      </fieldset>
                    )}
                    <Button
                      variant="secondary"
                      disabled={previewBusy}
                      onClick={() => void checkPreview()}
                    >
                      {t('operations.previewAction')}
                    </Button>
                    <h3>{t('operations.preview')}</h3>
                    <p className="op-note">{t('operations.previewHelp')}</p>
                    <ol className="op-preview">
                      {instants.map((value) => (
                        <li key={value.utc}>
                          <time dateTime={value.utc}>{value.local}</time>
                          <small> · {value.utc}</small>
                        </li>
                      ))}
                    </ol>
                  </>
                )}
              </>
            )}
            {step === 2 && (
              <>
                <div className="op-form-grid">
                  {(['overlap', 'missed'] as const).map((key) => (
                    <Field key={key} label={t('operations.' + key)}>
                      <select
                        aria-label={t('operations.' + key)}
                        value={config.policy[key]}
                        onChange={(e) =>
                          setConfig((c) => ({
                            ...c,
                            policy: { ...c.policy, [key]: e.target.value },
                          }))
                        }
                      >
                        {(key === 'overlap' ? ['skip', 'queue'] : ['skip', 'catch_up']).map(
                          (value) => (
                            <option value={value} key={value}>
                              {t('operations.' + value)}
                            </option>
                          ),
                        )}
                      </select>
                    </Field>
                  ))}
                  {(
                    [
                      'catch_up_limit',
                      'max_runs_per_day',
                      'max_tokens_per_task',
                      'max_attempts',
                      'backoff_seconds',
                    ] as const
                  ).map((key, i) => (
                    <Field key={key} label={t('operations.' + key)}>
                      <input
                        aria-label={t('operations.' + key)}
                        type="number"
                        min={[1, 1, 128, 1, 60][i]}
                        max={[3, 100, 32768, 3, 3600][i]}
                        value={config.policy[key]}
                        onChange={(e) =>
                          setConfig((c) => ({
                            ...c,
                            policy: { ...c.policy, [key]: Number(e.target.value) },
                          }))
                        }
                      />
                    </Field>
                  ))}
                </div>
                <p className="op-note">{t('operations.retryHelp')}</p>
              </>
            )}
            {step === 3 && (
              <>
                <Facts
                  values={[
                    [t('operations.name'), config.title],
                    [
                      t('operations.project'),
                      workspace.context?.projects.find((p) => p.id === project)?.name,
                    ],
                    [t('operations.target'), config.target.id],
                    [t('operations.version'), config.target.version_id],
                    [t('operations.targetHash'), config.target.payload_hash],
                    [t('operations.trigger'), t('operations.' + config.schedule.kind)],
                    [t('operations.timezone'), config.schedule.timezone],
                    [
                      t('operations.environment'),
                      capabilities.data
                        ? t('operations.' + capabilities.data.mode)
                        : t('operations.unavailable'),
                    ],
                    [t('operations.scheduler'), capabilities.data?.scheduler.authority],
                  ]}
                />
                <Facts
                  values={Object.entries(config.policy).map(([key, value]) => [
                    t('operations.' + key),
                    typeof value === 'string' ? t('operations.' + value) : String(value),
                  ])}
                />
                <ol className="op-preview">
                  {instants.map((value) => (
                    <li key={value.utc}>{value.local}</li>
                  ))}
                </ol>
                <label className="op-check">
                  <input
                    type="checkbox"
                    checked={consent}
                    onChange={(e) => setConsent(e.target.checked)}
                  />
                  {t('operations.consent')}
                </label>
                <p className="op-note">{t('operations.saveHelp')}</p>
              </>
            )}
            {error && (
              <p className="op-error" role="alert">
                {t(conflict ? 'operations.conflict' : 'operations.error')}
              </p>
            )}
            {conflict && (
              <Button variant="secondary" onClick={() => setRecover(true)}>
                {t('operations.refresh')}
              </Button>
            )}
            <div className="op-actions">
              <Button
                variant="secondary"
                disabled={step === 0 || busy}
                onClick={() => setStep((value) => value - 1)}
              >
                {t('operations.back')}
              </Button>
              {step < 3 ? (
                <Button
                  disabled={
                    busy ||
                    (step === 0 && !targetStepValid) ||
                    (step === 1 && !triggerStepValid) ||
                    !canManage
                  }
                  onClick={() => setStep((value) => value + 1)}
                >
                  {t('operations.next')}
                </Button>
              ) : (
                <Button
                  disabled={
                    busy ||
                    conflict ||
                    !consent ||
                    !targetStepValid ||
                    !triggerStepValid ||
                    !canManage ||
                    !configurationSchema.safeParse(config).success
                  }
                  onClick={() => void save()}
                >
                  {t('operations.pausedSave')}
                </Button>
              )}
            </div>
          </section>
        </div>
        <aside className="op-side">
          <h3>{t('operations.review')}</h3>
          <Facts
            values={[
              [
                t('operations.project'),
                workspace.context?.projects.find((p) => p.id === project)?.name,
              ],
              [t('operations.target'), config.target.id || t('operations.chooseTarget')],
              [t('operations.trigger'), t('operations.' + config.schedule.kind)],
              [t('operations.status'), t('operations.states.paused')],
              [t('operations.approval'), t('operations.needsApproval')],
            ]}
          />
          <p className="op-note">{t('operations.localBoundary')}</p>
        </aside>
      </div>
      <Dialog
        open={blocker.status === 'blocked'}
        onOpenChange={(open) => {
          if (!open) blocker.reset?.()
        }}
      >
        <DialogContent>
          <DialogTitle>{t('operations.unsaved')}</DialogTitle>
          <DialogDescription>{t('operations.saveHelp')}</DialogDescription>
          <div className="op-actions">
            <Button variant="secondary" onClick={() => blocker.reset?.()}>
              {t('operations.keep')}
            </Button>
            <Button onClick={() => blocker.proceed?.()}>{t('operations.discard')}</Button>
          </div>
        </DialogContent>
      </Dialog>
      <Dialog open={recover} onOpenChange={setRecover}>
        <DialogContent>
          <DialogTitle>{t('operations.refresh')}</DialogTitle>
          <DialogDescription>{t('operations.reloadHelp')}</DialogDescription>
          <div className="op-actions">
            <Button variant="secondary" onClick={() => setRecover(false)}>
              {t('operations.keep')}
            </Button>
            <Button
              onClick={() => {
                setRecover(false)
                onReload()
              }}
            >
              {t('operations.confirm')}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </>
  )
}
