import { Link, useLocation } from '@tanstack/react-router'
import { useWorkspace } from '@/app/providers/WorkspaceProvider'
import { Button } from '@/components/ui/button'
import { readBrief } from '../lib/home-state'
import { BriefReview } from './GuidedCreation'
export function HomeDraftHandoff({
  title,
  children,
}: {
  title: string
  children: React.ReactNode
}) {
  const { context, project } = useWorkspace()
  const location = useLocation()
  const brief =
    context && project
      ? readBrief(
          location.state.homeBriefId,
          { organizationId: context.organization.id, projectId: project.id },
          context.user.id,
        )
      : undefined
  if (!brief || (brief.kind === 'agent' ? 'Agents' : 'Workflows') !== title) return children
  return (
    <section className="home-handoff" aria-labelledby="brief-handoff-heading">
      <p className="home-kicker">STARTING BRIEF · NOT SAVED</p>
      <h2 id="brief-handoff-heading">
        {brief.kind === 'agent' ? 'Agent' : 'Workflow'} Builder unavailable
      </h2>
      <p className="muted">
        Your starting brief is ready for review. This release does not include the builder editor.
      </p>
      <BriefReview brief={brief} />
      <p className="home-note">
        Nothing has been created, published, approved, or run. Reloading clears this unsaved brief.
      </p>
      <Button variant="secondary" asChild>
        <Link to="/">Back to Home</Link>
      </Button>
    </section>
  )
}
