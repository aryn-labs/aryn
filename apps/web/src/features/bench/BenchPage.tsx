import {
  useCatalog,
  useCopy,
  useFilters,
  useIntelligenceContext,
  useRecord,
} from '@/components/intelligence/hooks'
import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useNavigate, useParams, useSearch } from '@tanstack/react-router'
import { useWorkspace } from '@/app/providers/WorkspaceProvider'
import { Button } from '@/components/ui/button'
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
  Tabs,
} from '@/components/intelligence/IntelligenceUI'
import {
  base,
  request,
  evaluationSchema,
  evaluationDetailSchema,
  replaySchema,
  replayDetailSchema,
  capsuleSchema,
  suitesSchema,
  type Evaluation,
} from '@/features/intelligence/api'
import { ProjectName } from '@/features/brief/BriefPage'
import { SuiteAuthoringPanel } from './SuiteAuthoringPanel'
import { ScenarioCandidateDialog } from './ScenarioCandidateDialog'

export function BenchPage() {
  const c = useCopy(),
    search = useSearch({ strict: false }),
    [tab, setTab] = useState(
      'tab' in search && ['suites', 'baselines', 'replays'].includes(String(search.tab))
        ? String(search.tab)
        : 'evaluations',
    ),
    filters = useFilters('project' in search ? String(search.project ?? '') : ''),
    w = useWorkspace()
  return (
    <IntelligenceLayout
      module="bench"
      tab={tab}
      tabs={['evaluations', 'suites', 'baselines', 'replays']}
      onTab={setTab}
      actions={
        <Button asChild variant="secondary">
          <Link to="/agents">{c('startEvaluation')}</Link>
        </Button>
      }
    >
      <Notice>
        {c(tab === 'replays' ? 'replayBoundary' : tab === 'suites' ? 'suitesHelp' : 'passedHelp')}
      </Notice>
      {tab === 'suites' ? (
        <Suites project={filters.project || w.project?.id || ''} />
      ) : tab === 'replays' ? (
        <Replays filters={filters} />
      ) : (
        <Evaluations filters={filters} baseline={tab === 'baselines'} />
      )}
    </IntelligenceLayout>
  )
}
function useSuites(project: string) {
  const w = useWorkspace()
  return useQuery({
    queryKey: ['intelligence-suites', w.context?.user.id, w.context?.organization.id, project],
    enabled: !!w.context?.projects.some((p) => p.id === project),
    retry: false,
    queryFn: ({ signal }) => request(base(project) + '/bench/suites', suitesSchema, { signal }),
  })
}
function Evaluations({
  filters,
  baseline,
}: {
  filters: ReturnType<typeof useFilters>
  baseline: boolean
}) {
  const c = useCopy(),
    w = useWorkspace(),
    [blueprint, setBlueprint] = useState(''),
    [version, setVersion] = useState(''),
    [suite, setSuite] = useState(''),
    query = useCatalog('/bench/evaluations', evaluationSchema, filters.project, {
      q: filters.term,
      status: filters.status,
      blueprint_id: blueprint,
      version_id: version,
      suite_id: suite,
    }),
    manifest = useSuites(filters.project || w.project?.id || ''),
    items = query.error ? [] : (query.data?.pages.flatMap((p) => p.items) ?? [])
  return (
    <>
      {baseline && <Notice>{c('baselineHelp')}</Notice>}
      <CatalogFilters filters={filters} states={['passed', 'failed']}>
        <Field label={c('blueprint')}>
          <input
            value={blueprint}
            maxLength={64}
            pattern="[A-Za-z0-9_-]*"
            onChange={(e) => setBlueprint(e.target.value.replace(/[^A-Za-z0-9_-]/g, ''))}
          />
        </Field>
        <Field label={c('version')}>
          <input
            value={version}
            maxLength={64}
            onChange={(e) => setVersion(e.target.value.replace(/[^A-Za-z0-9_-]/g, ''))}
          />
        </Field>
        <Field label={c('suite')}>
          <select value={suite} onChange={(e) => setSuite(e.target.value)}>
            <option value="">{c('allSuites')}</option>
            {manifest.data?.items.map((s) => (
              <option key={s.suite_id} value={s.suite_id}>
                {s.name}
              </option>
            ))}
          </select>
        </Field>
      </CatalogFilters>
      <QueryState query={query} empty={!items.length} />
      {items.length > 0 && (
        <div className="intel-table-wrap">
          <table className="intel-table">
            <thead>
              <tr>
                {[
                  'evaluations',
                  'result',
                  'integrity',
                  'version',
                  'score',
                  'regression',
                  'date',
                ].map((k) => (
                  <th key={k}>{c(k)}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {items.map((e) => (
                <tr key={e.id}>
                  <td>
                    <ResourceLink kind="evaluation" project={e.project_id} id={e.id}>
                      {e.blueprint_name}
                    </ResourceLink>
                    <small>
                      {e.suite_id} · <ProjectName id={e.project_id} />
                    </small>
                    <small>{e.id}</small>
                  </td>
                  <td>
                    <Badge value={e.passed ? 'passed' : 'failed'} />
                  </td>
                  <td>
                    <Badge value={e.verified ? 'VERIFIED' : 'UNVERIFIED'} />
                  </td>
                  <td>
                    v{e.version_number}
                    <small>{e.version_status}</small>
                  </td>
                  <td>
                    <strong>{Math.round(e.score * 100)}%</strong>
                    <small>
                      {e.passed_scenarios}/{e.total_scenarios}
                    </small>
                  </td>
                  <td>
                    {e.regression ? (
                      <Badge
                        value={c(e.regression.promotion_blocked ? 'blocked' : 'eligible')}
                        tone={e.regression.promotion_blocked ? 'warn' : 'good'}
                      />
                    ) : (
                      c('unavailable')
                    )}
                    {e.regression && <small>{e.regression.reason}</small>}
                  </td>
                  <td>
                    <DateValue value={e.evaluated_at} />
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
function Suites({ project }: { project: string }) {
  const query = useSuites(project)
  return (
    <>
      <SuiteAuthoringPanel project={project} />
      <QueryState query={query} empty={!query.data?.items.length} />
      <div className="intel-stack">
        {!query.error &&
          query.data?.items.map((s) => (
            <Panel title={s.name} key={s.suite_id}>
              <p className="intel-caption">{s.description}</p>
              <code>
                {s.suite_id} · {s.evaluation_version}
              </code>
              {s.scenarios.map((sc) => (
                <details className="intel-row" key={sc.scenario_id}>
                  <summary>
                    <strong>{sc.name}</strong>
                    <span>
                      {sc.category} · {sc.scenario_version}
                    </span>
                  </summary>
                  <Facts values={sc.graders.map((g) => [g.grader_id, g.type])} />
                </details>
              ))}
            </Panel>
          ))}
      </div>
    </>
  )
}
function Replays({ filters }: { filters: ReturnType<typeof useFilters> }) {
  const c = useCopy(),
    query = useCatalog('/bench/replays', replaySchema, filters.project),
    items = query.error ? [] : (query.data?.pages.flatMap((p) => p.items) ?? [])
  return (
    <>
      <CatalogFilters filters={filters} />
      <QueryState query={query} empty={!items.length} />
      <div className="intel-table-wrap">
        <table className="intel-table">
          <thead>
            <tr>
              {['replayId', 'capsuleId', 'result', 'runtime', 'project', 'date'].map((k) => (
                <th key={k}>{c(k)}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {items
              .filter(
                (r) =>
                  !filters.term ||
                  r.id.includes(filters.term) ||
                  r.capsule_id.includes(filters.term),
              )
              .map((r) => (
                <tr key={r.id}>
                  <td>
                    <ResourceLink project={r.project_id} kind="replay" id={r.id} />
                  </td>
                  <td>
                    <ResourceLink project={r.project_id} kind="capsule" id={r.capsule_id} />
                  </td>
                  <td>
                    <Badge value={r.passed ? 'passed' : 'failed'} />
                  </td>
                  <td>
                    <code>{r.backend}</code>
                  </td>
                  <td>
                    <ProjectName id={r.project_id} />
                  </td>
                  <td>
                    <DateValue value={r.created_at} />
                  </td>
                </tr>
              ))}
          </tbody>
        </table>
      </div>
      <More query={query} />
    </>
  )
}
export function EvaluationDetailPage() {
  const { projectId = '', evaluationId = '' } = useParams({ strict: false })
  return (
    <ScopeGuard project={projectId}>
      <EvaluationDetail key={evaluationId} project={projectId} id={evaluationId} />
    </ScopeGuard>
  )
}
function EvaluationDetail({ project, id }: { project: string; id: string }) {
  const c = useCopy(),
    query = useRecord(project, '/bench/evaluations', id, evaluationDetailSchema),
    data = query.error ? undefined : query.data,
    [tab, setTab] = useState('scenarios'),
    [accept, setAccept] = useState(false),
    [reason, setReason] = useState(''),
    [transition, setTransition] = useState(false),
    [candidate, setCandidate] = useState(false),
    permission = useIntelligenceContext(project),
    cache = useQueryClient()
  return (
    <IntelligenceLayout module="bench" back refresh={() => void query.refetch()}>
      <QueryState query={query} />
      {data && (
        <>
          <h2 className="intel-title">
            {data.blueprint_name} · v{data.version_number}
          </h2>
          <div className="intel-meta">
            <ProjectName id={project} />
            <code>{data.id}</code>
            <DateValue value={data.evaluated_at} />
          </div>
          <div className="intel-summary">
            <div>
              <small>{c('score')}</small>
              <strong>{Math.round(data.score * 100)}%</strong> · {data.passed_scenarios}/
              {data.total_scenarios} <Badge value={data.passed ? 'passed' : 'failed'} />
            </div>
            <div>
              <small>{c('integrity')}</small>
              <Badge value={data.verified ? 'VERIFIED' : 'UNVERIFIED'} />
            </div>
            <div>
              <small>{c('promotion')}</small>
              <Badge
                value={c(data.promotion_eligible ? 'eligible' : 'blocked')}
                tone={data.promotion_eligible ? 'good' : 'warn'}
              />
            </div>
          </div>
          {!data.verified && <Notice warning>{c('passedHelp')}</Notice>}
          <div className="intel-actions">
            {data.verified && data.regression && (
              <a
                className="intel-back"
                href={base(project) + `/bench/evaluations/${id}/regression/download`}
              >
                {c('exportRegression')}
              </a>
            )}
            <Button
              variant="secondary"
              disabled={
                !data.verified || data.passed || !permission.data?.permissions['version:create']
              }
              onClick={() => setCandidate(true)}
            >
              {c('createCandidate')}
            </Button>
          </div>
          {!!data.regression?.critical_regressions.length && (
            <Notice warning>
              {c('blocked')} · {data.regression.reason} ·{' '}
              {data.regression.critical_regressions.length} critical
            </Notice>
          )}
          <Tabs
            items={['scenarios', 'regression'].map((k) => [k, c(k)])}
            value={tab}
            onChange={setTab}
          />
          <div className="intel-split">
            <div className="intel-stack">
              {tab === 'scenarios' ? (
                <Panel title={c('scenarios')}>
                  {data.scenarios.map((s) => (
                    <details className="intel-row" key={s.scenario_id}>
                      <summary>
                        <strong>{s.name}</strong>
                        <Badge value={s.state} />
                        <span>
                          {s.category} · {s.scenario_version}
                        </span>
                      </summary>
                      <p className="intel-caption">{s.failure_reason}</p>
                      <Facts
                        values={[
                          [c('reference'), s.scenario_id],
                          [c('latency'), s.latency_seconds],
                          [c('actualModel'), s.execution?.actual_model ?? null],
                          [c('provider'), s.execution?.provider ?? null],
                          [c('runtime'), s.execution?.runtime_backend ?? null],
                          [c('gateway'), s.execution?.gateway ?? null],
                          [
                            c('usage'),
                            s.execution?.usage ? JSON.stringify(s.execution.usage) : null,
                          ],
                          [c('cost'), s.execution?.cost_usd ?? null],
                          [
                            c('resources'),
                            s.execution?.resources ? JSON.stringify(s.execution.resources) : null,
                          ],
                          [
                            c('trace'),
                            s.execution
                              ? c(s.execution.trace_available ? 'yes' : 'no')
                              : c('unavailable'),
                          ],
                        ]}
                      />
                      <h3>{c('actualOutput')}</h3>
                      <pre>{s.actual_output}</pre>
                      <h3>{c('toolActivity')}</h3>
                      {s.tool_activity_available ? (
                        s.tool_activity.map((event) => (
                          <details className="intel-row" key={event.event_id}>
                            <summary>
                              <Badge value={event.status} /> <DateValue value={event.occurred_at} />
                            </summary>
                            <JsonFacts data={event.receipt} />
                          </details>
                        ))
                      ) : (
                        <Notice>{c('unavailable')}</Notice>
                      )}
                      <h3>{c('graders')}</h3>
                      {s.grader_results.length ? (
                        s.grader_results.map((g) => (
                          <details className="intel-row" key={g.grader_id}>
                            <summary>
                              <strong>{g.grader_id}</strong>
                              <Badge value={g.state} />
                              <span>
                                {g.grader_type} · {g.grader_version}
                              </span>
                            </summary>
                            <p>{g.reason}</p>
                            <JsonFacts data={g.details} />
                          </details>
                        ))
                      ) : (
                        <Notice warning>{c('unavailable')}</Notice>
                      )}
                    </details>
                  ))}
                </Panel>
              ) : (
                <BaselineComparison data={data} />
              )}
            </div>
            <aside className="intel-stack">
              <Panel title={c('provenance')}>
                <Facts
                  values={[
                    [c('version'), data.version_id],
                    [c('suite'), data.suite_id],
                    [c('version') + ' · ' + c('suite'), data.evaluation_version],
                    [c('model'), data.requested_model],
                    [c('runtime'), String(data.provenance.runtime_adapter ?? c('unavailable'))],
                    [
                      c('digest'),
                      <code>{String(data.provenance.payload_hash ?? c('unavailable'))}</code>,
                    ],
                  ]}
                />
                <Link
                  to="/agents/$projectId/$blueprintId"
                  params={{ projectId: project, blueprintId: data.blueprint_id }}
                  search={{ version: data.version_id }}
                >
                  {c('versionLifecycle')}
                </Link>
                <Notice>{c('noTrace')}</Notice>
              </Panel>
              <Panel title={c('baselines')}>
                <Notice>{c('baselineHelp')}</Notice>
                <Button
                  variant="secondary"
                  disabled={
                    !permission.data?.permissions['bench:accept_baseline'] ||
                    !data.verified ||
                    !data.passed ||
                    !data.current_evaluation
                  }
                  onClick={() => {
                    setReason('')
                    setTransition(false)
                    setAccept(true)
                  }}
                >
                  {c('acceptBaseline')}
                </Button>
              </Panel>
            </aside>
          </div>
        </>
      )}
      {accept && data && (
        <MutationDialog
          title={c('acceptBaseline')}
          description={c('baselineHelp')}
          project={project}
          path={'/blueprints/' + data.blueprint_id + '/baseline'}
          body={{
            evaluation_id: data.id,
            expected_baseline_id: data.baseline?.baseline_id ?? null,
            reason: reason.trim(),
            suite_transition: transition,
          }}
          allowed={
            !!reason.trim() &&
            !!permission.data?.permissions['bench:accept_baseline'] &&
            data.verified &&
            data.passed &&
            data.current_evaluation
          }
          onClose={() => setAccept(false)}
          onSuccess={async () => {
            await query.refetch()
            await cache.invalidateQueries({ queryKey: ['intelligence-catalog'] })
          }}
        >
          <Facts
            values={[
              [c('reference'), data.id],
              [c('version'), data.version_id],
              [c('baselineId'), data.baseline?.baseline_id ?? '∅'],
            ]}
          />
          <Field label={c('reason')}>
            <textarea value={reason} maxLength={1000} onChange={(e) => setReason(e.target.value)} />
          </Field>
          <Field label={c('suiteTransition')}>
            <input
              type="checkbox"
              checked={transition}
              onChange={(e) => setTransition(e.target.checked)}
            />
          </Field>
        </MutationDialog>
      )}
      {candidate && data && (
        <ScenarioCandidateDialog
          project={project}
          sourceKind="evaluation"
          sourceId={id}
          onClose={() => setCandidate(false)}
        />
      )}
    </IntelligenceLayout>
  )
}
function BaselineComparison({ data }: { data: Evaluation }) {
  const c = useCopy(),
    r = data.regression
  return (
    <Panel title={c('regression')}>
      {data.baseline && (
        <Facts
          values={[
            [c('baselineId'), data.baseline.baseline_id],
            [
              c('evaluations'),
              <ResourceLink
                project={data.project_id}
                kind="evaluation"
                id={data.baseline.evaluation.evaluation_id}
              />,
            ],
            [c('version'), data.baseline.evaluation.version_id],
            [c('suite'), data.baseline.suite_id],
            [c('owner'), data.baseline.accepted_by],
            [c('date'), <DateValue value={data.baseline.accepted_at} />],
          ]}
        />
      )}
      {r ? (
        <>
          <Badge value={r.state} />
          <Notice warning={r.promotion_blocked}>
            {c(r.promotion_blocked ? 'blocked' : 'eligible')} · {r.reason}
          </Notice>
          <Facts
            values={[
              [c('score') + ' · baseline', r.baseline_score],
              [c('score') + ' · candidate', r.candidate_score],
              ['Δ', r.score_delta],
            ]}
          />
          {r.critical_regressions.map((finding, i) => (
            <Notice warning key={i}>
              <JsonFacts data={finding} />
            </Notice>
          ))}
          {r.scenarios.map((entry) => (
            <details className="intel-row" key={entry.scenario_id}>
              <summary>
                <strong>{entry.scenario_id}</strong>
                <Badge value={entry.baseline_state} /> → <Badge value={entry.candidate_state} />
                {entry.critical && <Badge value="critical" tone="warn" />}
              </summary>
              <p>{entry.candidate_reason}</p>
              {entry.graders.map((grader) => (
                <div className="intel-row" key={grader.grader_id}>
                  <strong>{grader.grader_id}</strong>
                  <Facts
                    values={[
                      [c('version'), grader.grader_version],
                      ['Baseline', grader.baseline_state],
                      ['Candidate', grader.candidate_state],
                      [c('reason'), grader.candidate_reason],
                    ]}
                  />
                  {grader.critical && <Badge value="critical" tone="warn" />}
                </div>
              ))}
            </details>
          ))}
          {Object.entries(r.metrics).map(([metric, entry]) => (
            <details className="intel-row" key={metric}>
              <summary>
                <strong>{metric}</strong>
                <Badge value={entry.state} />
              </summary>
              <Facts
                values={[
                  ['Baseline', entry.baseline],
                  ['Candidate', entry.candidate],
                  ['Δ', entry.delta],
                ]}
              />
            </details>
          ))}
          {r.regressions.map((entry, i) => (
            <details className="intel-row" key={i}>
              <summary>
                {String(
                  entry.scenario_id ??
                    entry.grader_id ??
                    entry.metric ??
                    entry.reason ??
                    entry.code ??
                    c('regression'),
                )}
              </summary>
              <JsonFacts data={entry} />
            </details>
          ))}
          <JsonFacts data={r.provenance_differences} />
          {r.limitations.map((p, i) => (
            <Notice key={i}>{p}</Notice>
          ))}
        </>
      ) : (
        <Notice warning>{c('noComparison')}</Notice>
      )}
    </Panel>
  )
}
export function ReplayDetailPage() {
  const { projectId = '', replayId = '' } = useParams({ strict: false })
  return (
    <ScopeGuard project={projectId}>
      <ReplayDetail project={projectId} id={replayId} />
    </ScopeGuard>
  )
}
function ReplayDetail({ project, id }: { project: string; id: string }) {
  const c = useCopy(),
    query = useRecord(project, '/bench/replays', id, replayDetailSchema),
    r = query.error ? undefined : query.data
  return (
    <IntelligenceLayout module="bench" back refresh={() => void query.refetch()}>
      <QueryState query={query} />
      {r && (
        <>
          <h2 className="intel-title">{c('replays')}</h2>
          <Badge value={r.passed ? 'passed' : 'failed'} />
          <Notice warning>{c('replayBoundary')}</Notice>
          <div className="intel-split">
            <Panel title={c('graders')}>
              {r.graders.map((g) => (
                <details className="intel-row" key={g.grader_id}>
                  <summary>
                    <strong>{g.grader_id}</strong>
                    <Badge value={g.state} />
                  </summary>
                  <p>{g.reason}</p>
                  <JsonFacts data={g.details} />
                </details>
              ))}
            </Panel>
            <aside>
              <Panel title={c('provenance')}>
                <Facts
                  values={[
                    [c('replayId'), r.id],
                    [
                      c('capsuleId'),
                      <ResourceLink project={project} kind="capsule" id={r.capsule_id} />,
                    ],
                    [c('runtime'), r.backend],
                    [c('model'), c('no')],
                    [c('provider'), c('no')],
                    ['live_write_calls', r.live_write_calls],
                    ['promotion_evidence', String(r.promotion_evidence)],
                    [c('digest'), <code>{r.digest}</code>],
                  ]}
                />
                <ResourceLink project={project} kind="incident" id={r.capsule.incident_id} />
              </Panel>
            </aside>
          </div>
        </>
      )}
    </IntelligenceLayout>
  )
}
export function CapsuleDetailPage() {
  const { projectId = '', capsuleId = '' } = useParams({ strict: false })
  return (
    <ScopeGuard project={projectId}>
      <CapsuleDetail key={capsuleId} project={projectId} id={capsuleId} />
    </ScopeGuard>
  )
}
function CapsuleDetail({ project, id }: { project: string; id: string }) {
  const c = useCopy(),
    query = useRecord(project, '/relay/capsules', id, capsuleSchema),
    data = query.error ? undefined : query.data,
    permission = useIntelligenceContext(project),
    [confirm, setConfirm] = useState(false),
    [candidate, setCandidate] = useState(false),
    navigate = useNavigate()
  return (
    <IntelligenceLayout module="bench" back refresh={() => void query.refetch()}>
      <QueryState query={query} />
      {data && (
        <>
          <h2 className="intel-title">{c('capsule')}</h2>
          <Notice warning>{c('replayBoundary')}</Notice>
          {data.outcome && (
            <Notice warning={data.outcome !== 'RECOVERED'}>
              {c('capturedOutcome')}: {data.outcome} · {data.failure_reason}
            </Notice>
          )}
          {data.lineage && (
            <details>
              <summary>{c('archivedLineage')}</summary>
              <JsonFacts data={data.lineage} />
            </details>
          )}
          <Panel title={c('provenance')}>
            <Facts
              values={[
                [c('capsuleId'), data.id],
                [
                  c('incidents'),
                  <ResourceLink project={project} kind="incident" id={data.incident_id} />,
                ],
                [
                  c('bundles'),
                  <ResourceLink project={project} kind="bundle" id={data.bundle_id} />,
                ],
                [c('scenario'), data.scenario_id],
                [c('version'), data.scenario_version],
                [c('digest'), <code>{data.digest}</code>],
              ]}
            />
            <Button
              disabled={!permission.data?.permissions['run:create']}
              onClick={() => setConfirm(true)}
            >
              {c('replay')}
            </Button>
            <Button
              variant="secondary"
              disabled={!permission.data?.permissions['version:create']}
              onClick={() => setCandidate(true)}
            >
              {c('createCandidate')}
            </Button>
          </Panel>
        </>
      )}
      {confirm && (
        <MutationDialog
          title={c('replay')}
          description={c('replayBoundary')}
          project={project}
          path={'/bench/capsules/' + id + '/replay'}
          body={{}}
          allowed={!!permission.data?.permissions['run:create']}
          onClose={() => setConfirm(false)}
          onSuccess={async (result) => {
            const replay = replaySchema.parse(result)
            await navigate({
              to: '/bench/$projectId/replays/$replayId',
              params: { projectId: project, replayId: replay.id },
            })
          }}
        />
      )}
      {candidate && data && (
        <ScenarioCandidateDialog
          project={project}
          sourceKind="capsule"
          sourceId={id}
          onClose={() => setCandidate(false)}
        />
      )}
    </IntelligenceLayout>
  )
}
