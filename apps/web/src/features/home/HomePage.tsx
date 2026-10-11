import { translate as tr } from '@/i18n'
import { useTranslation } from 'react-i18next'
import { useState } from 'react'
import { StandardLayout } from '@/app/shell/MainWorkspace'
import { useWorkspace } from '@/app/providers/WorkspaceProvider'
import { DataState, QueryError } from '@/components/feedback/DataState'
import { Button } from '@/components/ui/button'
import { ApiError } from '@/lib/api/client'
import { useHomeOverview } from './hooks/useHomeOverview'
import { canCreate, resourceItem, type CreationKind, type HomeResource } from './lib/home-state'
import { HomeHeader } from './components/HomeHeader'
import { HomeAssistant } from './components/HomeAssistant'
import { QuickActions } from './components/QuickActions'
import { ContinueWorking } from './components/ContinueWorking'
import { NeedsAttention } from './components/NeedsAttention'
import { RecentActivity } from './components/RecentActivity'
import { GettingStarted } from './components/GettingStarted'
import { GuidedCreation } from './components/GuidedCreation'
import { HomeDetailsDrawer } from './components/HomeDetailsDrawer'
import { HomeServiceStatus } from './components/HomeServiceStatus'
import { ProjectDialog } from '@/features/projects/components/ProjectDialog'
import './home.css'

export function HomePage() {
  useTranslation()

  const { context } = useWorkspace()
  return (
    <StandardLayout title={tr('ui.home')}>
      <HomeContent key={`${context?.user.id}:${context?.organization.id}`} />
    </StandardLayout>
  )
}
function HomeContent() {
  useTranslation()

  const overview = useHomeOverview()
  const { workspace, data, condition, scope } = overview
  const [creation, setCreation] = useState<{
    kind?: CreationKind
    goal: string
    scratch: boolean
  } | null>(null)
  const [creatingProject, setCreatingProject] = useState(false)
  const [selection, setSelection] = useState<HomeResource | null>(null)
  const permissions = data?.summary.permissions ?? {}
  const canAgent = canCreate(permissions, 'agent'),
    canWorkflow = canCreate(permissions, 'workflow')
  return (
    <div
      className="home-page"
      data-home-state={condition ?? (overview.error ? 'error' : 'loading')}
    >
      <HomeHeader />
      {overview.error ? (
        overview.error instanceof ApiError && [404, 501].includes(overview.error.status) ? (
          <DataState
            kind="unavailable"
            title={tr('ui.home_overview_unavailable')}
            description={tr(
              'ui.a_required_workspace_service_is_unavailable_your_project_has_not_been_classified_as_empty',
            )}
            retry={overview.retry}
          />
        ) : (
          <QueryError error={overview.error} retry={overview.retry} />
        )
      ) : workspace.signedOut ? (
        <>
          <DataState
            kind="unauthorized"
            title={tr('ui.you_are_signed_out')}
            description={tr('ui.sign_in_to_load_your_workspace')}
          />
          <div className="text-center">
            <Button asChild>
              <a href="/auth/login">{tr('ui.sign_in_to_aryn')}</a>
            </Button>
          </div>
        </>
      ) : overview.loading ? (
        <HomeSkeleton />
      ) : !workspace.project ? (
        workspace.context?.user.role === 'admin' ? (
          <div className="home-zero-projects">
            <DataState
              kind="empty"
              title={tr('projects.emptyTitle')}
              description={tr('projects.emptyDescription')}
            />
            <Button onClick={() => setCreatingProject(true)}>{tr('projects.create')}</Button>
            {creatingProject && <ProjectDialog onClose={() => setCreatingProject(false)} />}
          </div>
        ) : (
          <DataState
            kind="empty"
            title={tr('ui.no_accessible_projects')}
            description={tr('ui.no_project_is_available_to_this_account')}
          />
        )
      ) : (
        data && (
          <>
            <HomeAssistant compact={condition !== 'new'}>
              {condition === 'unavailable' && !overview.services.length && (
                <DataState
                  kind="unavailable"
                  title={tr('ui.workspace_inventory_unavailable')}
                  description={tr(
                    'ui.the_backend_has_not_reported_enough_inventory_information_to_determine_whether_this_project_is_new',
                  )}
                />
              )}
              <QuickActions
                canAgent={canAgent}
                canWorkflow={canWorkflow}
                onCreate={(kind, scratch = false) => setCreation({ kind, scratch, goal: '' })}
              />
              <HomeServiceStatus services={overview.services} />
              {condition === 'new' ? (
                <GettingStarted />
              ) : (
                <>
                  <NeedsAttention items={data.attention} onOpen={setSelection} />
                  <ContinueWorking
                    agents={data.agents.map((item) =>
                      resourceItem(item, 'agent', workspace.project?.name),
                    )}
                    workflows={data.workflows.map((item) => ({
                      id: item.id,
                      name: item.name,
                      kind: 'workflow',
                      revision: item.revision,
                    }))}
                    onOpen={setSelection}
                    workflowsError={overview.workflowsError}
                    conversations={data.conversations}
                  />
                  <RecentActivity items={data.activity} onOpen={setSelection} />
                  {condition === 'active' &&
                    !data.attention.length &&
                    !data.agents.length &&
                    !data.workflows.length &&
                    !data.activity.length && (
                      <p className="home-section-note">
                        {tr(
                          'ui.work_is_recorded_in_this_project_no_recent_definitions_or_activity_are_available_in_this_overview',
                        )}
                      </p>
                    )}
                </>
              )}
            </HomeAssistant>
            {creation && (
              <GuidedCreation
                initialKind={creation.kind}
                goal={creation.goal}
                scratch={creation.scratch}
                permissions={permissions}
                onClose={() => setCreation(null)}
              />
            )}
            {selection && (
              <HomeDetailsDrawer
                item={selection}
                scope={{
                  organizationId: scope.organizationId,
                  projectId: selection.projectId ?? scope.projectId,
                }}
                projectName={selection.projectName ?? workspace.project?.name ?? ''}
                onClose={() => setSelection(null)}
              />
            )}
          </>
        )
      )}
    </div>
  )
}
function HomeSkeleton() {
  useTranslation()

  return (
    <div className="home-skeleton" role="status" aria-busy="true">
      <span className="sr-only">{tr('ui.loading_home_overview')}</span>
      <div className="home-skeleton-composer" />
      <div className="home-skeleton-actions">
        <span />
        <span />
        <span />
      </div>
      <div className="home-skeleton-columns">
        <div />
        <div />
      </div>
    </div>
  )
}
