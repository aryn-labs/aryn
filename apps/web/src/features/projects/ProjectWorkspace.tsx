import { useEffect, useRef, useState } from 'react'
import { Link, useLocation, useNavigate, useParams, useSearch } from '@tanstack/react-router'
import { useTranslation } from 'react-i18next'
import { ChevronRight, MoreHorizontal, Users, Cloud, Pencil } from 'lucide-react'
import { StandardLayout } from '@/app/shell/MainWorkspace'
import { useWorkspace } from '@/app/providers/WorkspaceProvider'
import { DataState } from '@/components/feedback/DataState'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { useProject, useProjectScope } from './hooks/useProjects'
import { parseSelection, selectionValue, type ProjectResource, type Collection } from './lib/api'
import { ProjectsSkeleton } from './ProjectsPage'
import { ProjectDialog } from './components/ProjectDialog'
import { ProjectOverview } from './components/ProjectOverview'
import { ProjectCollection } from './components/ProjectCollection'
import { ProjectResourceDrawer } from './components/ProjectResourceDrawer'
import { ProjectQueryError } from './components/ProjectQueryError'
import './projects.css'

const tabs = ['overview', 'work', 'team', 'results', 'activity'] as const
export function ProjectWorkspace() {
  const { projectId = '' } = useParams({ strict: false })
  return <ScopedProjectWorkspace key={projectId} projectId={projectId} />
}
function ScopedProjectWorkspace({ projectId }: { projectId: string }) {
  const { t } = useTranslation()
  const scope = useProjectScope(projectId),
    workspace = useWorkspace(),
    project = useProject(projectId)
  const navigate = useNavigate(),
    location = useLocation(),
    search = useSearch({ strict: false })
  const suffix = location.pathname.split('/')[3],
    tab = tabs.find((value) => value === suffix) ?? 'overview'
  const alignedRoute = useRef('')
  const [editing, setEditing] = useState(false)
  useEffect(() => {
    if (!workspace.context) return
    if (alignedRoute.current !== projectId) {
      if (workspace.context.projects.some((value) => value.id === projectId)) {
        workspace.selectProject(projectId)
        alignedRoute.current = projectId
      }
    } else if (workspace.project && workspace.project.id !== projectId) {
      void navigate({
        to: tab === 'overview' ? '/projects/$projectId' : `/projects/$projectId/${tab}`,
        params: { projectId: workspace.project.id },
        search: {},
      })
    }
  }, [navigate, projectId, tab, workspace])
  const selection = parseSelection(
    'selection' in search && typeof search.selection === 'string' ? search.selection : undefined,
  )
  function open(item: ProjectResource) {
    void navigate({ to: '.', search: { selection: selectionValue(item) }, replace: false })
  }
  return (
    <StandardLayout title={t('projects.title')}>
      <div className="projects-page project-workspace" key={projectId}>
        {workspace.error ? (
          <ProjectQueryError error={workspace.error} retry={workspace.retry} />
        ) : workspace.signedOut ? (
          <DataState kind="unauthorized" retry={workspace.retry} />
        ) : project.isPending ? (
          <ProjectsSkeleton />
        ) : project.error ? (
          <ProjectQueryError error={project.error} retry={() => void project.refetch()} />
        ) : (
          project.data && (
            <>
              <nav className="project-breadcrumb" aria-label={t('projects.title')}>
                <Link to="/projects">{t('projects.title')}</Link>
                <ChevronRight size={13} aria-hidden="true" />
                <span>{project.data.name}</span>
              </nav>
              <header className="project-workspace-header">
                <div>
                  <h1>{project.data.name}</h1>
                  {project.data.description && <p>{project.data.description}</p>}
                </div>
                {project.data.can_edit && (
                  <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                      <Button variant="ghost" size="icon" aria-label={t('projects.options')}>
                        <MoreHorizontal size={19} />
                      </Button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="end">
                      <DropdownMenuItem onSelect={() => setEditing(true)}>
                        <Pencil size={15} />
                        {t('projects.edit')}
                      </DropdownMenuItem>
                    </DropdownMenuContent>
                  </DropdownMenu>
                )}
              </header>
              <div className="project-metadata">
                <span>
                  <Users size={14} />
                  {t('projects.organizationProject')}
                </span>
                {workspace.context?.mode === 'development' && (
                  <span>
                    <Cloud size={14} />
                    {t('projects.local')}
                  </span>
                )}
              </div>
              <nav className="project-tabs" aria-label={t('projects.tabs')}>
                {tabs.map((value) => (
                  <Link
                    key={value}
                    to={
                      value === 'overview'
                        ? '/projects/$projectId'
                        : `/projects/$projectId/${value}`
                    }
                    params={{ projectId }}
                    search={{}}
                    activeOptions={{ exact: true }}
                    aria-current={tab === value ? 'page' : undefined}
                  >
                    {t('projects.' + value)}
                  </Link>
                ))}
              </nav>
              {tab === 'team' && (
                <div className="project-agent-factory-link">
                  <Button variant="secondary" asChild>
                    <Link to="/agents">{t('agents.catalog')}</Link>
                  </Button>
                </div>
              )}
              {['work', 'results', 'activity'].includes(tab) && (
                <nav className="project-agent-factory-link" aria-label={t('intelligence.linked')}>
                  {(['brief', 'relay', 'bench'] as const).map((module) => (
                    <Button key={module} variant="secondary" asChild>
                      <Link to={'/' + module} search={{ project: projectId }}>
                        {t('intelligence.' + module)}
                      </Link>
                    </Button>
                  ))}
                </nav>
              )}
              {workspace.project?.id === projectId &&
                (tab === 'overview' ? (
                  <ProjectOverview key={projectId} scope={scope} onOpen={open} />
                ) : (
                  <ProjectCollection
                    key={`${projectId}:${tab}`}
                    scope={scope}
                    collection={tab as Collection}
                    onOpen={open}
                  />
                ))}
              {editing && (
                <ProjectDialog project={project.data} onClose={() => setEditing(false)} />
              )}
              <ProjectResourceDrawer
                scope={scope}
                selection={selection}
                onClose={() => void navigate({ to: '.', search: {}, replace: true })}
              />
            </>
          )
        )}
      </div>
    </StandardLayout>
  )
}
