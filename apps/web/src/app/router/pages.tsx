import { labelText } from '@/i18n'
import { translate as tr } from '@/i18n'
import { useTranslation } from 'react-i18next'
import { Link } from '@tanstack/react-router'
import { StandardLayout } from '@/app/shell/MainWorkspace'
import { DataState, QueryError } from '@/components/feedback/DataState'
import { Button } from '@/components/ui/button'
import { useWorkspace } from '@/app/providers/WorkspaceProvider'
import { useWorkspaceStatus } from '@/hooks/use-workspace-queries'
import { Box, Cloud, Monitor } from 'lucide-react'
import { HomeDraftHandoff } from '@/features/home/components/HomeDraftHandoff'
import { ChatPreferences } from '@/features/settings/ChatPreferences'
export function FeatureScaffold({ title }: { title: string }) {
  useTranslation()

  const { project } = useWorkspace()
  return (
    <StandardLayout title={labelText(title)}>
      <section className="feature-scaffold">
        <p className="eyebrow">{tr('ui.aryn_workspace')}</p>
        <h1>{labelText(title)}</h1>
        <p className="muted">{project?.name ?? tr('ui.no_project_selected')}</p>
        {title === 'Settings' ? (
          <>
            <ChatPreferences />
            <WorkspaceRuntime />
          </>
        ) : (
          <HomeDraftHandoff title={title}>
            <div className="scaffold-card">
              <DataState
                kind="unavailable"
                title={tr('ui.feature_unavailable', { feature: labelText(title) })}
                description={tr(
                  'ui.this_release_provides_the_studio_shell_and_home_feature_tools_will_be_added_to_this_workspace_in_a_future_release',
                )}
              />
              <Button variant="secondary" asChild>
                <Link to="/">{tr('ui.back_to_home')}</Link>
              </Button>
            </div>
          </HomeDraftHandoff>
        )}
      </section>
    </StandardLayout>
  )
}
function WorkspaceRuntime() {
  useTranslation()

  const { context, project, loading, error, retry } = useWorkspace()
  const status = useWorkspaceStatus()
  const measuredStatus = context && !status.isError ? status.data : undefined
  if (error) return <QueryError error={error} retry={retry} />
  if (loading) return <DataState kind="loading" title={tr('ui.loading_workspace')} />
  if (!context)
    return (
      <DataState
        kind="unavailable"
        description={tr('ui.sign_in_to_view_workspace_runtime_information')}
      />
    )
  const environment =
    context.mode === 'hosted'
      ? 'Hosted'
      : context.mode === 'development'
        ? 'Local'
        : 'Isolated test'
  const EnvironmentIcon = context.mode === 'hosted' ? Cloud : Monitor
  return (
    <div className="runtime-grid">
      <section className="runtime-card" aria-labelledby="environment-heading">
        <h2 id="environment-heading">
          <EnvironmentIcon size={19} aria-hidden="true" />
          {tr('ui.environment')}
        </h2>
        <p className="muted">
          {tr('ui.runtime_information_for')}
          {context.organization.name}.
        </p>
        <dl className="detail-list">
          <dt>{tr('ui.environment')}</dt>
          <dd>{labelText(environment)}</dd>
          <dt>{tr('ui.mode')}</dt>
          <dd>{context.mode}</dd>
        </dl>
        {status.isLoading ? (
          <DataState kind="loading" title={tr('ui.checking_runtime')} />
        ) : status.error ? (
          <QueryError error={status.error} retry={() => void status.refetch()} />
        ) : measuredStatus ? (
          <div className="info-card">
            <strong>
              {measuredStatus.runtime.ready ? tr('ui.runtime_ready') : tr('ui.runtime_not_ready')}
            </strong>
            <p>{measuredStatus.runtime.message}</p>
            <small>
              {tr('ui.connection')}
              {measuredStatus.runtime.connected ? 'Connected' : 'Disconnected'}
            </small>
          </div>
        ) : (
          <DataState kind="unavailable" description={tr('ui.runtime_information_is_unavailable')} />
        )}
      </section>
      <section className="runtime-card" aria-labelledby="models-heading">
        <h2 id="models-heading">
          <Box size={19} aria-hidden="true" />
          {tr('ui.models')}
        </h2>
        <p className="muted">{project?.name ?? tr('ui.no_project_selected')}</p>
        <DataState
          kind={project ? 'unavailable' : 'empty'}
          title={project ? tr('ui.active_model_unavailable') : tr('ui.no_project_selected')}
          description={
            project
              ? tr('ui.no_active_or_default_model_has_been_reported_for_this_project')
              : tr('ui.no_project_is_available_to_this_account')
          }
        />
        {status.isLoading ? (
          <p role="status">{tr('ui.loading_model_catalog')}</p>
        ) : status.error ? (
          <QueryError error={status.error} retry={() => void status.refetch()} />
        ) : measuredStatus?.models.length ? (
          <div className="model-catalog">
            <h3>{tr('ui.discovered_models')}</h3>
            {measuredStatus.models.map((model) => (
              <div key={model.model_id}>
                <span>{model.display_name}</span>
                <small>{model.availability ?? tr('ui.availability_unknown')}</small>
              </div>
            ))}
          </div>
        ) : (
          <p className="muted">{tr('ui.model_catalog_unavailable')}</p>
        )}
      </section>
    </div>
  )
}
export function NotFound() {
  useTranslation()

  return (
    <StandardLayout title={tr('ui.page_not_found')}>
      <DataState
        kind="unavailable"
        title={tr('ui.page_not_found')}
        description={tr('ui.this_route_is_not_part_of_aryn_studio')}
      />
      <div className="text-center">
        <Button asChild>
          <Link to="/">{tr('ui.back_to_home')}</Link>
        </Button>
      </div>
    </StandardLayout>
  )
}
