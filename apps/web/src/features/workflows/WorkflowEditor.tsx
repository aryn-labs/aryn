import { useCallback, useEffect, useRef, useState } from 'react'
import { useQuery, useInfiniteQuery } from '@tanstack/react-query'
import { Link, useBlocker, useNavigate, useParams, useSearch } from '@tanstack/react-router'
import { useTranslation } from 'react-i18next'
import {
  ArrowLeft,
  Download,
  Folder,
  History,
  PanelRightOpen,
  Play,
  Plus,
  Save,
  ShieldCheck,
  Workflow,
} from 'lucide-react'
import { useWorkspace } from '@/app/providers/WorkspaceProvider'
import { StudioWorkspace, StudioNavigation } from '@/app/studio/StudioWorkspace'
import { StudioLibrary } from '@/app/studio/StudioLibrary'
import { StudioInspector } from '@/app/studio/StudioInspector'
import { StudioCanvas, type CanvasViewport } from '@/app/studio/StudioCanvas'
import { useStudioDrawer } from '@/app/studio/useStudioDrawer'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogTitle, DialogDescription } from '@/components/ui/dialog'
import { DataState, QueryError } from '@/components/feedback/DataState'
import { z } from '@/lib/types/validation'
import {
  base,
  request,
  scoped,
  write,
  definitionSchema,
  draftSchema,
  pageSchema,
  versionSummarySchema,
  versionSchema,
  runSchema,
  targetsSchema,
  type Targets,
  WorkflowError,
  kinds,
  type Definition,
  type Draft,
  type Edge,
  type Issue,
  type Node,
  type Run,
} from './api'
import { connectionIssue, edgeState, graphIssues, makeNode, registry } from './registry'
import { WorkflowLibrary } from './WorkflowLibrary'
import { WorkflowInspector } from './WorkflowInspector'
import { WorkflowRunPanel } from './WorkflowRunPanel'
import { draftSnapshot } from './editor-state'
import '@/features/agents/agents.css'
import './workflows.css'

export function WorkflowEditor() {
  const { projectId = '', workflowId = '' } = useParams({ strict: false }),
    workspace = useWorkspace(),
    { t } = useTranslation(),
    navigate = useNavigate()
  const [reload, setReload] = useState(0),
    aligned = useRef('')
  const query = useQuery({
    queryKey: [
      'workflow-editor',
      workspace.context?.user.id,
      workspace.context?.organization.id,
      projectId,
      workflowId,
      reload,
    ],
    enabled: !!workspace.context?.projects.some((p) => p.id === projectId),
    retry: false,
    refetchOnWindowFocus: false,
    queryFn: async ({ signal }) => {
      const organization = workspace.context!.organization.id
      const [definition, lifecycle] = await Promise.all([
        request(
          base(projectId) + '/workflows/' + encodeURIComponent(workflowId),
          definitionSchema,
          { signal },
        ),
        request(base(projectId) + '/workflow-targets?limit=50', targetsSchema, { signal }),
      ])
      scoped(definition, organization, projectId)
      scoped(lifecycle, organization, projectId)
      if (definition.id !== workflowId) throw new Error('Workflow scope differs.')
      return { definition, lifecycle }
    },
  })
  useEffect(() => {
    if (!query.data || !workspace.context) return
    if (aligned.current !== projectId) {
      workspace.selectProject(query.data.definition.project_id)
      aligned.current = projectId
    } else if (workspace.project && workspace.project.id !== projectId)
      void navigate({ to: '/workflows' })
  }, [query.data, workspace, projectId, navigate])
  if (workspace.error) return <QueryError error={workspace.error} retry={workspace.retry} />
  if (query.error) return <QueryError error={query.error} retry={() => void query.refetch()} />
  if (!workspace.loading && !workspace.context?.projects.some((p) => p.id === projectId))
    return <DataState kind="unavailable" />
  if (!query.data)
    return (
      <>
        <header className="studio-header">
          <Link to="/workflows">{t('workflows.title')}</Link>
        </header>
        <DataState kind="loading" />
      </>
    )
  return (
    <LoadedWorkflow
      key={[workspace.context?.user.id, projectId, workflowId, reload].join(':')}
      initial={query.data.definition}
      lifecycle={query.data.lifecycle}
      onReload={() => setReload((v) => v + 1)}
    />
  )
}
function LoadedWorkflow({
  initial,
  lifecycle,
  onReload,
}: {
  initial: Definition
  lifecycle: Targets
  onReload: () => void
}) {
  const workspace = useWorkspace(),
    { t } = useTranslation(),
    drawer = useStudioDrawer(),
    search = useSearch({ strict: false })
  const organization = initial.organization_id,
    project = initial.project_id,
    workflow = initial.id,
    user = workspace.context!.user.id,
    csrf = workspace.csrf
  const storageKey = ['aryn-workflow-run', user, organization, project, workflow].join(':')
  const [runId, setRunId] = useState(() => {
    if ('run' in search && typeof search.run === 'string') return search.run
    try {
      return sessionStorage.getItem(storageKey) ?? ''
    } catch {
      return ''
    }
  })
  const [draft, setDraft] = useState<Draft>({
      name: initial.name,
      graph: initial.graph,
      positions: initial.positions,
    }),
    [saved, setSaved] = useState(initial)
  const [selected, setSelected] = useState<string | null>(
      initial.graph.nodes.find((n) => n.kind === 'agent')?.id ?? null,
    ),
    [viewport, setViewport] = useState<CanvasViewport>({ x: 30, y: 20, zoom: drawer ? 0.4 : 0.65 })
  const [past, setPast] = useState<Draft[]>([]),
    [future, setFuture] = useState<Draft[]>([])
  const [inspector, setInspector] = useState(!drawer),
    [panel, setPanel] = useState<'configure' | 'versions' | 'run'>(runId ? 'run' : 'configure'),
    [libraryAnchor, setLibraryAnchor] = useState<HTMLElement | null>(null)
  const [busy, setBusy] = useState(false),
    [conflict, setConflict] = useState(false),
    [message, setMessage] = useState(''),
    [serverIssues, setServerIssues] = useState<Issue[]>([]),
    lock = useRef(false)
  const [viewVersion, setViewVersion] = useState(''),
    [viewRun, setViewRun] = useState(!!runId),
    [artifactId, setArtifactId] = useState<string | null>(null)
  const aligned = workspace.project?.id === project,
    canEdit = !!csrf && lifecycle.permissions['version:create'] === true
  const dirty =
    draftSnapshot(draft) !==
    draftSnapshot({ name: saved.name, graph: saved.graph, positions: saved.positions })
  const blocker = useBlocker({
    shouldBlockFn: () => dirty || busy,
    enableBeforeUnload: dirty || busy,
    withResolver: true,
  })
  const versions = useInfiniteQuery({
    queryKey: ['workflow-versions', user, organization, project, workflow],
    initialPageParam: '',
    retry: false,
    queryFn: async ({ signal, pageParam }) => {
      const page = await request(
        base(project) +
          '/workflows/' +
          encodeURIComponent(workflow) +
          '/versions?' +
          new URLSearchParams({ limit: '25', after: pageParam }),
        pageSchema(versionSummarySchema),
        { signal },
      )
      page.items.forEach((v) => {
        scoped(v, organization, project)
        if (v.workflow_id !== workflow) throw new Error('Version scope differs.')
      })
      return page
    },
    getNextPageParam: (last) => last.next ?? undefined,
  })
  const versionItems = versions.data?.pages.flatMap((page) => page.items) ?? []
  const targetPages = useInfiniteQuery({
    queryKey: ['workflow-targets', user, organization, project],
    initialPageParam: '',
    initialData: { pages: [lifecycle], pageParams: [''] },
    retry: false,
    queryFn: async ({ signal, pageParam }) =>
      scoped(
        await request(
          base(project) +
            '/workflow-targets?' +
            new URLSearchParams({ limit: '50', after: pageParam }),
          targetsSchema,
          { signal },
        ),
        organization,
        project,
      ),
    getNextPageParam: (last) => last.next ?? undefined,
  })
  const pinnedTargets = useQuery({
    queryKey: [
      'workflow-pinned-targets',
      user,
      organization,
      project,
      initial.graph.nodes.map((n) => n.assignment_id),
    ],
    retry: false,
    queryFn: async ({ signal }) => {
      const ids = [
        ...new Set(
          initial.graph.nodes.map((n) => n.assignment_id).filter((id): id is string => !!id),
        ),
      ]
      return (
        await Promise.all(
          ids.map(async (id) => {
            const page = scoped(
              await request(
                base(project) + '/workflow-targets/' + encodeURIComponent(id),
                targetsSchema,
                { signal },
              ),
              organization,
              project,
            )
            if (page.items.some((item) => item.id !== id))
              throw new Error('Assignment scope differs.')
            return page.items
          }),
        )
      ).flat()
    },
  })
  const targets = [
    ...(targetPages.data?.pages.flatMap((p) => p.items) ?? []),
    ...(pinnedTargets.data ?? []),
  ].filter((item, i, all) => all.findIndex((v) => v.id === item.id) === i)
  const runQuery = useQuery<Run>({
    queryKey: ['workflow-run', user, organization, project, workflow, runId],
    enabled: !!runId,
    retry: false,
    refetchInterval: (query) =>
      query.state.error
        ? false
        : query.state.data?.status === 'running'
          ? 700
          : query.state.data?.status === 'waiting_review'
            ? 3000
            : false,
    queryFn: async ({ signal }) => {
      const run = scoped(
        await request(base(project) + '/workflow-runs/' + encodeURIComponent(runId), runSchema, {
          signal,
        }),
        organization,
        project,
      )
      if (run.id !== runId || run.workflow_id !== workflow) throw new Error('Run scope differs.')
      return run
    },
  })
  const run = !runQuery.error ? runQuery.data : undefined
  const versionId = viewRun && run ? run.version_id : viewVersion
  const snapshot = useQuery({
    queryKey: ['workflow-snapshot', user, organization, project, workflow, versionId],
    enabled: !!versionId,
    retry: false,
    queryFn: async ({ signal }) => {
      const version = scoped(
        await request(
          base(project) + '/workflow-versions/' + encodeURIComponent(versionId),
          versionSchema,
          { signal },
        ),
        organization,
        project,
      )
      if (version.id !== versionId || version.workflow_id !== workflow)
        throw new Error('Version identity differs.')
      return version
    },
  })
  const readonlySnapshot = viewRun || !!viewVersion
  const graph = readonlySnapshot ? (snapshot.data?.graph ?? { nodes: [], edges: [] }) : draft.graph
  const verifiedRun =
    viewRun &&
    run &&
    snapshot.data &&
    snapshot.data.id === run.version_id &&
    (!run.graph_digest || snapshot.data.digest === run.graph_digest)
      ? run
      : undefined
  const editable = canEdit && aligned && !busy && !conflict && !readonlySnapshot
  const issues = [...graphIssues(graph), ...serverIssues]
  const closeLibrary = useCallback(
    (focus: boolean) => {
      setLibraryAnchor(null)
      if (focus && libraryAnchor?.isConnected) libraryAnchor.focus({ preventScroll: true })
    },
    [libraryAnchor],
  )
  function showLibrary(trigger: HTMLButtonElement) {
    if (!editable) return
    setLibraryAnchor((v) => (v ? null : trigger))
    if (drawer) setInspector(false)
  }
  function change(next: Draft) {
    if (!editable) return
    setPast((v) => [...v.slice(-49), draft])
    setFuture([])
    setDraft(next)
    setServerIssues([])
    setMessage('')
  }
  function undo() {
    if (!editable || !past.length) return
    setFuture((v) => [draft, ...v])
    setDraft({ ...past[past.length - 1]!, name: draft.name })
    setPast((v) => v.slice(0, -1))
    setServerIssues([])
  }
  function redo() {
    if (!editable || !future.length) return
    setPast((v) => [...v, draft])
    setDraft({ ...future[0]!, name: draft.name })
    setFuture((v) => v.slice(1))
    setServerIssues([])
  }
  function add(kind: Node['kind'], position?: { x: number; y: number }) {
    if (
      !editable ||
      draft.graph.nodes.length >= 24 ||
      (registry[kind].singleton && draft.graph.nodes.some((n) => n.kind === kind))
    )
      return
    const node = makeNode(
      kind,
      t('workflows.' + kind) + ' ' + (draft.graph.nodes.filter((n) => n.kind === kind).length + 1),
    )
    change({
      ...draft,
      graph: { ...draft.graph, nodes: [...draft.graph.nodes, node] },
      positions: [
        ...draft.positions,
        {
          id: node.id,
          x: position?.x ?? 360 + draft.graph.nodes.length * 35,
          y: position?.y ?? 80,
        },
      ],
    })
    setSelected(node.id)
    closeLibrary(false)
    setPanel('configure')
    if (!drawer) setInspector(true)
    requestAnimationFrame(() => document.querySelector<HTMLElement>('.af-board')?.focus())
  }
  function remove(id: string) {
    change({
      ...draft,
      graph: {
        nodes: draft.graph.nodes.filter((n) => n.id !== id),
        edges: draft.graph.edges.filter((e) => e.source !== id && e.target !== id),
      },
      positions: draft.positions.filter((p) => p.id !== id),
    })
    if (selected === id) setSelected(null)
  }
  function connect(value: Omit<Edge, 'id'>) {
    if (!editable) return
    const code = connectionIssue(draft.graph, value)
    if (code) {
      setServerIssues([{ subject: value.source, code }])
      return
    }
    change({
      ...draft,
      graph: {
        ...draft.graph,
        edges: [
          ...draft.graph.edges,
          { ...value, id: 'edge_' + crypto.randomUUID().replaceAll('-', '').slice(0, 20) },
        ],
      },
    })
  }
  async function save() {
    if (!csrf || !canEdit || !aligned || conflict || !draftSchema.safeParse(draft).success)
      throw new Error('Draft cannot be saved.')
    if (!dirty) return saved
    const result = scoped(
      await write(
        base(project) + '/workflows/' + encodeURIComponent(workflow),
        { ...draft, expected_revision: saved.revision },
        definitionSchema,
        csrf,
      ),
      organization,
      project,
    )
    if (result.id !== workflow) throw new Error('Workflow identity differs.')
    setSaved(result)
    return result
  }
  async function perform(action: 'save' | 'validate' | 'freeze') {
    if (lock.current || !csrf) return
    lock.current = true
    setBusy(true)
    setMessage('')
    setServerIssues([])
    try {
      const result = await save()
      if (action === 'validate') {
        await write(
          base(project) + '/workflows/' + encodeURIComponent(workflow) + '/validate',
          {},
          z.object({ valid: z.literal(true), revision: z.number(), digest: z.string() }),
          csrf,
        )
        setMessage('valid')
      }
      if (action === 'freeze') {
        const version = scoped(
          await write(
            base(project) + '/workflows/' + encodeURIComponent(workflow) + '/versions',
            { expected_revision: result.revision },
            versionSchema,
            csrf,
          ),
          organization,
          project,
        )
        if (version.workflow_id !== workflow) throw new Error('Version scope differs.')
        await versions.refetch()
        setViewVersion(version.id)
      }
    } catch (error) {
      if (error instanceof WorkflowError && error.status === 409) setConflict(true)
      if (error instanceof WorkflowError && error.issues.length) setServerIssues(error.issues)
      else setMessage('genericError')
    } finally {
      setBusy(false)
      lock.current = false
    }
  }
  function select(id: string) {
    setSelected(id)
    setInspector(true)
    setPanel('configure')
    closeLibrary(false)
  }
  function openRun(id: string) {
    setRunId(id)
    setViewRun(true)
    setViewVersion('')
    setArtifactId(null)
    setPanel('run')
    setInspector(true)
    try {
      sessionStorage.setItem(storageKey, id)
    } catch {
      /* Storage is optional. */
    }
  }
  function exportDraft() {
    const url = URL.createObjectURL(
      new Blob(
        [
          JSON.stringify(
            {
              organization_id: organization,
              project_id: project,
              workflow_id: workflow,
              expected_revision: saved.revision,
              ...draft,
            },
            null,
            2,
          ),
        ],
        { type: 'application/json' },
      ),
    )
    const a = document.createElement('a')
    a.href = url
    a.download = 'aryn-workflow-local-draft.json'
    a.click()
    URL.revokeObjectURL(url)
  }
  const accessError = [targetPages.error, pinnedTargets.error, runQuery.error, snapshot.error].find(
    (error) => error && 'status' in error && (error.status === 401 || error.status === 403),
  )
  if (accessError) return <QueryError error={accessError} retry={onReload} />
  const drawerOpen = drawer && inspector
  return (
    <div className="wf-editor">
      <StudioWorkspace
        header={
          <header className="studio-header" inert={drawerOpen}>
            <h1 className="sr-only">
              {t('workflows.builder')} · {draft.name}
            </h1>
            <Button variant="ghost" size="icon" asChild>
              <Link to="/workflows" aria-label={t('workflows.title')}>
                <ArrowLeft size={18} />
              </Link>
            </Button>
            <div className="studio-identity">
              <div className="studio-title">
                <input
                  className="wf-title-input"
                  aria-label={t('workflows.name')}
                  value={draft.name}
                  readOnly={!editable}
                  maxLength={120}
                  onChange={(e) => setDraft({ ...draft, name: e.target.value })}
                />
                <span className="af-state">
                  {t('workflows.revision')} {saved.revision}
                </span>
              </div>
              <p>
                <Folder size={12} />
                <span className="studio-project-name">
                  {workspace.context?.projects.find((p) => p.id === project)?.name}
                </span>
                <span className="studio-domain">· {t('workflows.builder')}</span>
              </p>
            </div>
            <span className="studio-save-state" role="status" data-dirty={dirty}>
              <span className="af-small-dot" />
              {t(busy ? 'workflows.saving' : dirty ? 'workflows.unsaved' : 'workflows.saved')}
            </span>
            <div className="studio-header-actions">
              <Button
                variant="secondary"
                aria-label={t('workflows.save')}
                disabled={
                  !canEdit ||
                  busy ||
                  conflict ||
                  !aligned ||
                  !draftSchema.safeParse(draft).success ||
                  readonlySnapshot
                }
                onClick={() => void perform('save')}
              >
                <Save size={15} />
                <span>{t('workflows.save')}</span>
              </Button>
              <Button
                variant="secondary"
                aria-label={t('workflows.validate')}
                disabled={!editable}
                onClick={() => void perform('validate')}
              >
                <ShieldCheck size={15} />
                <span>{t('workflows.validate')}</span>
              </Button>
              <Button
                aria-label={t('workflows.run')}
                disabled={!lifecycle.permissions['run:create'] || !aligned}
                onClick={() => {
                  setPanel('run')
                  setInspector(true)
                  closeLibrary(false)
                }}
              >
                <Play size={15} />
                <span>{t('workflows.run')}</span>
              </Button>
            </div>
          </header>
        }
        navigation={
          <StudioNavigation
            inert={drawerOpen}
            items={[
              {
                id: 'studio-canvas',
                label: t('workflows.canvas'),
                icon: Workflow,
                active: !readonlySnapshot,
                onClick: () => {
                  setViewRun(false)
                  setViewVersion('')
                  closeLibrary(false)
                  requestAnimationFrame(() =>
                    document.querySelector<HTMLElement>('.af-board')?.focus(),
                  )
                },
              },
              {
                id: 'studio-add-node',
                label: t('workflows.library'),
                icon: Plus,
                disabled: !editable,
                active: !!libraryAnchor,
                controls: 'studio-node-library',
                expanded: !!libraryAnchor,
                onClick: showLibrary,
              },
              {
                id: 'studio-versions',
                label: t('workflows.versions'),
                icon: History,
                active: panel === 'versions' && inspector,
                onClick: () => {
                  setPanel('versions')
                  setInspector(true)
                  closeLibrary(false)
                },
              },
              {
                id: 'studio-execution',
                label: t('workflows.executionPanel'),
                icon: Play,
                active: panel === 'run' && inspector,
                onClick: () => {
                  setPanel('run')
                  setInspector(true)
                  closeLibrary(false)
                  if (runId) setViewRun(true)
                },
              },
              {
                id: 'studio-inspector-toggle',
                label: t('studio.inspector'),
                icon: PanelRightOpen,
                active: inspector,
                controls: 'studio-inspector',
                expanded: inspector,
                onClick: () => {
                  setInspector((v) => !v)
                  setPanel('configure')
                  closeLibrary(false)
                },
              },
            ]}
          />
        }
        notices={
          <>
            {!aligned && (
              <p className="af-note" role="alert">
                {t('workflows.projectChanged')}
              </p>
            )}
            {conflict && (
              <div className="af-conflict" role="alert">
                <p>{t('workflows.conflict')}</p>
                <Button variant="secondary" onClick={exportDraft}>
                  {t('workflows.export')}
                </Button>
                <Button variant="secondary" onClick={onReload}>
                  {t('workflows.reload')}
                </Button>
              </div>
            )}
            {message && (
              <p className={message === 'valid' ? 'af-note' : 'af-error'} role="status">
                {t('workflows.' + message)}
              </p>
            )}
            {readonlySnapshot && (
              <p className="af-note">
                {t('workflows.immutable')}
                <Button
                  variant="ghost"
                  onClick={() => {
                    setViewVersion('')
                    setViewRun(false)
                  }}
                >
                  {t('workflows.editDraft')}
                </Button>
              </p>
            )}
            {!!issues.length && !readonlySnapshot && (
              <details className="wf-issues" open={!!serverIssues.length}>
                <summary>
                  {t('workflows.invalid')} · {issues.length}
                </summary>
                <ul>
                  {issues.map((issue, i) => (
                    <li key={issue.subject + issue.code + i}>
                      {issue.subject} ·{' '}
                      {t('workflows.issue.' + issue.code, { defaultValue: t('workflows.invalid') })}
                    </li>
                  ))}
                </ul>
              </details>
            )}
          </>
        }
      >
        <div className="studio-canvas-workspace">
          {libraryAnchor && (
            <StudioLibrary
              label={t('workflows.library')}
              anchor={libraryAnchor}
              onClose={closeLibrary}
            >
              <WorkflowLibrary graph={draft.graph} onAdd={add} onClose={() => closeLibrary(true)} />
            </StudioLibrary>
          )}
          <div className="studio-canvas-column" inert={drawerOpen}>
            {snapshot.error && readonlySnapshot ? (
              <QueryError error={snapshot.error} retry={() => void snapshot.refetch()} />
            ) : (
              <StudioCanvas
                nodes={graph.nodes.map((node, i) => {
                  const definition = registry[node.kind],
                    position = draft.positions.find((p) => p.id === node.id) ?? {
                      x: 60 + i * 300,
                      y: 220,
                    },
                    state =
                      verifiedRun?.tasks.find((task) => task.node_id === node.id)?.status ?? 'idle'
                  return {
                    ...position,
                    id: node.id,
                    type: 'workflow-' + node.kind,
                    label: node.label,
                    title: node.label,
                    icon: definition.icon,
                    width: 236,
                    height: 142,
                    state,
                    invalid: !readonlySnapshot && issues.some((issue) => issue.subject === node.id),
                    footer: t('workflows.' + state),
                    body: (
                      <>
                        <p>
                          {node.kind === 'agent'
                            ? (node.renderer ?? node.agent_version_id ?? t('workflows.chooseAgent'))
                            : t('workflows.' + node.kind + 'Help')}
                        </p>
                        <span className="af-node-chip">
                          {node.input_schema} → {node.output_schema}
                        </span>
                      </>
                    ),
                    ports: definition.ports(node),
                  }
                })}
                edges={graph.edges.map((edge) => ({
                  ...edge,
                  state: edgeState(edge, verifiedRun),
                }))}
                viewport={viewport}
                selected={selected}
                readOnly={!editable}
                canUndo={!!past.length}
                canRedo={!!future.length}
                labels={{
                  canvas: t('workflows.canvas'),
                  subtitle: t('workflows.canvasHelp'),
                  select: t('agents.select'),
                  connect: t('workflows.connect'),
                  add: t('workflows.add'),
                  undo: t('agents.undo'),
                  redo: t('agents.redo'),
                  zoomIn: t('agents.zoomIn'),
                  zoomOut: t('agents.zoomOut'),
                  fit: t('agents.fit'),
                  minimap: t('agents.minimap'),
                  empty: t('agents.noNodes'),
                  connectionHint: t('agents.connectionHint'),
                  cancel: t('agents.cancel'),
                }}
                onMove={(id, position) =>
                  change({
                    ...draft,
                    positions: [
                      ...draft.positions.filter((p) => p.id !== id),
                      { id, x: position.x, y: position.y },
                    ],
                  })
                }
                onDelete={remove}
                onConnect={(edge) => connect(edge as Omit<Edge, 'id'>)}
                onViewport={setViewport}
                onSelect={select}
                onLibrary={showLibrary}
                onAdd={(kind, position) => {
                  if (kinds.includes(kind as Node['kind'])) add(kind as Node['kind'], position)
                }}
                onUndo={undo}
                onRedo={redo}
              />
            )}
            <footer className="af-canvas-foot">{t('agents.canvasHint')}</footer>
          </div>
          <StudioInspector
            open={inspector}
            drawer={drawer}
            title={t('workflows.' + (panel === 'run' ? 'executionPanel' : panel))}
            closeLabel={t('studio.closeInspector')}
            onClose={() => setInspector(false)}
            tabs={
              <>
                {(['configure', 'versions', 'run'] as const).map((tab) => (
                  <button key={tab} aria-pressed={panel === tab} onClick={() => setPanel(tab)}>
                    {t('workflows.' + tab)}
                  </button>
                ))}
              </>
            }
          >
            <div hidden={panel !== 'configure'}>
              <WorkflowInspector
                key={selected ?? 'none'}
                node={graph.nodes.find((n) => n.id === selected)}
                graph={graph}
                targets={targets}
                hasMoreTargets={!!targetPages.hasNextPage}
                loadingTargets={targetPages.isFetchingNextPage}
                onMoreTargets={() => void targetPages.fetchNextPage()}
                project={project}
                readOnly={!editable}
                issues={issues}
                run={verifiedRun}
                onChange={(node) =>
                  change({
                    ...draft,
                    graph: {
                      ...draft.graph,
                      nodes: draft.graph.nodes.map((n) => (n.id === node.id ? node : n)),
                    },
                  })
                }
                onDelete={() => {
                  if (selected) remove(selected)
                }}
                onConnect={(port, target) => {
                  if (selected)
                    connect({
                      source: selected,
                      source_port: port as Edge['source_port'],
                      target,
                      target_port: 'value',
                    })
                }}
                onRemoveEdge={(id) =>
                  change({
                    ...draft,
                    graph: { ...draft.graph, edges: draft.graph.edges.filter((e) => e.id !== id) },
                  })
                }
                onArtifact={(id) => {
                  setArtifactId(id)
                  setPanel('run')
                }}
              />
              <p className="af-note">{t('workflows.draftHelp')}</p>
              <p className="af-note">{t('workflows.positionsHelp')}</p>
            </div>
            <div className="wf-panel" hidden={panel !== 'versions'}>
              <h2>{t('workflows.versions')}</h2>
              <p className="af-note">{t('workflows.versionHelp')}</p>
              <Button
                disabled={
                  !editable ||
                  !lifecycle.permissions['version:publish'] ||
                  graphIssues(draft.graph).length > 0
                }
                onClick={() => void perform('freeze')}
              >
                {t('workflows.freeze')}
              </Button>
              {versions.error ? (
                <QueryError error={versions.error} retry={() => void versions.refetch()} />
              ) : versions.isPending ? (
                <DataState kind="loading" />
              ) : (
                <div className="wf-version-list">
                  {versionItems.map((version) => (
                    <button
                      key={version.id}
                      aria-pressed={versionId === version.id}
                      onClick={() => {
                        setViewVersion(version.id)
                        setViewRun(false)
                      }}
                    >
                      {t('workflows.revision')} {version.revision}
                      <code>{version.digest}</code>
                    </button>
                  ))}
                </div>
              )}
              {versions.hasNextPage && (
                <Button
                  variant="secondary"
                  disabled={versions.isFetchingNextPage}
                  onClick={() => void versions.fetchNextPage()}
                >
                  {t('workflows.more')}
                </Button>
              )}
              {!versionItems.length && <p className="af-note">{t('workflows.noVersions')}</p>}
            </div>
            <div hidden={panel !== 'run'}>
              <WorkflowRunPanel
                organization={organization}
                project={project}
                workflow={workflow}
                user={user}
                csrf={aligned ? csrf : undefined}
                permissions={lifecycle.permissions}
                versions={versionItems}
                run={run}
                graph={verifiedRun ? snapshot.data?.graph : undefined}
                runError={runQuery.error}
                pendingRun={!!runId && runQuery.isPending}
                onRun={openRun}
                onRefresh={() => void runQuery.refetch()}
                onSelect={select}
                artifactId={artifactId}
                onArtifact={setArtifactId}
              />
            </div>
          </StudioInspector>
        </div>
      </StudioWorkspace>
      <Dialog
        open={blocker.status === 'blocked'}
        onOpenChange={(open) => {
          if (!open && blocker.status === 'blocked') blocker.reset()
        }}
      >
        <DialogContent>
          <DialogTitle>{t('workflows.leave')}</DialogTitle>
          <DialogDescription>{t('workflows.leaveHelp')}</DialogDescription>
          <div className="af-dialog-actions">
            <Button variant="secondary" onClick={exportDraft}>
              <Download size={15} />
              {t('workflows.export')}
            </Button>
            <Button
              variant="secondary"
              onClick={() => {
                if (blocker.status === 'blocked') blocker.reset()
              }}
            >
              {t('workflows.stay')}
            </Button>
            <Button
              onClick={() => {
                if (blocker.status === 'blocked') blocker.proceed()
              }}
            >
              {t('workflows.discard')}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  )
}
