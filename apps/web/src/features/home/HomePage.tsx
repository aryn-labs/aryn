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
import './home.css'

export function HomePage() {
  const { context, project } = useWorkspace()
  return (
    <StandardLayout title="Home">
      <HomeContent key={`${context?.user.id}:${context?.organization.id}:${project?.id}`} />
    </StandardLayout>
  )
}
function HomeContent() {
  const overview = useHomeOverview()
  const { workspace, data, condition, scope } = overview
  const [creation, setCreation] = useState<{
    kind?: CreationKind
    goal: string
    scratch: boolean
  } | null>(null)
  const [selection, setSelection] = useState<HomeResource | null>(null)
  const permissions = data?.summary.permissions ?? {}
  const canAgent = canCreate(permissions, 'agent'),
    canWorkflow = canCreate(permissions, 'workflow')
  return (
    <div
      className="home-page"
      data-home-state={condition ?? (overview.error ? 'error' : 'loading')}
    >
      <HomeHeader projectName={workspace.project?.name} />
      {overview.error ? (
        overview.error instanceof ApiError && [404, 501].includes(overview.error.status) ? (
          <DataState
            kind="unavailable"
            title="Home overview unavailable"
            description="A required workspace service is unavailable. Your project has not been classified as empty."
            retry={overview.retry}
          />
        ) : (
          <QueryError error={overview.error} retry={overview.retry} />
        )
      ) : workspace.signedOut ? (
        <>
          <DataState
            kind="unauthorized"
            title="You are signed out"
            description="Sign in to load your workspace."
          />
          <div className="text-center">
            <Button asChild>
              <a href="/auth/login">Sign in to ARYN</a>
            </Button>
          </div>
        </>
      ) : overview.loading ? (
        <HomeSkeleton />
      ) : !workspace.project ? (
        <DataState
          kind="empty"
          title="No accessible projects"
          description="No project is available to this account."
        />
      ) : (
        data && (
          <>
            <HomeAssistant
              compact={condition !== 'new'}
              canAgent={canAgent}
              canWorkflow={canWorkflow}
              onDraft={(kind, goal) => setCreation({ kind, goal, scratch: false })}
            >
              {condition === 'unavailable' && !overview.services.length && (
                <DataState
                  kind="unavailable"
                  title="Workspace inventory unavailable"
                  description="The backend has not reported enough inventory information to determine whether this project is new."
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
                    agents={data.agents.map((item) => resourceItem(item, 'agent'))}
                    workflows={data.workflows.map((item) => ({
                      id: item.id,
                      name: item.name,
                      kind: 'workflow',
                      revision: item.revision,
                    }))}
                    onOpen={setSelection}
                    workflowsError={overview.workflowsError}
                  />
                  <RecentActivity items={data.activity} onOpen={setSelection} />
                  {condition === 'active' &&
                    !data.attention.length &&
                    !data.agents.length &&
                    !data.workflows.length &&
                    !data.activity.length && (
                      <p className="home-section-note">
                        Work is recorded in this project. No recent definitions or activity are
                        available in this overview.
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
            {selection && workspace.project && (
              <HomeDetailsDrawer
                item={selection}
                scope={scope}
                projectName={workspace.project.name}
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
  return (
    <div className="home-skeleton" role="status" aria-busy="true">
      <span className="sr-only">Loading Home overview</span>
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
