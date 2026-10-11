import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { ChevronRight, ShieldCheck } from 'lucide-react'
import { DataState } from '@/components/feedback/DataState'
import { useHomeOverview } from '@/features/home/hooks/useHomeOverview'
import { HomeDetailsDrawer } from '@/features/home/components/HomeDetailsDrawer'
import type { HomeResource } from '@/features/home/lib/home-state'
import { statusLabel } from '@/features/home/lib/home-labels'
import { useProjectCollection } from '../hooks/useProjects'
import type { ProjectResource, Scope } from '../lib/api'
import { ProjectsSkeleton } from '../ProjectsPage'
import { ResourceRows } from './ResourceRows'
import { ProjectQueryError } from './ProjectQueryError'

export function ProjectOverview({
  scope,
  onOpen,
}: {
  scope: Scope
  onOpen: (item: ProjectResource) => void
}) {
  const { t } = useTranslation()
  const work = useProjectCollection(scope, 'work', { limit: 4, active_only: true })
  const team = useProjectCollection(scope, 'team', { limit: 3, kind: 'assignment' })
  const results = useProjectCollection(scope, 'results', { limit: 3 })
  const home = useHomeOverview()
  const [attentionDetail, setAttentionDetail] = useState<HomeResource | null>(null)
  const queries = [work, team, results]
  // The current Relay contract contains disposable demonstration incidents only.
  const problems =
    home.data?.attention
      .filter((item) => item.kind !== 'incident')
      .filter(
        (item) =>
          item.kind !== 'run' ||
          home.data?.summary.latest_runs.find((run) => run.id === item.id)?.verified === true,
      ) ?? []
  const busy =
    work.data?.pages
      .flatMap((page) => page.items)
      .filter((item) =>
        ['running', 'started', 'queued', 'stopping', 'waiting_review'].includes(item.status ?? ''),
      ) ?? []
  const agents =
    team.data?.pages.flatMap((page) => page.items).filter((item) => item.kind === 'assignment') ??
    []
  const outputs = results.data?.pages.flatMap((page) => page.items) ?? []
  const empty = !busy.length && !agents.length && !outputs.length && !problems.length
  if (queries.some((query) => query.isPending) || home.loading) return <ProjectsSkeleton />
  return (
    <div className="project-overview">
      <h2 className="sr-only">{t('projects.overview')}</h2>
      {home.error && <ProjectQueryError error={home.error} retry={home.retry} />}
      {problems.length > 0 && (
        <section>
          <h2>{t('projects.decisions')}</h2>
          <div className="project-resource-list">
            {problems.slice(0, 3).map((item) => (
              <button
                key={`${item.kind}:${item.id}`}
                type="button"
                className="project-attention-row"
                onClick={() => setAttentionDetail(item)}
              >
                <ShieldCheck size={19} aria-hidden="true" />
                <span className="project-row-text">
                  <strong>{item.name}</strong>
                  <span>
                    {[
                      busy.find((resource) => resource.id === item.id)?.name,
                      t('projects.attentionKinds.' + item.kind),
                    ]
                      .filter(Boolean)
                      .join(' · ')}
                  </span>
                </span>
                <span className="project-status-warning">
                  {item.status ? statusLabel(item.status) : ''}
                </span>
                <ChevronRight size={15} aria-hidden="true" />
              </button>
            ))}
          </div>
        </section>
      )}
      {busy.length > 0 && (
        <section>
          <h2>{t('projects.working')}</h2>
          <ResourceRows items={busy.slice(0, 4)} onOpen={onOpen} />
        </section>
      )}
      <div className="project-overview-columns">
        {agents.length > 0 && (
          <section>
            <h2>{t('projects.team')}</h2>
            <ResourceRows items={agents.slice(0, 3)} onOpen={onOpen} />
          </section>
        )}
        {outputs.length > 0 && (
          <section>
            <h2>{t('projects.latestResults')}</h2>
            <ResourceRows items={outputs.slice(0, 3)} onOpen={onOpen} />
          </section>
        )}
      </div>
      {queries
        .filter((query) => query.error)
        .map((query, index) => (
          <ProjectQueryError key={index} error={query.error!} retry={() => void query.refetch()} />
        ))}
      {empty && !home.error && !home.services.length && !queries.some((query) => query.error) && (
        <DataState title={t('projects.startTitle')} description={t('projects.startDescription')} />
      )}
      {home.services.length > 0 && (
        <p className="project-service-note">{t('projects.errorUnavailable')}</p>
      )}
      {attentionDetail && (
        <HomeDetailsDrawer
          scope={{ organizationId: scope.organization, projectId: scope.project }}
          projectName={home.workspace.project?.name ?? ''}
          item={attentionDetail}
          onClose={() => setAttentionDetail(null)}
        />
      )}
    </div>
  )
}
