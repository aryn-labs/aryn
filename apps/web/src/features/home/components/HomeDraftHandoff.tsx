import { translate as tr } from '@/i18n'
import { useTranslation } from 'react-i18next'
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
  useTranslation()

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
      <p className="home-kicker">{tr('ui.starting_brief_not_saved')}</p>
      <h2 id="brief-handoff-heading">
        {brief.kind === 'agent' ? tr('common.agent') : tr('common.workflow')}{' '}
        {tr('ui.builder_unavailable')}
      </h2>
      <p className="muted">
        {tr(
          'ui.your_starting_brief_is_ready_for_review_this_release_does_not_include_the_builder_editor',
        )}
      </p>
      <BriefReview brief={brief} />
      <p className="home-note">
        {tr(
          'ui.nothing_has_been_created_published_approved_or_run_reloading_clears_this_unsaved_brief',
        )}
      </p>
      <Button variant="secondary" asChild>
        <Link to="/">{tr('ui.back_to_home')}</Link>
      </Button>
    </section>
  )
}
