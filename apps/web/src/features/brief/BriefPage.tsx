import {
  useCatalog,
  useCopy,
  useFilters,
  useIntelligenceContext,
  useRecord,
  useDialogFocus,
} from '@/components/intelligence/hooks'
import { useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { useNavigate, useParams, useSearch } from '@tanstack/react-router'
import { Plus } from 'lucide-react'
import { useWorkspace } from '@/app/providers/WorkspaceProvider'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogTitle, DialogDescription } from '@/components/ui/dialog'
import { DataState } from '@/components/feedback/DataState'
import {
  Badge,
  CatalogFilters,
  DateValue,
  Facts,
  Field,
  IntelligenceLayout,
  More,
  MutationDialog,
  Notice,
  Panel,
  QueryState,
  ResourceLink,
  ScopeGuard,
} from '@/components/intelligence/IntelligenceUI'
import {
  base,
  scoped,
  write,
  bundleSchema,
  evidenceStates,
  sourceSchema,
  sourceDetailSchema,
  linkSchema,
  fixtureSchema,
  type Bundle,
} from '@/features/intelligence/api'

export function BriefPage() {
  const c = useCopy(),
    search = useSearch({ strict: false }),
    [tab, setTab] = useState(
      'tab' in search && ['sources', 'linked'].includes(String(search.tab))
        ? String(search.tab)
        : 'bundles',
    )
  const filters = useFilters('project' in search ? String(search.project ?? '') : ''),
    [builder, setBuilder] = useState(false),
    [ingest, setIngest] = useState(false),
    w = useWorkspace()
  return (
    <IntelligenceLayout
      module="brief"
      tab={tab}
      tabs={['bundles', 'sources', 'linked']}
      onTab={(value) => {
        setTab(value)
        filters.setStatus('')
      }}
      actions={
        <>
          <Button variant="secondary" disabled={!w.project} onClick={() => setIngest(true)}>
            {c('addSource')}
          </Button>
          <Button disabled={!w.project} onClick={() => setBuilder(true)}>
            <Plus size={15} />
            {c('createBundle')}
          </Button>
        </>
      }
    >
      {tab === 'bundles' ? (
        <BundleCatalog filters={filters} />
      ) : tab === 'sources' ? (
        <SourceCatalog filters={filters} />
      ) : (
        <LinkedLookup
          initialKind={'kind' in search ? String(search.kind ?? 'run') : 'run'}
          initialId={'ref' in search ? String(search.ref ?? '') : ''}
          project={filters.project || w.project?.id || ''}
        />
      )}
      {builder && (
        <BundleBuilder
          initialProject={filters.project || w.project?.id || ''}
          onClose={() => setBuilder(false)}
        />
      )}
      {ingest && (
        <SourceBuilder
          initialProject={filters.project || w.project?.id || ''}
          onClose={() => setIngest(false)}
        />
      )}
    </IntelligenceLayout>
  )
}
function BundleCatalog({ filters }: { filters: ReturnType<typeof useFilters> }) {
  const c = useCopy(),
    query = useCatalog('/brief', bundleSchema, filters.project, {
      q: filters.term,
      status: filters.status,
    }),
    items = query.error ? [] : (query.data?.pages.flatMap((p) => p.items) ?? [])
  return (
    <>
      <CatalogFilters filters={filters} states={evidenceStates} />
      <QueryState query={query} empty={!items.length} />
      {items.length > 0 && (
        <div className="intel-table-wrap">
          <table className="intel-table">
            <thead>
              <tr>
                {['bundles', 'current', 'original', 'coverage', 'project', 'created'].map((k) => (
                  <th key={k}>{c(k)}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {items.map((b) => (
                <tr key={b.id}>
                  <td>
                    <ResourceLink project={b.project_id} kind="bundle" id={b.id}>
                      {b.title}
                    </ResourceLink>
                    <small>{b.hypothesis.question}</small>
                  </td>
                  <td>
                    <Badge value={b.evaluation.status} />
                  </td>
                  <td>
                    <Badge value={b.status} />
                  </td>
                  <td>
                    {b.evaluation.coverage}/{b.evaluation.required_coverage}
                  </td>
                  <td>
                    <ProjectName id={b.project_id} />
                  </td>
                  <td>
                    <DateValue value={b.created_at} />
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
export function ProjectName({ id }: { id: string }) {
  const w = useWorkspace()
  return <>{w.context?.projects.find((p) => p.id === id)?.name ?? id}</>
}
function SourceCatalog({ filters }: { filters: ReturnType<typeof useFilters> }) {
  const c = useCopy(),
    query = useCatalog('/brief/sources', sourceSchema, filters.project),
    items = query.error ? [] : (query.data?.pages.flatMap((p) => p.items) ?? [])
  const visible = items.filter(
    (s) =>
      (!filters.term ||
        [s.title, s.id, s.source_ref.id]
          .join(' ')
          .toLowerCase()
          .includes(filters.term.toLowerCase())) &&
      (!filters.status || s.freshness === filters.status),
  )
  return (
    <>
      <Notice>{c('sourceHelp')}</Notice>
      <CatalogFilters filters={filters} states={['fresh', 'stale', 'unavailable']} />
      <p className="intel-caption">
        {c('sources')}: {visible.length} / {items.length} · {c('loadedSourceFilters')}
      </p>
      <QueryState query={query} empty={!visible.length} />
      {visible.length > 0 && (
        <div className="intel-table-wrap">
          <table className="intel-table">
            <thead>
              <tr>
                {['source', 'origin', 'integrity', 'freshness', 'observed'].map((k) => (
                  <th key={k}>{c(k)}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {visible.map((s) => (
                <tr key={s.id}>
                  <td>
                    <ResourceLink kind="source" id={s.id} project={s.project_id}>
                      {s.title}
                    </ResourceLink>
                    <small>
                      <ProjectName id={s.project_id} />
                    </small>
                  </td>
                  <td>
                    {s.source_ref.kind}
                    <small>{s.source_ref.id}</small>
                  </td>
                  <td>
                    <Badge value={s.integrity} />
                  </td>
                  <td>
                    <Badge value={s.freshness} />
                  </td>
                  <td>
                    <DateValue value={s.observed_at} />
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
function LinkedLookup({
  initialKind,
  initialId,
  project,
}: {
  initialKind: string
  initialId: string
  project: string
}) {
  const c = useCopy(),
    [kind, setKind] = useState(initialKind),
    [id, setId] = useState(initialId),
    [lookup, setLookup] = useState(initialId ? { kind: initialKind, id: initialId } : null),
    [owner, setOwner] = useState(project),
    w = useWorkspace()
  const query = useCatalog(
    '/brief-links',
    bundleSchema,
    owner,
    { kind: lookup?.kind ?? 'run', id: lookup?.id ?? '' },
    !!lookup,
  )
  const results = query.error ? [] : (query.data?.pages.flatMap((p) => p.items) ?? [])
  return (
    <>
      <Notice>{c('linkedHelp')}</Notice>
      <form
        className="intel-linked-form intel-filters"
        onSubmit={(e) => {
          e.preventDefault()
          setLookup({ kind, id })
        }}
      >
        <Field label={c('project')}>
          <select
            value={owner}
            onChange={(e) => {
              setOwner(e.target.value)
              setLookup(null)
            }}
          >
            {w.context?.projects.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
        </Field>
        <Field label={c('recordKind')}>
          <select value={kind} onChange={(e) => setKind(e.target.value)}>
            {['run', 'artifact', 'workflow_run', 'incident', 'capsule', 'replay'].map((k) => (
              <option key={k}>{k}</option>
            ))}
          </select>
        </Field>
        <Field label={c('reference')}>
          <input
            required
            pattern="[A-Za-z0-9_-]{1,64}"
            maxLength={64}
            value={id}
            onChange={(e) => setId(e.target.value)}
          />
        </Field>
        <Button type="submit">{c('lookup')}</Button>
      </form>
      {lookup && (
        <>
          <QueryState query={query} empty={!results.length} />
          {!query.error &&
            results.map((b) => (
              <div className="intel-row" key={b.id}>
                <ResourceLink project={owner} kind="bundle" id={b.id}>
                  {b.title}
                </ResourceLink>{' '}
                <Badge value={b.evaluation.status} />
              </div>
            ))}
          <More query={query} />
        </>
      )}
    </>
  )
}
export function BundleDetailPage() {
  const { projectId = '', bundleId = '' } = useParams({ strict: false })
  return (
    <ScopeGuard project={projectId}>
      <BundleDetail key={bundleId} project={projectId} id={bundleId} />
    </ScopeGuard>
  )
}
function BundleDetail({ project, id }: { project: string; id: string }) {
  const query = useRecord(project, '/brief', id, bundleSchema),
    data = query.error ? undefined : query.data
  return (
    <IntelligenceLayout module="brief" back refresh={() => void query.refetch()}>
      <QueryState query={query} />
      {data && (
        <>
          <h2 className="intel-title">{data.title}</h2>
          <div className="intel-meta">
            <ProjectName id={project} />
            <code>{data.id}</code>
            <DateValue value={data.created_at} />
          </div>
          <BundleWorkspace bundle={data} />
        </>
      )}
    </IntelligenceLayout>
  )
}
export function BundleWorkspace({ bundle: b }: { bundle: Bundle }) {
  const c = useCopy(),
    links = useCatalog('/brief/' + b.id + '/links', linkSchema, b.project_id)
  return (
    <>
      <div className="intel-summary">
        <div>
          <small>{c('current')}</small>
          <Badge value={b.evaluation.status} />
        </div>
        <div>
          <small>{c('original')}</small>
          <Badge value={b.status} />
        </div>
        <div>
          <small>{c('coverage')}</small>
          <strong>
            {b.evaluation.coverage}/{b.evaluation.required_coverage}
          </strong>
        </div>
      </div>
      <Notice>
        {b.hypothesis.question} · <code>{b.hypothesis.predicate}</code>
      </Notice>
      {b.evaluation.abstention && (
        <Notice warning>
          <strong>{c('abstention')}</strong> · {b.evaluation.abstention}
        </Notice>
      )}
      <div className="intel-split">
        <div className="intel-stack">
          <Panel title={c('matrix')}>
            {b.evaluation.items.length === 0 ? (
              <DataState title={c('empty')} />
            ) : (
              b.evaluation.items.map((item) => (
                <article className="intel-row" key={item.source_id}>
                  <ResourceLink kind="source" project={b.project_id} id={item.source_id} />
                  <div className="intel-actions">
                    <Badge value={item.relationship} />
                    <Badge value={item.integrity} />
                    <Badge value={item.freshness} />
                  </div>
                  {item.integrity === 'VERIFIED' && item.excerpt && (
                    <blockquote className="intel-excerpt">{item.excerpt}</blockquote>
                  )}
                  <p className="intel-caption">{item.reason}</p>
                  <div className="intel-meta">
                    {item.observed_at && (
                      <span>
                        {c('observed')}: <DateValue value={item.observed_at} />
                      </span>
                    )}
                    {item.collected_at && (
                      <span>
                        {c('collected')}: <DateValue value={item.collected_at} />
                      </span>
                    )}
                  </div>
                </article>
              ))
            )}
          </Panel>
        </div>
        <aside className="intel-stack">
          <Panel title={c('provenance')}>
            <Facts
              values={[
                [c('predicate'), b.hypothesis.predicate],
                [c('target'), b.hypothesis.target_id],
                [c('literal'), b.hypothesis.text || null],
                [c('digest'), <code>{b.digest}</code>],
                [c('date'), <DateValue value={b.evaluation.evaluated_at} />],
              ]}
            />
            <a className="intel-back" href={base(b.project_id) + '/brief/' + b.id + '/download'}>
              {c('export')}
            </a>
          </Panel>
          <Panel title={c('linked')}>
            <QueryState query={links} empty={!links.data?.pages.some((p) => p.items.length)} />
            {!links.error &&
              links.data?.pages
                .flatMap((p) => p.items)
                .map((l) => (
                  <div className="intel-row" key={l.id}>
                    {l.reference_kind} ·{' '}
                    <ResourceLink
                      project={b.project_id}
                      kind={l.reference_kind}
                      id={l.reference_id}
                    />
                  </div>
                ))}
            <More query={links} />
          </Panel>
        </aside>
      </div>
    </>
  )
}
export function SourceDetailPage() {
  const { projectId = '', sourceId = '' } = useParams({ strict: false })
  return (
    <ScopeGuard project={projectId}>
      <SourceDetail project={projectId} id={sourceId} />
    </ScopeGuard>
  )
}
function SourceDetail({ project, id }: { project: string; id: string }) {
  const c = useCopy(),
    query = useRecord(project, '/brief/sources', id, sourceDetailSchema),
    s = query.error ? undefined : query.data
  return (
    <IntelligenceLayout module="brief" back refresh={() => void query.refetch()}>
      <QueryState query={query} />
      {s && (
        <>
          <h2 className="intel-title">{s.title}</h2>
          <div className="intel-actions">
            <Badge value={s.integrity} />
            <Badge value={s.freshness} />
          </div>
          <div className="intel-split">
            <Panel title={c('sanitized')}>
              <blockquote className="intel-excerpt">
                {typeof s.content.text === 'string'
                  ? s.content.text
                  : JSON.stringify(s.content, null, 2)}
              </blockquote>
              <Notice>{c('documentHelp')}</Notice>
            </Panel>
            <aside>
              <Panel title={c('provenance')}>
                <Facts
                  values={[
                    [c('project'), <ProjectName id={project} />],
                    [c('sourceKind'), s.source_ref.kind],
                    [c('origin'), s.source_ref.id],
                    [c('observed'), <DateValue value={s.observed_at} />],
                    [c('collected'), <DateValue value={s.collected_at} />],
                    [c('quality'), s.quality],
                    [c('digest'), <code>{s.digest}</code>],
                    [c('sanitized'), c(s.sanitized ? 'yes' : 'no')],
                  ]}
                />
                {['run', 'artifact'].includes(s.source_ref.kind) && (
                  <ResourceLink kind={s.source_ref.kind} project={project} id={s.source_ref.id} />
                )}
              </Panel>
            </aside>
          </div>
        </>
      )}
    </IntelligenceLayout>
  )
}
function SourceBuilder({
  initialProject,
  onClose,
}: {
  initialProject: string
  onClose: () => void
}) {
  const c = useCopy(),
    [project, setProject] = useState(initialProject),
    [kind, setKind] = useState('document'),
    [title, setTitle] = useState(''),
    [text, setText] = useState(''),
    [id, setId] = useState(''),
    w = useWorkspace(),
    permission = useIntelligenceContext(project),
    cache = useQueryClient()
  return (
    <MutationDialog
      title={c('addSource')}
      description={c(kind === 'document' ? 'documentHelp' : 'sourceHelp')}
      project={project}
      path={kind === 'document' ? '/brief/documents' : '/brief/sources'}
      body={
        kind === 'document'
          ? { title: title.trim(), text }
          : { title: title.trim(), source_ref: { kind, id } }
      }
      allowed={
        !!permission.data?.permissions['version:create'] &&
        !!title.trim() &&
        (kind === 'document' ? !!text.trim() : /^[A-Za-z0-9_-]{1,64}$/.test(id))
      }
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
      <Field label={c('sourceKind')}>
        <select value={kind} onChange={(e) => setKind(e.target.value)}>
          {['document', 'run', 'artifact', 'demo_observation'].map((k) => (
            <option key={k}>{k}</option>
          ))}
        </select>
      </Field>
      <Field label={c('title')}>
        <input value={title} maxLength={160} onChange={(e) => setTitle(e.target.value)} />
      </Field>
      {kind === 'document' ? (
        <Field label={c('documentText')}>
          <textarea value={text} maxLength={16000} onChange={(e) => setText(e.target.value)} />
        </Field>
      ) : (
        <Field label={c('reference')}>
          <input value={id} maxLength={64} onChange={(e) => setId(e.target.value)} />
        </Field>
      )}
    </MutationDialog>
  )
}
function BundleBuilder({
  initialProject,
  onClose,
}: {
  initialProject: string
  onClose: () => void
}) {
  const c = useCopy(),
    w = useWorkspace(),
    navigate = useNavigate(),
    [project, setProject] = useState(initialProject),
    permission = useIntelligenceContext(project),
    [step, setStep] = useState(0),
    [title, setTitle] = useState(''),
    [question, setQuestion] = useState(''),
    [predicate, setPredicate] = useState('contains_text'),
    [literal, setLiteral] = useState(''),
    [target, setTarget] = useState(''),
    [minimum, setMinimum] = useState(1),
    [ids, setIds] = useState<string[]>([]),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(false),
    focus = useDialogFocus()
  const sources = useCatalog('/brief/sources', sourceSchema, project),
    fixtures = useCatalog('/relay/demo-fixtures', fixtureSchema, project),
    items = sources.error ? [] : (sources.data?.pages.flatMap((p) => p.items) ?? [])
  const valid =
    step === 0
      ? !!title.trim() && ids.length > 0
      : step === 1
        ? !!question.trim() &&
          minimum >= 1 &&
          minimum <= 8 &&
          (predicate === 'contains_text'
            ? !!literal.trim()
            : predicate === 'service_healthy'
              ? !!target
              : true)
        : true
  async function save() {
    if (!w.csrf || busy || !permission.data?.permissions['version:create']) return
    setBusy(true)
    setError(false)
    try {
      const result = scoped(
        await write(
          base(project) + '/brief',
          {
            title: title.trim(),
            source_ids: ids,
            hypothesis: {
              question: question.trim(),
              predicate,
              text: predicate === 'contains_text' ? literal : '',
              target_id: predicate === 'service_healthy' ? target : null,
              minimum_sources: minimum,
            },
          },
          bundleSchema,
          w.csrf,
        ),
        w.context!.organization.id,
        project,
      )
      await navigate({
        to: '/brief/$projectId/$bundleId',
        params: { projectId: project, bundleId: result.id },
      })
      onClose()
    } catch {
      setError(true)
    } finally {
      setBusy(false)
    }
  }
  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open && !busy) onClose()
      }}
    >
      <DialogContent className="intel-dialog" closeDisabled={busy} {...focus}>
        <DialogTitle>{c('createBundle')}</DialogTitle>
        <DialogDescription>{c('reviewHelp')}</DialogDescription>
        <ol className="intel-steps">
          {['selectSources', 'hypothesis', 'review'].map((s, i) => (
            <li key={s} aria-current={step === i ? 'step' : undefined}>
              {i + 1}. {c(s)}
            </li>
          ))}
        </ol>
        {step === 0 ? (
          <>
            <Field label={c('project')}>
              <select
                value={project}
                onChange={(e) => {
                  setProject(e.target.value)
                  setIds([])
                  setTarget('')
                }}
              >
                {w.context?.projects.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </select>
            </Field>
            <Field label={c('title')}>
              <input value={title} maxLength={160} onChange={(e) => setTitle(e.target.value)} />
            </Field>
            <QueryState query={sources} empty={!items.length} />
            <div className="intel-scroll">
              {items.map((s) => (
                <label className="intel-source-choice" key={s.id}>
                  <input
                    type="checkbox"
                    checked={ids.includes(s.id)}
                    disabled={!ids.includes(s.id) && ids.length >= 16}
                    onChange={(e) =>
                      setIds(e.target.checked ? [...ids, s.id] : ids.filter((id) => id !== s.id))
                    }
                  />
                  <span>
                    {s.title}
                    <small>
                      {s.source_ref.kind} · {s.source_ref.id}
                    </small>
                    <Badge value={s.integrity} />
                    <Badge value={s.freshness} />
                  </span>
                </label>
              ))}
            </div>
            <More query={sources} />
          </>
        ) : step === 1 ? (
          <>
            <Field label={c('question')}>
              <textarea
                value={question}
                maxLength={500}
                onChange={(e) => setQuestion(e.target.value)}
              />
            </Field>
            <Field label={c('predicate')}>
              <select value={predicate} onChange={(e) => setPredicate(e.target.value)}>
                {['contains_text', 'service_healthy', 'run_completed'].map((p) => (
                  <option key={p}>{p}</option>
                ))}
              </select>
            </Field>
            {predicate === 'contains_text' && (
              <Field label={c('literal')}>
                <input
                  value={literal}
                  maxLength={200}
                  onChange={(e) => setLiteral(e.target.value)}
                />
              </Field>
            )}
            {predicate === 'service_healthy' && (
              <>
                <Field label={c('target')}>
                  <select value={target} onChange={(e) => setTarget(e.target.value)}>
                    <option value="">—</option>
                    {!fixtures.error &&
                      fixtures.data?.pages
                        .flatMap((p) => p.items)
                        .map((f) => (
                          <option key={f.id} value={f.id}>
                            {f.name}
                          </option>
                        ))}
                  </select>
                </Field>
                <QueryState query={fixtures} />
                <More query={fixtures} />
              </>
            )}
            <Field label={c('minimum')}>
              <input
                type="number"
                min={1}
                max={8}
                value={minimum}
                onChange={(e) => setMinimum(Number(e.target.value))}
              />
            </Field>
          </>
        ) : (
          <Facts
            values={[
              [c('project'), <ProjectName id={project} />],
              [c('title'), title],
              [c('question'), question],
              [c('predicate'), predicate],
              [c('sources'), ids.length],
              [c('minimum'), minimum],
              [c('target'), target || null],
              [c('literal'), literal || null],
            ]}
          />
        )}
        <Notice>{c('reviewHelp')}</Notice>
        {error && <p role="alert">{c('mutationError')}</p>}
        <div className="intel-actions">
          <Button variant="secondary" disabled={busy} onClick={onClose}>
            {c('cancel')}
          </Button>
          <Button
            variant="secondary"
            disabled={step === 0 || busy}
            onClick={() => setStep(step - 1)}
          >
            {c('previous')}
          </Button>
          <Button
            disabled={!valid || busy || !permission.data?.permissions['version:create']}
            onClick={() => (step < 2 ? setStep(step + 1) : void save())}
          >
            {busy ? '…' : c(step === 2 ? 'save' : 'next')}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}
