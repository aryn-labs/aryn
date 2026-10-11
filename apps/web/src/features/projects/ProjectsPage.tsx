import { useDeferredValue, useState } from 'react'
import { Link } from '@tanstack/react-router'
import { useTranslation } from 'react-i18next'
import { Folder, Search, Plus, ChevronRight } from 'lucide-react'
import { StandardLayout } from '@/app/shell/MainWorkspace'
import { useWorkspace } from '@/app/providers/WorkspaceProvider'
import { DataState } from '@/components/feedback/DataState'
import { Button } from '@/components/ui/button'
import { formatDate } from '@/lib/utils'
import { useProjects } from './hooks/useProjects'
import { ProjectDialog } from './components/ProjectDialog'
import { ProjectQueryError } from './components/ProjectQueryError'
import './projects.css'

export function ProjectsPage() {
  const { t } = useTranslation()
  const workspace = useWorkspace()
  const [search, setSearch] = useState(''),
    q = useDeferredValue(search.trim())
  const [creating, setCreating] = useState(false)
  const query = useProjects(q),
    data = query.data?.pages.flatMap((page) => page.items) ?? []
  const canCreate = !query.isError && query.data?.pages[0]?.can_create === true
  return (
    <StandardLayout title={t('projects.title')}>
      <div className="projects-page">
        <header className="projects-list-header">
          <h1>{t('projects.title')}</h1>
          {canCreate && data.length > 0 && (
            <Button onClick={() => setCreating(true)}>
              <Plus size={16} />
              {t('projects.new')}
            </Button>
          )}
        </header>
        <h2 className="sr-only">{t('projects.listHeading')}</h2>
        {workspace.error ? (
          <ProjectQueryError error={workspace.error} retry={workspace.retry} />
        ) : workspace.signedOut ? (
          <DataState kind="unauthorized" retry={workspace.retry} />
        ) : workspace.loading || query.isPending ? (
          <ProjectsSkeleton />
        ) : query.error ? (
          <ProjectQueryError error={query.error} retry={() => void query.refetch()} />
        ) : !data.length && !q ? (
          <div className="project-empty">
            <span className="project-empty-icon">
              <Folder size={29} />
            </span>
            <h2>{t('projects.emptyTitle')}</h2>
            <p>{t(canCreate ? 'projects.emptyDescription' : 'projects.noCreate')}</p>
            {canCreate && (
              <Button onClick={() => setCreating(true)}>
                <Plus size={16} />
                {t('projects.create')}
              </Button>
            )}
          </div>
        ) : (
          <>
            <label className="project-search">
              <Search size={17} aria-hidden="true" />
              <input
                aria-label={t('projects.search')}
                placeholder={t('projects.search')}
                value={search}
                maxLength={120}
                onChange={(event) => setSearch(event.target.value)}
              />
            </label>
            {data.length ? (
              <div className="project-list">
                {data.map((project) => (
                  <Link
                    key={project.id}
                    to="/projects/$projectId"
                    params={{ projectId: project.id }}
                    className="project-list-row"
                  >
                    <span className="project-symbol">
                      <Folder size={23} />
                    </span>
                    <span className="project-row-text">
                      <strong>{project.name}</strong>
                      {project.description && <span>{project.description}</span>}
                    </span>
                    <time dateTime={project.created_at}>{formatDate(project.created_at)}</time>
                    <ChevronRight size={17} aria-hidden="true" />
                  </Link>
                ))}
              </div>
            ) : (
              <DataState title={t('projects.noMatches')} />
            )}
            {query.hasNextPage && (
              <Button
                variant="secondary"
                disabled={query.isFetchingNextPage}
                onClick={() => void query.fetchNextPage()}
              >
                {t(query.isFetchingNextPage ? 'projects.loading' : 'projects.more')}
              </Button>
            )}
          </>
        )}
        {creating && <ProjectDialog onClose={() => setCreating(false)} />}
      </div>
    </StandardLayout>
  )
}
export function ProjectsSkeleton() {
  const { t } = useTranslation()
  return (
    <div className="project-skeleton" role="status" aria-label={t('projects.loading')}>
      <span className="sr-only">{t('projects.loading')}</span>
      {[1, 2, 3].map((item) => (
        <div key={item} className="project-skeleton-row" />
      ))}
    </div>
  )
}
