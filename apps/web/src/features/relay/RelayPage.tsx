import {
  useCatalog,
  useCopy,
  useFilters,
  useIntelligenceContext,
  useRecord,
} from '@/components/intelligence/hooks'
import { useState } from 'react'
import { z } from '@/lib/types/validation'
import { useQueryClient } from '@tanstack/react-query'
import { useParams, useSearch } from '@tanstack/react-router'
import { useWorkspace } from '@/app/providers/WorkspaceProvider'
import { Button } from '@/components/ui/button'
import { DataState } from '@/components/feedback/DataState'
import {
  Badge,
  CatalogFilters,
  DateValue,
  Facts,
  Field,
  IntelligenceLayout,
  JsonFacts,
  More,
  MutationDialog,
  Notice,
  Panel,
  QueryState,
  ResourceLink,
  ScopeGuard,
} from '@/components/intelligence/IntelligenceUI'
import {
  incidentStates,
  incidentSchema,
  incidentDetailSchema,
  fixtureSchema,
  capsuleSchema,
  type Incident,
  base,
  request,
  scoped,
  write,
} from '@/features/intelligence/api'
import { ApiError } from '@/lib/api/client'
import { BundleWorkspace, ProjectName } from '@/features/brief/BriefPage'
import { OperationalTargetsPanel } from './OperationalTargetsPanel'

export function RelayPage() {
  const c = useCopy(),
    search = useSearch({ strict: false }),
    filters = useFilters('project' in search ? String(search.project ?? '') : ''),
    [tab, setTab] = useState('incidents'),
    [create, setCreate] = useState(false),
    w = useWorkspace()
  return (
    <IntelligenceLayout
      module="relay"
      tabs={['incidents', 'targets', 'capsules', 'fixtures']}
      tab={tab}
      onTab={setTab}
      actions={
        tab === 'fixtures' ? (
          <Button disabled={!w.project} onClick={() => setCreate(true)}>
            {c('createFixture')}
          </Button>
        ) : undefined
      }
    >
      {tab === 'fixtures' && <Notice warning>{c('demoBoundary')}</Notice>}
      {tab === 'targets' ? (
        <OperationalTargetsPanel project={filters.project || w.project?.id || ''} />
      ) : tab === 'fixtures' ? (
        <FixtureCatalog project={filters.project || w.project?.id || ''} />
      ) : tab === 'capsules' ? (
        <CapsuleCatalog filters={filters} />
      ) : (
        <IncidentCatalog filters={filters} />
      )}
      {create && (
        <FixtureCreate
          initialProject={filters.project || w.project?.id || ''}
          onClose={() => setCreate(false)}
        />
      )}
    </IntelligenceLayout>
  )
}
function CapsuleCatalog({ filters }: { filters: ReturnType<typeof useFilters> }) {
  const c = useCopy(),
    query = useCatalog('/relay/capsules', capsuleSchema, filters.project)
  const items = query.error ? [] : (query.data?.pages.flatMap((page) => page.items) ?? [])
  return (
    <>
      <CatalogFilters filters={filters} />
      <QueryState query={query} empty={!items.length} />
      <div className="intel-stack">
        {items
          .filter(
            (item) =>
              !filters.term ||
              item.id.includes(filters.term) ||
              item.incident_id.includes(filters.term),
          )
          .map((item) => (
            <Panel key={item.id} title={item.id}>
              <Badge
                value={item.outcome ?? (item.recovered === true ? 'RECOVERED' : 'unavailable')}
              />
              <DateValue value={item.created_at} />
              <Facts
                values={[
                  [c('project'), <ProjectName id={item.project_id} />],
                  [
                    c('incidents'),
                    <ResourceLink
                      project={item.project_id}
                      kind="incident"
                      id={item.incident_id}
                    />,
                  ],
                  [c('reason'), item.failure_reason ?? null],
                ]}
              />
              <ResourceLink project={item.project_id} kind="capsule" id={item.id}>
                {c('openCapsule')}
              </ResourceLink>
            </Panel>
          ))}
      </div>
      <More query={query} />
    </>
  )
}
function IncidentCatalog({ filters }: { filters: ReturnType<typeof useFilters> }) {
  const c = useCopy(),
    query = useCatalog('/relay', incidentSchema, filters.project, {
      q: filters.term,
      status: filters.status,
    }),
    items = query.error ? [] : (query.data?.pages.flatMap((p) => p.items) ?? [])
  return (
    <>
      <CatalogFilters filters={filters} states={incidentStates} />
      <QueryState query={query} empty={!items.length} />
      {items.length > 0 && (
        <div className="intel-table-wrap">
          <table className="intel-table">
            <thead>
              <tr>
                {['incidents', 'severity', 'status', 'target', 'project', 'updated'].map((k) => (
                  <th key={k}>{c(k)}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {items.map((i) => (
                <tr key={i.id}>
                  <td>
                    <ResourceLink project={i.project_id} kind="incident" id={i.id}>
                      {i.title}
                    </ResourceLink>
                    <small>{i.id}</small>
                  </td>
                  <td>
                    <Badge value={i.severity} tone={i.severity === 'high' ? 'bad' : 'warn'} />
                  </td>
                  <td>
                    <Badge value={i.status} />
                  </td>
                  <td>
                    <code>{i.target_id}</code>
                  </td>
                  <td>
                    <ProjectName id={i.project_id} />
                  </td>
                  <td>
                    <DateValue value={i.updated_at} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <More query={query} />
    </>
  )
}
function FixtureCreate({
  initialProject,
  onClose,
}: {
  initialProject: string
  onClose: () => void
}) {
  const c = useCopy(),
    w = useWorkspace(),
    [project, setProject] = useState(initialProject),
    [name, setName] = useState(''),
    permission = useIntelligenceContext(project),
    cache = useQueryClient()
  return (
    <MutationDialog
      title={c('createFixture')}
      description={c('demoBoundary')}
      project={project}
      path="/relay/demo-fixtures"
      body={{ name: name.trim() }}
      allowed={!!permission.data?.permissions['run:create'] && !!name.trim()}
      onClose={onClose}
      onSuccess={async () => {
        await cache.invalidateQueries({ queryKey: ['intelligence-catalog'] })
      }}
    >
      <Field label={c('project')}>
        <select value={project} onChange={(e) => setProject(e.target.value)}>
          {w.context?.projects.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
            </option>
          ))}
        </select>
      </Field>
      <Field label={c('title')}>
        <input value={name} maxLength={100} onChange={(e) => setName(e.target.value)} />
      </Field>
    </MutationDialog>
  )
}
function FixtureCatalog({ project }: { project: string }) {
  const c = useCopy(),
    w = useWorkspace(),
    [selectedOwner, setOwner] = useState(''),
    owner = selectedOwner || project || w.project?.id || '',
    query = useCatalog('/relay/demo-fixtures', fixtureSchema, owner),
    permission = useIntelligenceContext(owner),
    [action, setAction] = useState<{
      id: string
      revision: number
      running: boolean
      blocking_fault: boolean
      signal: boolean
    } | null>(null),
    [running, setRunning] = useState(false),
    [fault, setFault] = useState(false),
    [dedup, setDedup] = useState(''),
    cache = useQueryClient()
  const items = query.error ? [] : (query.data?.pages.flatMap((p) => p.items) ?? [])
  return (
    <>
      <div className="intel-filters">
        <Field label={c('project')}>
          <select value={owner} onChange={(e) => setOwner(e.target.value)}>
            {w.context?.projects.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
        </Field>
        <Button variant="secondary" onClick={() => void query.refetch()}>
          {c('refresh')}
        </Button>
      </div>
      <QueryState query={query} empty={!items.length} />
      <div className="intel-stack">
        {items.map((f) => (
          <Panel key={f.id} title={f.name}>
            <Facts
              values={[
                [c('target'), <code>{f.id}</code>],
                [c('revision'), f.revision],
                [c('running'), c(f.running ? 'yes' : 'no')],
                [c('blockingFault'), c(f.blocking_fault ? 'yes' : 'no')],
                [c('updated'), <DateValue value={f.updated_at} />],
              ]}
            />
            <div className="intel-actions">
              <Button
                variant="secondary"
                disabled={!permission.data?.permissions['run:create']}
                onClick={() => {
                  setRunning(f.running)
                  setFault(f.blocking_fault)
                  setAction({ ...f, signal: false })
                }}
              >
                {c('changeFixture')}
              </Button>
              <Button
                disabled={
                  !permission.data?.permissions['run:create'] || (f.running && !f.blocking_fault)
                }
                onClick={() => {
                  setDedup(crypto.randomUUID())
                  setAction({ ...f, signal: true })
                }}
              >
                {c('collectSignal')}
              </Button>
            </div>
          </Panel>
        ))}
      </div>
      <More query={query} />
      {action && (
        <MutationDialog
          title={c(action.signal ? 'collectSignal' : 'changeFixture')}
          description={c('demoBoundary')}
          project={owner}
          path={action.signal ? '/relay/signals' : '/relay/demo-fixtures/' + action.id}
          body={
            action.signal
              ? { target_id: action.id, dedup_key: dedup, severity: 'medium' }
              : { expected_revision: action.revision, running, blocking_fault: fault }
          }
          allowed={
            !!permission.data?.permissions['run:create'] && (!action.signal || !!dedup.trim())
          }
          onClose={() => setAction(null)}
          onSuccess={async () => {
            await cache.invalidateQueries({ queryKey: ['intelligence-catalog'] })
          }}
        >
          {action.signal ? (
            <Field label={c('dedup')}>
              <input value={dedup} maxLength={128} onChange={(e) => setDedup(e.target.value)} />
            </Field>
          ) : (
            <>
              <Field label={c('running')}>
                <input
                  type="checkbox"
                  checked={running}
                  onChange={(e) => setRunning(e.target.checked)}
                />
              </Field>
              <Field label={c('blockingFault')}>
                <input
                  type="checkbox"
                  checked={fault}
                  onChange={(e) => setFault(e.target.checked)}
                />
              </Field>
              <code>
                {action.id} · {c('revision')} {action.revision}
              </code>
            </>
          )}
        </MutationDialog>
      )}
    </>
  )
}
export function IncidentDetailPage() {
  const { projectId = '', incidentId = '' } = useParams({ strict: false })
  return (
    <ScopeGuard project={projectId}>
      <IncidentDetail key={incidentId} project={projectId} id={incidentId} />
    </ScopeGuard>
  )
}
function PendingCancellation({
  project,
  id,
  onResult,
}: {
  project: string
  id: string
  onResult: (confirmed: boolean) => void
}) {
  const c = useCopy(),
    w = useWorkspace(),
    permission = useIntelligenceContext(project)
  const [busy, setBusy] = useState(false),
    [failed, setFailed] = useState(false),
    [confirmed, setConfirmed] = useState<boolean | null>(null)
  async function cancel() {
    if (busy || !w.context || !w.csrf || !permission.data?.permissions['run:cancel']) return
    setBusy(true)
    setFailed(false)
    try {
      const current = scoped(
        await request(base(project) + '/relay/' + id, incidentDetailSchema),
        w.context.organization.id,
        project,
      )
      if (current.id !== id) throw new ApiError(502, 'errors.scope')
      const result = await write(
        base(project) + '/relay/' + id + '/cancel',
        { expected_revision: current.revision },
        z.object({ cancellation_confirmed: z.boolean() }),
        w.csrf,
      )
      setConfirmed(result.cancellation_confirmed)
      onResult(result.cancellation_confirmed)
    } catch {
      setFailed(true)
    } finally {
      setBusy(false)
    }
  }
  return (
    <div aria-live="polite">
      <Notice>{c('cancellationHelp')}</Notice>
      <Button
        variant="secondary"
        disabled={busy || confirmed !== null || !permission.data?.permissions['run:cancel']}
        onClick={() => void cancel()}
      >
        {c('cancelExecution')}
      </Button>
      {confirmed !== null && (
        <Notice warning={!confirmed}>
          {c(confirmed ? 'cancellationConfirmed' : 'cancellationUncertain')}
        </Notice>
      )}
      {failed && <p role="alert">{c('conflictError')}</p>}
    </div>
  )
}
function IncidentDetail({ project, id }: { project: string; id: string }) {
  const c = useCopy(),
    query = useRecord(project, '/relay', id, incidentDetailSchema),
    permission = useIntelligenceContext(project),
    data = query.error ? undefined : query.data,
    [reason, setReason] = useState(''),
    [cancellation, setCancellation] = useState<boolean | null>(null),
    [action, setAction] = useState<{ name: string; body: Record<string, unknown> } | null>(null),
    cache = useQueryClient()
  function start(name: string, i: Incident) {
    setReason('')
    const body: Record<string, unknown> =
      name === 'investigate' ||
      name === 'reconcile' ||
      name === 'close' ||
      name === 'cancel' ||
      name === 'capsule'
        ? { expected_revision: i.revision }
        : name === 'proposals'
          ? {
              expected_revision: i.revision,
              action: i.demo ? 'restart_demo' : 'restart_service',
              target_id: i.target_id,
              target_revision: i.fixture.revision,
              bundle_id: i.bundle_id,
            }
          : name === 'approve'
            ? { payload_hash: i.proposal!.payload_hash }
            : {
                proposal_id: i.proposal!.id,
                payload_hash: i.proposal!.payload_hash,
                idempotency_key: crypto.randomUUID(),
              }
    setAction({ name, body })
  }
  const run = !!permission.data?.permissions['run:create'],
    review = run && !!permission.data?.permissions['version:approve'],
    mayReason = action?.name === 'proposals' || action?.name === 'approve'
  const names: Record<string, string> = {
    investigate: 'investigate',
    proposals: 'propose',
    approve: 'approve',
    execute: 'execute',
    reconcile: 'reconcile',
    close: 'close',
    cancel: 'cancelExecution',
    capsule: 'captureCapsule',
  }
  return (
    <IntelligenceLayout module="relay" back refresh={() => void query.refetch()}>
      <QueryState query={query} />
      {data && (
        <>
          <h2 className="intel-title">{data.title}</h2>
          <div className="intel-meta">
            <ProjectName id={project} />
            <code>{data.id}</code>
            <DateValue value={data.updated_at} />
          </div>
          <div className="intel-actions">
            <Badge value={data.status} />
            <Badge value={data.severity} tone={data.severity === 'high' ? 'bad' : 'warn'} />
          </div>
          <Notice warning>{c(data.demo ? 'demoBoundary' : 'operationalBoundary')}</Notice>
          {data.status === 'OUTCOME_UNKNOWN' && <Notice warning>{c('unknown')}</Notice>}
          {cancellation !== null && (
            <Notice warning={!cancellation}>
              {c(cancellation ? 'cancellationConfirmed' : 'cancellationUncertain')}
            </Notice>
          )}
          <Button
            variant="secondary"
            disabled={
              !permission.data?.permissions['run:cancel'] ||
              !['PROPOSED', 'EXECUTING', 'OUTCOME_UNKNOWN'].includes(data.status)
            }
            onClick={() => start('cancel', data)}
          >
            {c('cancelExecution')}
          </Button>
          <Panel title={c('lifecycle')}>
            <ol className="intel-steps">
              {incidentStates.map((state) => (
                <li key={state} aria-current={data.status === state ? 'step' : undefined}>
                  {state}
                </li>
              ))}
            </ol>
          </Panel>
          <div className="intel-split">
            <div className="intel-stack">
              <Panel title={c('timeline')}>
                <ol className="intel-timeline">
                  {data.timeline.map((e) => (
                    <li key={e.id}>
                      <strong>{e.event}</strong> · <Badge value={e.to_status} />
                      <DateValue value={e.created_at} />
                      <code>{e.reference_id}</code>
                    </li>
                  ))}
                </ol>
              </Panel>
              <Panel title={c('investigation')}>
                <div className="intel-actions">
                  <Button
                    disabled={
                      !run ||
                      !permission.data?.permissions['version:create'] ||
                      !['OPEN', 'INVESTIGATING', 'DEGRADED'].includes(data.status)
                    }
                    onClick={() => start('investigate', data)}
                  >
                    {c('investigate')}
                  </Button>
                </div>
                {data.bundle ? (
                  <>
                    <ResourceLink kind="bundle" project={project} id={data.bundle.id}>
                      {data.bundle.title}
                    </ResourceLink>
                    <BundleWorkspace bundle={data.bundle} />
                  </>
                ) : (
                  <DataState title={c('empty')} description={c('abstention')} />
                )}
              </Panel>
            </div>
            <aside className="intel-stack">
              <Panel title={c('proposal')}>
                <Facts
                  values={[
                    [c('target'), <code>{data.target_id}</code>],
                    [c('revision'), data.fixture.revision],
                    [c('owner'), data.owner_id],
                  ]}
                />
                {data.proposal ? (
                  <>
                    <Facts
                      values={[
                        [c('proposal'), data.proposal.id],
                        [c('revision'), data.proposal.target_revision],
                        [c('payloadHash'), <code>{data.proposal.payload_hash}</code>],
                        [c('digest'), <code>{data.proposal.bundle_digest}</code>],
                        [c('reason'), data.proposal.reason],
                        [c('connectionIdentity'), data.proposal.configuration_hash ?? null],
                        [
                          c('approvalExpiry'),
                          data.proposal.expires_at ? (
                            <DateValue
                              value={new Date(data.proposal.expires_at * 1000).toISOString()}
                            />
                          ) : null,
                        ],
                      ]}
                    />
                    <details>
                      <summary>{c('review')}</summary>
                      <p className="intel-caption">{data.proposal.preconditions}</p>
                      <p className="intel-caption">{data.proposal.reversible_intent}</p>
                      <Facts
                        values={[
                          [c('health'), data.proposal.verification.kind],
                          [c('running'), c('yes')],
                          [c('blockingFault'), c('no')],
                        ]}
                      />
                    </details>
                  </>
                ) : (
                  <DataState title={c('empty')} />
                )}
                <Button
                  variant="secondary"
                  disabled={
                    !run ||
                    !['INVESTIGATING', 'DEGRADED', 'PROPOSED'].includes(data.status) ||
                    !data.bundle_id
                  }
                  onClick={() => start('proposals', data)}
                >
                  {c('propose')}
                </Button>
              </Panel>
              <Panel title={c('approval')}>
                {data.approval ? (
                  <Facts
                    values={[
                      [c('reference'), data.approval.approval_id],
                      [c('owner'), data.approval.approved_by],
                      [c('payloadHash'), <code>{data.approval.payload_hash}</code>],
                    ]}
                  />
                ) : data.execution ? (
                  <Facts
                    values={[
                      [c('execution'), data.execution.id],
                      [c('payloadHash'), <code>{data.execution.payload_hash}</code>],
                    ]}
                  />
                ) : (
                  <p className="intel-caption">{c('unavailable')}</p>
                )}
                <div className="intel-actions">
                  <Button
                    variant="secondary"
                    disabled={!review || data.status !== 'PROPOSED' || !data.proposal}
                    onClick={() => start('approve', data)}
                  >
                    {c('approve')}
                  </Button>
                  <Button
                    disabled={
                      !run || data.status !== 'PROPOSED' || !data.proposal || !data.approval
                    }
                    onClick={() => start('execute', data)}
                  >
                    {c('execute')}
                  </Button>
                </div>
              </Panel>
              <Panel title={c('health')}>
                <Notice warning={!data.verification?.recovered}>{c('independent')}</Notice>
                {data.execution && (
                  <Facts
                    values={[
                      [c('execution'), data.execution.id],
                      [c('status'), data.execution.status],
                      [
                        c('revision'),
                        `${data.execution.before_revision} → ${data.execution.after_revision ?? '—'}`,
                      ],
                      [c('result'), data.execution.error_code],
                    ]}
                  />
                )}
                {data.execution?.action_receipt && (
                  <details>
                    <summary>{c('actionReceipt')}</summary>
                    <JsonFacts data={data.execution.action_receipt} />
                  </details>
                )}
                {data.verification ? (
                  <>
                    <Badge value={data.verification.recovered ? 'RECOVERED' : 'DEGRADED'} />
                    <Facts
                      values={[
                        [c('reference'), data.verification.id],
                        [c('revision'), data.verification.target_revision],
                        [c('observed'), data.verification.observation_id],
                        [c('digest'), <code>{data.verification.digest}</code>],
                      ]}
                    />
                  </>
                ) : (
                  <p>{c('notRecovered')}</p>
                )}
                <div className="intel-actions">
                  <Button
                    variant="secondary"
                    disabled={!review || data.status !== 'OUTCOME_UNKNOWN'}
                    onClick={() => start('reconcile', data)}
                  >
                    {c('reconcile')}
                  </Button>
                  {!data.demo && (
                    <Button
                      variant="secondary"
                      disabled={
                        !run ||
                        !['DEGRADED', 'OUTCOME_UNKNOWN'].includes(data.status) ||
                        !data.execution
                      }
                      onClick={() => start('capsule', data)}
                    >
                      {c('captureCapsule')}
                    </Button>
                  )}
                  <Button
                    disabled={
                      !run ||
                      data.status !== 'RECOVERED' ||
                      !data.verification?.recovered ||
                      data.verification.target_revision !== data.fixture.revision ||
                      !data.fixture.running ||
                      data.fixture.blocking_fault
                    }
                    onClick={() => start('close', data)}
                  >
                    {c('close')}
                  </Button>
                </div>
              </Panel>
              {data.capsule && (
                <Panel title={c('capsule')}>
                  <ResourceLink project={project} kind="capsule" id={data.capsule.id} />
                  <p>
                    <a
                      href={
                        '/api/projects/' +
                        encodeURIComponent(project) +
                        '/relay/capsules/' +
                        data.capsule.id +
                        '/download'
                      }
                    >
                      {c('export')}
                    </a>
                  </p>
                </Panel>
              )}
            </aside>
          </div>
        </>
      )}
      {action && (
        <MutationDialog
          title={c(names[action.name] ?? action.name)}
          description={c(
            action.name === 'cancel'
              ? 'cancellationHelp'
              : action.name === 'reconcile'
                ? 'unknown'
                : data?.demo
                  ? 'demoBoundary'
                  : 'operationalBoundary',
          )}
          project={project}
          path={'/relay/' + id + '/' + action.name}
          body={{ ...action.body, ...(mayReason ? { reason: reason.trim() } : {}) }}
          pendingActions={
            action.name === 'execute' ? (
              <PendingCancellation project={project} id={id} onResult={setCancellation} />
            ) : undefined
          }
          allowed={
            (action.name === 'cancel'
              ? !!permission.data?.permissions['run:cancel']
              : action.name === 'approve' || action.name === 'reconcile'
                ? review
                : run) &&
            (!mayReason || !!reason.trim())
          }
          onClose={() => setAction(null)}
          onSuccess={async (result) => {
            if (action.name === 'cancel')
              setCancellation(
                z.object({ cancellation_confirmed: z.boolean() }).parse(result)
                  .cancellation_confirmed,
              )
            await query.refetch()
            await cache.invalidateQueries({ queryKey: ['intelligence-catalog'] })
          }}
        >
          <Facts
            values={Object.entries(action.body).map(([k, v]) => [k, <code>{String(v)}</code>])}
          />
          {mayReason && (
            <Field label={c('reason')}>
              <textarea
                value={reason}
                maxLength={1000}
                onChange={(e) => setReason(e.target.value)}
              />
            </Field>
          )}
        </MutationDialog>
      )}
    </IntelligenceLayout>
  )
}
