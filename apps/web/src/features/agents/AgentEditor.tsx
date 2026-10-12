import { useCallback, useEffect, useRef, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useBlocker, useNavigate, useParams, useSearch } from '@tanstack/react-router'
import { useTranslation } from 'react-i18next'
import {
  ArrowLeft,
  Plus,
  Play,
  Save,
  Download,
  PanelRightClose,
  PanelRightOpen,
  Workflow,
  History,
  Folder,
} from 'lucide-react'
import { useWorkspace } from '@/app/providers/WorkspaceProvider'
import { StudioWorkspace, StudioNavigation } from '@/app/studio/StudioWorkspace'
import { StudioLibrary } from '@/app/studio/StudioLibrary'
import { StudioInspector } from '@/app/studio/StudioInspector'
import { useStudioDrawer } from '@/app/studio/useStudioDrawer'
import { Tooltip } from '@/components/ui/tooltip'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogTitle } from '@/components/ui/dialog'
import { DataState, QueryError } from '@/components/feedback/DataState'
import { ApiError, request } from '@/lib/api/client'
import {
  basePath,
  capabilitiesSchema,
  draftSchema,
  layoutSchema,
  lifecycleSchema,
  post,
  scoped,
  versionSchema,
  workingSchema,
  type CanvasNode,
  type Draft,
  type Graph,
  type NodeType,
  type Preview,
  type Version,
} from './api'
import { graphErrors, initialGraph } from './registry'
import { AgentCanvas } from './AgentCanvas'
import { NodeLibrary } from './NodeLibrary'
import { AgentInspector } from './AgentInspector'
import { PreviewPanel } from './PreviewPanel'
import { LifecyclePanel } from './LifecyclePanel'
import './agents.css'

export function AgentEditor() {
  const { projectId = '', blueprintId = '' } = useParams({ strict: false })
  const search = useSearch({ strict: false }),
    requestedVersion = 'version' in search ? search.version : undefined
  const workspace = useWorkspace(),
    { t } = useTranslation(),
    navigate = useNavigate()
  const [revision, setRevision] = useState(0)
  const aligned = useRef('')
  const query = useQuery({
    queryKey: [
      'agent-editor',
      workspace.context?.user.id,
      workspace.context?.organization.id,
      projectId,
      blueprintId,
      requestedVersion,
      revision,
    ],
    enabled:
      !!workspace.context && workspace.context.projects.some((project) => project.id === projectId),
    retry: false,
    refetchOnWindowFocus: false,
    queryFn: async ({ signal }) => {
      const base = basePath(projectId, blueprintId),
        organization = workspace.context!.organization.id
      const [working, layout, lifecycle, capabilities] = await Promise.all([
        request(base + '/working-copy', workingSchema, { signal }),
        request(base + '/editor-layout', layoutSchema, { signal }),
        request(
          basePath(projectId) +
            '/lifecycle?' +
            new URLSearchParams({
              blueprint_id: blueprintId,
              ...(requestedVersion ? { version_id: requestedVersion } : {}),
            }),
          lifecycleSchema,
          { signal },
        ),
        request(basePath(projectId) + '/factory/capabilities', capabilitiesSchema, { signal }),
      ])
      scoped(working, organization, projectId)
      scoped(lifecycle, organization, projectId)
      scoped(capabilities, organization, projectId)
      if (
        working.blueprint_id !== blueprintId ||
        !lifecycle.blueprints.some(
          (item) =>
            item.id === blueprintId &&
            item.project_id === projectId &&
            item.organization_id === organization,
        )
      )
        throw new ApiError(502, 'errors.scope')
      return { working, layout, lifecycle, capabilities }
    },
  })
  useEffect(() => {
    // Align the shared selector only after API ownership and membership are verified.
    if (!workspace.context || !query.data) return
    if (aligned.current !== projectId) {
      workspace.selectProject(query.data.working.project_id)
      aligned.current = projectId
    } else if (workspace.project && workspace.project.id !== projectId)
      void navigate({ to: '/agents' })
  }, [navigate, projectId, query.data, workspace])
  return (
    <>
      {!query.data && (
        <header className="studio-header studio-loading-header">
          <Button variant="ghost" size="icon" asChild>
            <Link to="/agents" aria-label={t('studio.back')}>
              <ArrowLeft size={18} />
            </Link>
          </Button>
          <strong>ARYN Studio</strong>
        </header>
      )}
      {workspace.error ? (
        <QueryError error={workspace.error} retry={workspace.retry} />
      ) : query.error ? (
        <QueryError error={query.error} retry={() => void query.refetch()} />
      ) : !workspace.context?.projects.some((project) => project.id === projectId) &&
        !workspace.loading ? (
        <DataState kind="unavailable" />
      ) : query.isPending ? (
        <DataState kind="loading" title={t('agents.loading')} />
      ) : (
        <LoadedEditor
          key={[workspace.context?.user.id, projectId, blueprintId, revision].join(':')}
          initial={query.data}
          projectId={projectId}
          blueprintId={blueprintId}
          requestedVersion={requestedVersion}
          onReload={() => setRevision((value) => value + 1)}
        />
      )}
    </>
  )
}

type Initial = {
  working: import('./api').WorkingCopy
  layout: import('./api').Layout
  lifecycle: import('./api').Lifecycle
  capabilities: import('./api').Capabilities
}
function LoadedEditor({
  initial,
  projectId,
  blueprintId,
  onReload,
  requestedVersion,
}: {
  initial: Initial
  projectId: string
  blueprintId: string
  onReload: () => void
  requestedVersion?: string
}) {
  const workspace = useWorkspace(),
    { t } = useTranslation(),
    queryClient = useQueryClient()
  const drawer = useStudioDrawer()
  const organization = workspace.context!.organization.id,
    user = workspace.context!.user.id,
    blueprint = initial.lifecycle.blueprints.find((item) => item.id === blueprintId)!
  const [draft, setDraft] = useState<Draft | null>(
    initial.working.definition ??
      (initial.capabilities.draft_defaults
        ? {
            ...initial.capabilities.draft_defaults,
            objective: blueprint.objective ?? '',
            role: blueprint.role ?? initial.capabilities.draft_defaults.role,
            owner: blueprint.owner ?? null,
          }
        : null),
  )
  const [graph, setGraph] = useState<Graph>(initial.layout.graph ?? initialGraph())
  const [viewport, setViewport] = useState(initial.layout.viewport)
  const [working, setWorking] = useState(initial.working),
    [layout, setLayout] = useState(initial.layout),
    [lifecycle, setLifecycle] = useState(initial.lifecycle)
  const [source, setSource] = useState(initial.working.source_version_id)
  const [past, setPast] = useState<Graph[]>([]),
    [future, setFuture] = useState<Graph[]>([])
  const [selected, setSelected] = useState<NodeType | null>('agent'),
    [libraryAnchor, setLibraryAnchor] = useState<HTMLElement | null>(null),
    [inspector, setInspector] = useState(!drawer)
  const [tab, setTab] = useState<'blueprint' | 'versions'>(
      requestedVersion ? 'versions' : 'blueprint',
    ),
    [panel, setPanel] = useState<'configure' | 'preview'>('configure')
  const [busy, setBusy] = useState(false),
    [message, setMessage] = useState(''),
    [conflict, setConflict] = useState(false),
    [invalid, setInvalid] = useState(false)
  const [preview, setPreview] = useState<Preview>(),
    [versionId, setVersionId] = useState(
      requestedVersion ?? initial.lifecycle.versions[0]?.id ?? '',
    )
  const lock = useRef(false)
  const lifecycleRequest = useRef(0)
  const canEdit = lifecycle.permissions['version:create'] === true && !!workspace.csrf
  const definitionDirty =
    canEdit &&
    (JSON.stringify(draft) !== JSON.stringify(working.definition) ||
      source !== working.source_version_id)
  const layoutDirty =
    canEdit &&
    (JSON.stringify(graph) !== JSON.stringify(layout.graph) ||
      viewport.x !== layout.viewport.x ||
      viewport.y !== layout.viewport.y ||
      viewport.zoom !== layout.viewport.zoom)
  const dirty = definitionDirty || layoutDirty || invalid
  const blocker = useBlocker({
    shouldBlockFn: () => dirty || busy,
    withResolver: true,
    enableBeforeUnload: dirty || busy,
  })
  const closeLibrary = useCallback(
    (restoreFocus: boolean) => {
      setLibraryAnchor(null)
      if (restoreFocus && libraryAnchor?.isConnected) libraryAnchor.focus({ preventScroll: true })
    },
    [libraryAnchor],
  )
  function showLibrary(trigger: HTMLElement) {
    setTab('blueprint')
    setLibraryAnchor((current) => (current ? null : trigger))
    if (drawer) setInspector(false)
  }
  function closeInspector() {
    setInspector(false)
    if (!drawer) document.getElementById('studio-inspector-toggle')?.focus({ preventScroll: true })
  }
  function graphChange(next: Graph) {
    if (JSON.stringify(next) === JSON.stringify(graph)) return
    setPast((items) => [...items.slice(-49), graph])
    setGraph(next)
    setFuture([])
    setMessage('')
  }
  function undo() {
    if (!past.length) return
    setFuture((items) => [graph, ...items])
    setGraph(past[past.length - 1]!)
    setPast((items) => items.slice(0, -1))
  }
  function redo() {
    if (!future.length) return
    setPast((items) => [...items, graph])
    setGraph(future[0]!)
    setFuture((items) => items.slice(1))
  }
  function add(type: NodeType, position?: { x: number; y: number }) {
    if (!canEdit || busy || !aligned || graph.nodes.some((node) => node.type === type)) return
    const node: CanvasNode = {
      id: type,
      type,
      x: position?.x ?? 110 + graph.nodes.length * 35,
      y: position?.y ?? 40,
    }
    graphChange({ ...graph, nodes: [...graph.nodes, node] })
    setSelected(type)
    setInspector(!drawer)
    setPanel('configure')
    closeLibrary(false)
    requestAnimationFrame(() =>
      document.querySelector<HTMLElement>('.af-board')?.focus({ preventScroll: true }),
    )
  }
  async function save() {
    if (
      lock.current ||
      !canEdit ||
      !workspace.csrf ||
      !draft ||
      invalid ||
      !draftSchema.safeParse(draft).success
    ) {
      setMessage('invalidDefinition')
      throw new Error('Invalid draft')
    }
    lock.current = true
    setBusy(true)
    setMessage('')
    setConflict(false)
    let currentWorking = working,
      currentLayout = layout
    try {
      if (definitionDirty) {
        currentWorking = scoped(
          await post(
            basePath(projectId, blueprintId) + '/working-copy',
            workingSchema,
            workspace.csrf,
            {
              expected_generation: working.generation,
              definition: draft,
              source_version_id: source,
            },
          ),
          organization,
          projectId,
        )
        setWorking(currentWorking)
      }
      if (layoutDirty) {
        currentLayout = await post(
          basePath(projectId, blueprintId) + '/editor-layout',
          layoutSchema,
          workspace.csrf,
          { expected_generation: layout.generation, positions: [], graph, viewport },
        )
        setLayout(currentLayout)
      }
      setMessage('saved')
      return { generation: currentWorking.generation, layoutGeneration: currentLayout.generation }
    } catch (error) {
      setConflict(error instanceof ApiError && error.status === 409)
      setMessage('genericError')
      throw error
    } finally {
      lock.current = false
      setBusy(false)
    }
  }
  async function refreshLifecycle(id = versionId) {
    const requestId = ++lifecycleRequest.current
    const next = scoped(
      await request(
        basePath(projectId) +
          '/lifecycle?' +
          new URLSearchParams({ blueprint_id: blueprintId, ...(id ? { version_id: id } : {}) }),
        lifecycleSchema,
      ),
      organization,
      projectId,
    )
    if (requestId === lifecycleRequest.current) setLifecycle(next)
    void queryClient.invalidateQueries({ queryKey: ['agent-catalog'] })
    void queryClient.invalidateQueries({ queryKey: ['home'] })
    void queryClient.invalidateQueries({ queryKey: ['projects'] })
  }
  async function candidate() {
    try {
      const saved = await save()
      setBusy(true)
      const version = await post(
        basePath(projectId, blueprintId) + '/working-copy/versions',
        versionSchema,
        workspace.csrf!,
        { expected_generation: saved.generation },
      )
      setVersionId(version.id)
      await refreshLifecycle(version.id)
      setTab('versions')
      setMessage('actionSuccess')
    } catch (error) {
      setConflict(error instanceof ApiError && error.status === 409)
      setMessage('genericError')
    } finally {
      setBusy(false)
    }
  }
  function copySource(version: Version) {
    const value = draftSchema.safeParse(
      Object.fromEntries(Object.keys(draftSchema.shape).map((key) => [key, version[key]])),
    )
    if (!value.success || !version.integrity_valid) {
      setMessage('invalidDefinition')
      return
    }
    const parts = value.data.version_number.split('.').map(Number)
    setDraft({
      ...value.data,
      version_number:
        parts.length === 3 && parts.every(Number.isFinite)
          ? `${parts[0]}.${parts[1]}.${parts[2]! + 1}`
          : '1.0.1',
    })
    setSource(version.id)
    setInvalid(false)
    setTab('blueprint')
    setPanel('configure')
    setInspector(true)
    setSelected('agent')
    setMessage('sourceHelp')
  }
  function exportCopy() {
    const url = URL.createObjectURL(
      new Blob(
        [
          JSON.stringify(
            {
              definition: draft,
              graph,
              viewport,
              source_version_id: source,
              expected_generation: working.generation,
              expected_layout_generation: layout.generation,
            },
            null,
            2,
          ),
        ],
        { type: 'application/json' },
      ),
    )
    const link = document.createElement('a')
    link.href = url
    link.download = 'aryn-agent-local-copy.json'
    link.click()
    URL.revokeObjectURL(url)
  }
  const aligned = workspace.project?.id === projectId
  const ready =
    canEdit &&
    !busy &&
    !conflict &&
    !invalid &&
    draftSchema.safeParse(draft).success &&
    !graphErrors(graph).length &&
    lifecycle.permissions['run:create'] === true
  const published = lifecycle.versions.find(
    (version) => version.blueprint_id === blueprintId && version.status === 'published',
  )
  const owner = workspace.context?.projects.find((project) => project.id === blueprint.project_id)
  const drawerOpen = drawer && inspector && tab === 'blueprint'
  return (
    <div className="af-editor">
      <StudioWorkspace
        header={
          <header className="studio-header" inert={drawerOpen}>
            <Tooltip label={t('studio.back')}>
              <Button className="studio-back" variant="ghost" size="icon" asChild>
                <Link to="/agents" aria-label={t('studio.back')}>
                  <ArrowLeft size={18} />
                </Link>
              </Button>
            </Tooltip>
            <div className="studio-identity">
              <div className="studio-title">
                <h1>{blueprint.name}</h1>
                <span className="af-state" data-state="draft">
                  {t('studio.workingCopy')}
                </span>
                {published && (
                  <span className="af-state studio-published" data-state="published">
                    {t('studio.published', { version: published.version_number })}
                  </span>
                )}
              </div>
              <p title={owner?.name}>
                <Folder size={12} />
                <span className="studio-project-name">{owner?.name}</span>
                <span className="studio-domain">· {t('agents.factory')}</span>
              </p>
            </div>
            <span
              className="studio-save-state"
              role="status"
              title={`${t('studio.manualSave')} · ${t(busy ? 'agents.saving' : dirty ? 'agents.unsaved' : 'agents.saved')}`}
              data-dirty={dirty}
            >
              <span className="af-small-dot" />
              {t(busy ? 'agents.saving' : dirty ? 'agents.unsaved' : 'agents.saved')}
            </span>
            <div className="studio-header-actions">
              <Button
                variant="secondary"
                disabled={!canEdit || busy || conflict || !aligned}
                onClick={() => void save().catch(() => {})}
                aria-label={t(busy ? 'agents.saving' : 'agents.save')}
              >
                <Save size={15} />
                <span>{t(busy ? 'agents.saving' : 'agents.save')}</span>
              </Button>
              <Button
                disabled={!canEdit || !lifecycle.permissions['run:create'] || !aligned}
                onClick={() => {
                  setPanel('preview')
                  setInspector(true)
                  setTab('blueprint')
                  closeLibrary(false)
                }}
                aria-label={t('agents.test')}
              >
                <Play size={15} />
                <span>{t('agents.test')}</span>
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
                label: t('studio.canvas'),
                icon: Workflow,
                active: tab === 'blueprint',
                onClick: () => {
                  setTab('blueprint')
                  closeLibrary(false)
                  requestAnimationFrame(() =>
                    document.querySelector<HTMLElement>('.af-board')?.focus(),
                  )
                },
              },
              {
                id: 'studio-add-node',
                label: t('agents.library'),
                icon: Plus,
                active: !!libraryAnchor,
                disabled: !canEdit || busy || !aligned,
                controls: 'studio-node-library',
                expanded: !!libraryAnchor,
                onClick: showLibrary,
              },
              {
                id: 'studio-versions',
                label: t('agents.versions'),
                icon: History,
                active: tab === 'versions',
                onClick: () => {
                  setTab('versions')
                  closeLibrary(false)
                },
              },
              {
                id: 'studio-inspector-toggle',
                label: t(
                  inspector && tab === 'blueprint' ? 'studio.closeInspector' : 'studio.inspector',
                ),
                icon: inspector && tab === 'blueprint' ? PanelRightClose : PanelRightOpen,
                active: inspector && tab === 'blueprint',
                controls: 'studio-inspector',
                expanded: inspector && tab === 'blueprint',
                onClick: () => {
                  setTab('blueprint')
                  setPanel('configure')
                  setInspector(tab !== 'blueprint' || !inspector)
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
                {t('agents.projectChanged')}
              </p>
            )}
            {conflict && (
              <div className="af-conflict" role="alert">
                <p>{t('agents.conflict')}</p>
                <Button variant="secondary" onClick={exportCopy} disabled={drawerOpen}>
                  <Download size={14} />
                  {t('agents.export')}
                </Button>
                <Button variant="secondary" onClick={onReload} disabled={drawerOpen}>
                  {t('agents.reload')}
                </Button>
              </div>
            )}
            {message && !conflict && (
              <div
                className={`af-message ${['genericError', 'invalidDefinition', 'invalidConnection', 'incompletePath', 'occupiedPort', 'duplicateConnection'].includes(message) ? 'af-error' : ''}`}
                role="status"
              >
                {t('agents.' + message)}
              </div>
            )}
            {!canEdit && <p className="af-note">{t('agents.noPermission')}</p>}
          </>
        }
      >
        <div hidden={tab !== 'blueprint'} className="studio-canvas-workspace">
          {libraryAnchor && (
            <StudioLibrary
              anchor={libraryAnchor}
              label={t('agents.library')}
              onClose={closeLibrary}
            >
              <NodeLibrary graph={graph} onAdd={add} onClose={() => closeLibrary(true)} />
            </StudioLibrary>
          )}
          <div className="studio-canvas-column" inert={drawerOpen}>
            <AgentCanvas
              graph={graph}
              viewport={viewport}
              selected={selected}
              draft={draft}
              name={blueprint.name}
              preview={
                !definitionDirty &&
                !invalid &&
                JSON.stringify(graph) === JSON.stringify(layout.graph) &&
                preview?.working_copy_generation === working.generation
                  ? preview
                  : undefined
              }
              readOnly={!canEdit || busy || !aligned}
              canUndo={!!past.length}
              canRedo={!!future.length}
              onGraph={graphChange}
              onViewport={setViewport}
              onSelect={(type) => {
                setSelected(type)
                setPanel('configure')
                setInspector(true)
              }}
              onLibrary={showLibrary}
              onAdd={add}
              onUndo={undo}
              onRedo={redo}
              onMessage={setMessage}
            />
            <footer className="af-canvas-foot">{t('agents.canvasHint')}</footer>
          </div>
          <StudioInspector
            open={inspector}
            drawer={drawer}
            title={t('agents.' + panel)}
            closeLabel={t('studio.closeInspector')}
            onClose={closeInspector}
            tabs={
              <>
                {(['configure', 'preview'] as const).map((item) => (
                  <button key={item} aria-pressed={panel === item} onClick={() => setPanel(item)}>
                    {t('agents.' + item)}
                  </button>
                ))}
              </>
            }
          >
            <div hidden={panel !== 'configure'}>
              <AgentInspector
                key={source ?? 'working'}
                selected={selected}
                draft={draft}
                capabilities={initial.capabilities}
                lifecycle={lifecycle}
                graph={graph}
                readOnly={!canEdit || busy || !aligned}
                onChange={(value) => {
                  setDraft(value)
                  setMessage('')
                }}
                onGraph={graphChange}
                onInvalid={setInvalid}
              />
            </div>
            <div hidden={panel !== 'preview'}>
              <PreviewPanel
                organization={organization}
                project={projectId}
                blueprint={blueprintId}
                user={user}
                generation={working.generation}
                layoutGeneration={layout.generation}
                csrf={workspace.csrf}
                ready={ready && aligned}
                save={save}
                onPreview={setPreview}
              />
            </div>
          </StudioInspector>
        </div>
        <div className="studio-lifecycle" hidden={tab !== 'versions'}>
          <LifecyclePanel
            lifecycle={lifecycle}
            projectId={projectId}
            blueprintId={blueprintId}
            csrf={workspace.csrf}
            busy={busy || !aligned}
            dirty={dirty}
            onCandidate={() => void candidate()}
            onRefresh={refreshLifecycle}
            onSource={copySource}
            onVersion={(id) => {
              setVersionId(id)
              void refreshLifecycle(id).catch(() => setMessage('genericError'))
            }}
            versionId={versionId}
          />
        </div>
      </StudioWorkspace>
      <Dialog
        open={blocker.status === 'blocked'}
        onOpenChange={(open) => {
          if (!open) blocker.reset?.()
        }}
      >
        <DialogContent>
          <DialogTitle>{t('agents.leaveTitle')}</DialogTitle>
          <DialogDescription>{t('agents.leaveDescription')}</DialogDescription>
          <Button variant="secondary" onClick={exportCopy}>
            {t('agents.export')}
          </Button>
          <div className="af-dialog-actions">
            <Button variant="secondary" onClick={() => blocker.reset?.()}>
              {t('agents.keepEditing')}
            </Button>
            <Button disabled={busy} onClick={() => blocker.proceed?.()}>
              {t('agents.leave')}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  )
}
