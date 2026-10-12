import { useDeferredValue, useRef, useState } from 'react'
import { useInfiniteQuery, useQuery } from '@tanstack/react-query'
import { Link, useNavigate, useLocation } from '@tanstack/react-router'
import { useTranslation } from 'react-i18next'
import { ArrowUpRight, Plus, Search, Workflow } from 'lucide-react'
import { useWorkspace } from '@/app/providers/WorkspaceProvider'
import { StandardLayout } from '@/app/shell/MainWorkspace'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogTitle, DialogDescription } from '@/components/ui/dialog'
import { DataState, QueryError } from '@/components/feedback/DataState'
import { summarySchema as permissionSchema } from '@/lib/types/workspace'
import { useSummary } from '@/hooks/use-workspace-queries'
import { readBrief } from '@/features/home/lib/home-state'
import { base, request, pageSchema, summarySchema, definitionSchema, scoped, write } from './api'
import { initialDraft } from './registry'
import '@/features/agents/agents.css'
import './workflows.css'

export function WorkflowCatalog() {
  const workspace = useWorkspace(),
    { t } = useTranslation(),
    location = useLocation()
  const [filter, setFilter] = useState<string | null>(null),
    [search, setSearch] = useState(''),
    [creating, setCreating] = useState(false),
    [dismissed, setDismissed] = useState<string>()
  const project = filter ?? workspace.project?.id ?? '',
    q = useDeferredValue(search.trim()),
    summary = useSummary()
  const projects = (workspace.context?.projects ?? []).filter((p) => !project || p.id === project)
  const brief =
    workspace.context && workspace.project && dismissed !== location.state.homeBriefId
      ? readBrief(
          location.state.homeBriefId,
          { organizationId: workspace.context.organization.id, projectId: workspace.project.id },
          workspace.context.user.id,
        )
      : undefined
  const catalog = useInfiniteQuery({
    queryKey: [
      'workflow-catalog',
      workspace.context?.user.id,
      workspace.context?.organization.id,
      project,
      q,
    ],
    enabled: !!workspace.context && !!projects.length,
    initialPageParam: null as Record<string, string> | null,
    retry: false,
    queryFn: async ({ signal, pageParam }) => {
      const pages = await Promise.all(
        projects
          .filter((p) => !pageParam || pageParam[p.id])
          .map(async (p) => {
            const query = new URLSearchParams({ limit: '25', q })
            if (pageParam?.[p.id]) query.set('after', pageParam[p.id]!)
            const page = await request(
              base(p.id) + '/workflows?' + query,
              pageSchema(summarySchema),
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
  const items = catalog.data?.pages.flatMap((p) => p.items) ?? []
  return (
    <StandardLayout title={t('workflows.title')}>
      <div className="af-catalog wf-catalog">
        <header className="af-catalog-header">
          <div>
            <p className="af-kicker">{t('workflows.builder')}</p>
            <h1>{t('workflows.title')}</h1>
            <p>{t('workflows.subtitle')}</p>
          </div>
          <Button
            disabled={!workspace.csrf || !summary.data?.permissions['version:create']}
            onClick={() => setCreating(true)}
          >
            <Plus size={16} />
            {t('workflows.create')}
          </Button>
        </header>
        <div className="af-catalog-tools">
          <label className="af-search">
            <Search size={17} />
            <input
              aria-label={t('workflows.search')}
              placeholder={t('workflows.search')}
              value={search}
              maxLength={120}
              onChange={(e) => setSearch(e.target.value)}
            />
          </label>
          <label className="af-filter">
            <span className="sr-only">{t('workflows.project')}</span>
            <select
              aria-label={t('workflows.project')}
              value={project}
              onChange={(e) => setFilter(e.target.value)}
            >
              <option value="">{t('workflows.allProjects')}</option>
              {workspace.context?.projects.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
          </label>
        </div>
        {workspace.error ? (
          <QueryError error={workspace.error} retry={workspace.retry} />
        ) : catalog.error ? (
          <QueryError error={catalog.error} retry={() => void catalog.refetch()} />
        ) : workspace.loading || (catalog.isPending && projects.length > 0) ? (
          <DataState kind="loading" />
        ) : !items.length ? (
          <div className="af-catalog-empty">
            <div className="af-empty-emblem">
              <Workflow size={36} />
            </div>
            <h2>{t('workflows.empty')}</h2>
            <p>{t('workflows.emptyHelp')}</p>
            <Button
              disabled={!workspace.csrf || !summary.data?.permissions['version:create']}
              onClick={() => setCreating(true)}
            >
              <Plus size={16} />
              {t('workflows.create')}
            </Button>
          </div>
        ) : (
          <div className="af-catalog-grid">
            {items.map((item) => (
              <Link
                className="af-catalog-card"
                key={item.id}
                to="/workflows/$projectId/$workflowId"
                params={{ projectId: item.project_id, workflowId: item.id }}
              >
                <div className="af-catalog-card-top">
                  <span className="af-node-icon">
                    <Workflow size={22} />
                  </span>
                  <ArrowUpRight size={17} />
                </div>
                <h2>{item.name}</h2>
                <p>
                  {t('workflows.draft')} · {t('workflows.revision')} {item.revision}
                </p>
                <footer>
                  <span>
                    {workspace.context?.projects.find((p) => p.id === item.project_id)?.name}
                  </span>
                  <span>{t('workflows.open')}</span>
                </footer>
              </Link>
            ))}
          </div>
        )}
        {catalog.hasNextPage && (
          <Button
            variant="secondary"
            disabled={catalog.isFetchingNextPage}
            onClick={() => void catalog.fetchNextPage()}
          >
            {t('workflows.more')}
          </Button>
        )}
        {(creating || brief?.kind === 'workflow') && (
          <CreateWorkflow
            initialName={brief?.kind === 'workflow' ? brief.goal.slice(0, 120) : ''}
            onClose={() => {
              setCreating(false)
              setDismissed(location.state.homeBriefId)
            }}
          />
        )}
      </div>
    </StandardLayout>
  )
}
function CreateWorkflow({ initialName, onClose }: { initialName: string; onClose: () => void }) {
  const creationLock = useRef(false)
  const workspace = useWorkspace(),
    { t } = useTranslation(),
    navigate = useNavigate()
  const [project, setProject] = useState(workspace.project?.id ?? ''),
    [name, setName] = useState(initialName),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(false)
  const permissions = useQuery({
    queryKey: [
      'workflow-create-permissions',
      workspace.context?.user.id,
      workspace.context?.organization.id,
      project,
    ],
    enabled: !!project,
    retry: false,
    queryFn: ({ signal }) =>
      request(base(project) + '/summary', permissionSchema, { signal }).then((p) =>
        scoped(p, workspace.context!.organization.id, project),
      ),
  })
  async function create() {
    if (
      busy ||
      creationLock.current ||
      !workspace.csrf ||
      !permissions.data?.permissions['version:create']
    )
      return
    creationLock.current = true
    setBusy(true)
    setError(false)
    try {
      const labels = Object.fromEntries(
        ['start', 'agent', 'review', 'end'].map((kind) => [kind, t('workflows.' + kind)]),
      )
      const saved = scoped(
        await write(
          base(project) + '/workflows',
          { ...initialDraft(name.trim(), labels), expected_revision: 0 },
          definitionSchema,
          workspace.csrf,
        ),
        workspace.context!.organization.id,
        project,
      )
      onClose()
      await navigate({
        to: '/workflows/$projectId/$workflowId',
        params: { projectId: project, workflowId: saved.id },
      })
    } catch {
      setError(true)
    } finally {
      setBusy(false)
      creationLock.current = false
    }
  }
  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open && !busy) onClose()
      }}
    >
      <DialogContent className="af-create-dialog">
        <DialogTitle>{t('workflows.create')}</DialogTitle>
        <DialogDescription>{t('workflows.createHelp')}</DialogDescription>
        <form
          onSubmit={(e) => {
            e.preventDefault()
            void create()
          }}
        >
          <label className="af-field">
            <span>{t('workflows.name')}</span>
            <input
              required
              disabled={busy}
              maxLength={120}
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </label>
          <label className="af-field">
            <span>{t('workflows.project')}</span>
            <select
              aria-label={t('workflows.project')}
              disabled={busy}
              required
              value={project}
              onChange={(e) => setProject(e.target.value)}
            >
              <option value="" disabled>
                {t('workflows.project')}
              </option>
              {workspace.context?.projects.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
          </label>
          {(error || permissions.error) && (
            <p role="alert" className="af-error">
              {t('workflows.genericError')}
            </p>
          )}
          <div className="af-dialog-actions">
            <Button type="button" variant="secondary" onClick={onClose} disabled={busy}>
              {t('agents.cancel')}
            </Button>
            <Button
              disabled={busy || !name.trim() || !permissions.data?.permissions['version:create']}
            >
              {t('workflows.create')}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  )
}
