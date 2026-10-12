import { useDeferredValue, useState } from 'react'
import { useInfiniteQuery, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useLocation, useNavigate } from '@tanstack/react-router'
import { useTranslation } from 'react-i18next'
import { ArrowUpRight, Bot, Plus, Search, ShieldCheck } from 'lucide-react'
import { StandardLayout } from '@/app/shell/MainWorkspace'
import { useWorkspace } from '@/app/providers/WorkspaceProvider'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogTitle } from '@/components/ui/dialog'
import { DataState, QueryError } from '@/components/feedback/DataState'
import { request } from '@/lib/api/client'
import { pageSchema, summarySchema } from '@/lib/types/workspace'
import { useSummary } from '@/hooks/use-workspace-queries'
import { readBrief, type CreationBrief } from '@/features/home/lib/home-state'
import {
  basePath,
  blueprintSchema,
  capabilitiesSchema,
  layoutSchema,
  post,
  scoped,
  workingSchema,
} from './api'
import { initialGraph } from './registry'
import './agents.css'

export function AgentCatalog() {
  const { t } = useTranslation(),
    workspace = useWorkspace(),
    location = useLocation()
  const [projectFilter, setProjectFilter] = useState<string | null>(null)
  const project = projectFilter ?? workspace.project?.id ?? ''
  const [search, setSearch] = useState(''),
    q = useDeferredValue(search.trim())
  const [creating, setCreating] = useState(false)
  const [dismissedBrief, setDismissedBrief] = useState<string>()
  const brief =
    workspace.context && workspace.project && dismissedBrief !== location.state.homeBriefId
      ? readBrief(
          location.state.homeBriefId,
          { organizationId: workspace.context.organization.id, projectId: workspace.project.id },
          workspace.context.user.id,
        )
      : undefined
  const projects = (workspace.context?.projects ?? []).filter(
    (item) => !project || item.id === project,
  )
  const summary = useSummary()
  const catalog = useInfiniteQuery({
    queryKey: [
      'agent-catalog',
      workspace.context?.user.id,
      workspace.context?.organization.id,
      project,
      q,
    ],
    enabled: !!workspace.context && projects.length > 0,
    retry: false,
    initialPageParam: null as Record<string, string> | null,
    queryFn: async ({ signal, pageParam }) => {
      const pages = await Promise.all(
        projects
          .filter((item) => !pageParam || pageParam[item.id])
          .map(async (item) => {
            const query = new URLSearchParams({ q, limit: '25' })
            if (pageParam?.[item.id]) query.set('cursor', pageParam[item.id]!)
            return scoped(
              await request(basePath(item.id) + '/resources/blueprints?' + query, pageSchema, {
                signal,
              }),
              workspace.context!.organization.id,
              item.id,
            )
          }),
      )
      return {
        items: pages.flatMap((page) => page.items),
        cursors: Object.fromEntries(
          pages
            .filter((page) => page.next_cursor)
            .map((page) => [page.project_id, page.next_cursor!]),
        ),
      }
    },
    getNextPageParam: (last) => (Object.keys(last.cursors).length ? last.cursors : undefined),
  })
  const agents = catalog.data?.pages.flatMap((page) => page.items) ?? []
  return (
    <StandardLayout title={t('agents.title')}>
      <div className="af-catalog">
        <header className="af-catalog-header">
          <div>
            <p className="af-kicker">{t('agents.factory')}</p>
            <h1>{t('agents.catalog')}</h1>
            <p>{t('agents.subtitle')}</p>
          </div>
          <Button
            disabled={!workspace.csrf || !summary.data?.permissions['blueprint:create']}
            onClick={() => setCreating(true)}
          >
            <Plus size={16} />
            {t('agents.create')}
          </Button>
        </header>
        <div className="af-catalog-tools">
          <label className="af-search">
            <Search size={17} />
            <input
              aria-label={t('agents.search')}
              placeholder={t('agents.search')}
              maxLength={120}
              value={search}
              onChange={(event) => setSearch(event.target.value)}
            />
          </label>
          <label className="af-filter">
            <span className="sr-only">{t('agents.project')}</span>
            <select value={project} onChange={(event) => setProjectFilter(event.target.value)}>
              <option value="">{t('agents.allProjects')}</option>
              {workspace.context?.projects.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name}
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
          <DataState kind="loading" title={t('agents.loading')} />
        ) : !agents.length ? (
          <div className="af-catalog-empty">
            <div className="af-empty-emblem">
              <Bot size={36} />
            </div>
            <h2>{t('agents.empty')}</h2>
            <p>{t('agents.emptyDescription')}</p>
            <div className="af-empty-path">
              <span>{t('agents.input')}</span>
              <span>→</span>
              <span>
                <Bot size={16} />
                {t('agents.agent')}
              </span>
              <span>→</span>
              <span>{t('agents.output')}</span>
            </div>
            <Button
              disabled={!summary.data?.permissions['blueprint:create']}
              onClick={() => setCreating(true)}
            >
              <Plus size={16} />
              {t('agents.create')}
            </Button>
          </div>
        ) : (
          <div className="af-catalog-grid">
            {agents.map((agent) => (
              <Link
                className="af-catalog-card"
                key={agent.id}
                to="/agents/$projectId/$blueprintId"
                params={{ projectId: agent.project_id, blueprintId: agent.id }}
              >
                <div className="af-catalog-card-top">
                  <span className="af-node-icon">
                    <Bot size={22} />
                  </span>
                  <ArrowUpRight size={17} />
                </div>
                <h2>{agent.name}</h2>
                <p>{agent.description || t('agents.agentDescription')}</p>
                <footer>
                  <span>
                    {workspace.context?.projects.find((item) => item.id === agent.project_id)?.name}
                  </span>
                  <span>{t('agents.blueprint')}</span>
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
            {t('agents.more')}
          </Button>
        )}
        <p className="af-catalog-note">
          <ShieldCheck size={14} />
          {t('agents.bounded')}
        </p>
        {(creating || brief?.kind === 'agent') && (
          <CreateAgentDialog
            brief={brief}
            onClose={() => {
              setCreating(false)
              setDismissedBrief(location.state.homeBriefId)
            }}
          />
        )}
      </div>
    </StandardLayout>
  )
}

export function CreateAgentDialog({
  brief,
  onClose,
}: {
  brief?: CreationBrief
  onClose: () => void
}) {
  const { t } = useTranslation(),
    workspace = useWorkspace(),
    navigate = useNavigate(),
    client = useQueryClient()
  const [project, setProject] = useState(workspace.project?.id ?? '')
  const [name, setName] = useState(''),
    [objective, setObjective] = useState(brief?.goal ?? '')
  const [model, setModel] = useState(''),
    [pending, setPending] = useState(false),
    [error, setError] = useState(false)
  const capability = useQuery({
    queryKey: [
      'agent-capabilities',
      workspace.context?.user.id,
      workspace.context?.organization.id,
      project,
    ],
    enabled: !!project && !!workspace.context,
    retry: false,
    queryFn: async ({ signal }) =>
      scoped(
        await request(basePath(project) + '/factory/capabilities', capabilitiesSchema, { signal }),
        workspace.context!.organization.id,
        project,
      ),
  })
  const permissions = useQuery({
    queryKey: ['agent-create-permissions', workspace.context?.user.id, project],
    enabled: !!project && !!workspace.context,
    retry: false,
    queryFn: async ({ signal }) => {
      const result = await request(basePath(project) + '/summary', summarySchema, { signal })
      return scoped(result, workspace.context!.organization.id, project).permissions
    },
  })
  const selectedModel = model || capability.data?.models[0]?.model_id || ''
  async function create(event: React.FormEvent) {
    event.preventDefault()
    if (
      pending ||
      !workspace.csrf ||
      !capability.data?.draft_defaults ||
      !permissions.data?.['blueprint:create'] ||
      !permissions.data?.['version:create']
    )
      return
    setPending(true)
    setError(false)
    let blueprint: { id: string } | undefined
    try {
      const slug = 'agent-' + crypto.randomUUID().slice(0, 12)
      blueprint = scoped(
        await post(basePath(project) + '/blueprints', blueprintSchema, workspace.csrf, {
          name: name.trim(),
          slug,
          objective,
        }),
        workspace.context!.organization.id,
        project,
      )
      const definition = {
        ...capability.data.draft_defaults,
        objective,
        model: selectedModel,
        output_contract: {
          ...capability.data.draft_defaults.output_contract,
          description: brief?.output || null,
        },
        model_policy: {
          ...capability.data.draft_defaults.model_policy,
          primary_model: selectedModel,
          allowed_models: [selectedModel],
        },
      }
      await post(basePath(project, blueprint.id) + '/working-copy', workingSchema, workspace.csrf, {
        expected_generation: 0,
        definition,
      })
      await post(basePath(project, blueprint.id) + '/editor-layout', layoutSchema, workspace.csrf, {
        expected_generation: 0,
        graph: initialGraph(),
        viewport: { x: 0, y: 0, zoom: 0.8 },
      })
      void client.invalidateQueries({ queryKey: ['agent-catalog'] })
      void client.invalidateQueries({ queryKey: ['summary'] })
    } catch {
      setError(true)
    } finally {
      setPending(false)
      if (blueprint) {
        workspace.selectProject(project)
        void navigate({
          to: '/agents/$projectId/$blueprintId',
          params: { projectId: project, blueprintId: blueprint.id },
        })
        onClose()
      }
    }
  }
  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open && !pending) onClose()
      }}
    >
      <DialogContent className="af-create-dialog">
        <DialogTitle>{t('agents.create')}</DialogTitle>
        <DialogDescription>{t('agents.createDescription')}</DialogDescription>
        <form onSubmit={(event) => void create(event)}>
          <label className="af-field">
            <span>{t('agents.project')}</span>
            <select
              disabled={pending}
              value={project}
              required
              onChange={(event) => {
                setProject(event.target.value)
                setModel('')
              }}
            >
              {workspace.context?.projects.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name}
                </option>
              ))}
            </select>
          </label>
          <label className="af-field">
            <span>{t('agents.name')}</span>
            <input
              value={name}
              required
              minLength={2}
              maxLength={100}
              disabled={pending}
              onChange={(event) => setName(event.target.value)}
            />
          </label>
          <label className="af-field">
            <span>{t('agents.objective')}</span>
            <textarea
              rows={3}
              maxLength={2000}
              disabled={pending}
              value={objective}
              onChange={(event) => setObjective(event.target.value)}
            />
          </label>
          <label className="af-field">
            <span>{t('agents.model')}</span>
            <select
              value={selectedModel}
              disabled={pending || capability.isPending}
              required
              onChange={(event) => setModel(event.target.value)}
            >
              <option value="" disabled>
                {t('agents.model')}
              </option>
              {capability.data?.models.map((item) => (
                <option key={item.model_id} value={item.model_id}>
                  {item.display_name}
                </option>
              ))}
            </select>
          </label>
          {capability.isError || permissions.isError ? (
            <p className="af-error" role="alert">
              {t('agents.genericError')}
            </p>
          ) : !capability.isPending && !capability.data?.models.length ? (
            <p className="af-note">{t('agents.noModel')}</p>
          ) : null}
          {error && (
            <p role="alert" className="af-error">
              {t('agents.genericError')}
            </p>
          )}
          <div className="af-dialog-actions">
            <Button type="button" variant="secondary" onClick={onClose} disabled={pending}>
              {t('agents.cancel')}
            </Button>
            <Button
              disabled={
                pending ||
                name.trim().length < 2 ||
                !selectedModel ||
                !capability.data?.draft_defaults ||
                !permissions.data?.['blueprint:create'] ||
                !permissions.data?.['version:create']
              }
            >
              {t(pending ? 'agents.saving' : 'agents.create')}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  )
}
