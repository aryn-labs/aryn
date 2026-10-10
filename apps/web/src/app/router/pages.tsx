import { Link } from '@tanstack/react-router'
import { StandardLayout } from '@/app/shell/MainWorkspace'
import { DataState, QueryError } from '@/components/feedback/DataState'
import { Button } from '@/components/ui/button'
import { useWorkspace } from '@/app/providers/WorkspaceProvider'
import { useWorkspaceStatus } from '@/hooks/use-workspace-queries'
import { Box, Cloud, Monitor } from 'lucide-react'
import { HomeDraftHandoff } from '@/features/home/components/HomeDraftHandoff'
export function FeatureScaffold({ title }: { title: string }) {
  const { project } = useWorkspace()
  return (
    <StandardLayout title={title}>
      <section className="feature-scaffold">
        <p className="eyebrow">ARYN Workspace</p>
        <h1>{title}</h1>
        <p className="muted">{project?.name ?? 'No project selected'}</p>
        {title === 'Settings' ? (
          <WorkspaceRuntime />
        ) : (
          <HomeDraftHandoff title={title}>
            <div className="scaffold-card">
              <DataState
                kind="unavailable"
                title={`${title} workspace is not available yet`}
                description="This release provides the Studio shell and Home. Feature tools will be added to this workspace in a future release."
              />
              <Button variant="secondary" asChild>
                <Link to="/">Back to Home</Link>
              </Button>
            </div>
          </HomeDraftHandoff>
        )}
      </section>
    </StandardLayout>
  )
}
function WorkspaceRuntime() {
  const { context, project, loading, error, retry } = useWorkspace()
  const status = useWorkspaceStatus()
  const measuredStatus = context && !status.isError ? status.data : undefined
  if (error) return <QueryError error={error} retry={retry} />
  if (loading) return <DataState kind="loading" title="Loading workspace" />
  if (!context)
    return (
      <DataState kind="unavailable" description="Sign in to view workspace runtime information." />
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
          Environment
        </h2>
        <p className="muted">Runtime information for {context.organization.name}.</p>
        <dl className="detail-list">
          <dt>Environment</dt>
          <dd>{environment}</dd>
          <dt>Mode</dt>
          <dd>{context.mode}</dd>
        </dl>
        {status.isLoading ? (
          <DataState kind="loading" title="Checking runtime" />
        ) : status.error ? (
          <QueryError error={status.error} retry={() => void status.refetch()} />
        ) : measuredStatus ? (
          <div className="info-card">
            <strong>{measuredStatus.runtime.ready ? 'Runtime ready' : 'Runtime not ready'}</strong>
            <p>{measuredStatus.runtime.message}</p>
            <small>
              Connection: {measuredStatus.runtime.connected ? 'Connected' : 'Disconnected'}
            </small>
          </div>
        ) : (
          <DataState kind="unavailable" description="Runtime information is unavailable." />
        )}
      </section>
      <section className="runtime-card" aria-labelledby="models-heading">
        <h2 id="models-heading">
          <Box size={19} aria-hidden="true" />
          Models
        </h2>
        <p className="muted">{project?.name ?? 'No project selected'}</p>
        <DataState
          kind={project ? 'unavailable' : 'empty'}
          title={project ? 'Active model unavailable' : 'No project selected'}
          description={
            project
              ? 'No active or default model has been reported for this project.'
              : 'No project is available to this account.'
          }
        />
        {status.isLoading ? (
          <p role="status">Loading model catalog…</p>
        ) : status.error ? (
          <QueryError error={status.error} retry={() => void status.refetch()} />
        ) : measuredStatus?.models.length ? (
          <div className="model-catalog">
            <h3>Discovered models</h3>
            {measuredStatus.models.map((model) => (
              <div key={model.model_id}>
                <span>{model.display_name}</span>
                <small>{model.availability ?? 'Availability unknown'}</small>
              </div>
            ))}
          </div>
        ) : (
          <p className="muted">Model catalog unavailable.</p>
        )}
      </section>
    </div>
  )
}
export function NotFound() {
  return (
    <StandardLayout title="Page not found">
      <DataState
        kind="unavailable"
        title="Page not found"
        description="This route is not part of ARYN Studio."
      />
      <div className="text-center">
        <Button asChild>
          <Link to="/">Back to Home</Link>
        </Button>
      </div>
    </StandardLayout>
  )
}
