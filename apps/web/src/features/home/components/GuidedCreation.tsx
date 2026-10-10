import { translate as tr } from '@/i18n'
import { useTranslation } from 'react-i18next'
import { useRef, useState } from 'react'
import { useNavigate } from '@tanstack/react-router'
import { ArrowRight, Bot, Workflow } from 'lucide-react'
import { Dialog, DialogContent, DialogDescription, DialogTitle } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { useWorkspace } from '@/app/providers/WorkspaceProvider'
import { canCreate, stageBrief, type CreationBrief, type CreationKind } from '../lib/home-state'

declare module '@tanstack/history' {
  interface HistoryState {
    homeBriefId?: string
  }
}
export function BriefReview({ brief }: { brief: CreationBrief }) {
  useTranslation()

  return (
    <dl className="home-recap">
      <dt>{tr('ui.objective')}</dt>
      <dd>{brief.goal || tr('ui.to_be_defined_in_builder')}</dd>
      <dt>{tr('ui.artifact')}</dt>
      <dd>{brief.kind === 'agent' ? tr('ui.agent_definition') : tr('ui.workflow_graph')}</dd>
      <dt>{tr('ui.expected_output')}</dt>
      <dd>{brief.output || tr('ui.to_be_defined_in_builder')}</dd>
      <dt>{tr('ui.integration_needs')}</dt>
      <dd>
        {brief.integration === 'external'
          ? brief.integrationNotes || tr('ui.integration_review_required')
          : tr('ui.no_integration_requested')}
      </dd>
      <dt>{tr('ui.next_step')}</dt>
      <dd>
        {tr(
          'ui.review_the_definition_publishing_approvals_and_execution_remain_separate_decisions',
        )}
      </dd>
    </dl>
  )
}
export function GuidedCreation({
  initialKind,
  goal,
  scratch,
  permissions,
  onClose,
}: {
  initialKind?: CreationKind
  goal: string
  scratch: boolean
  permissions: Record<string, boolean>
  onClose: () => void
}) {
  useTranslation()

  const workspace = useWorkspace()
  const navigate = useNavigate()
  const [brief, setBrief] = useState<CreationBrief>({
    kind: initialKind ?? (canCreate(permissions, 'agent') ? 'agent' : 'workflow'),
    goal,
    output: '',
    integration: 'none',
    integrationNotes: '',
  })
  const [step, setStep] = useState<'details' | 'review'>('details')
  const returnFocus = useRef<HTMLElement | null>(null)
  const heading = useRef<HTMLHeadingElement | null>(null)
  function moveStep(value: 'details' | 'review') {
    setStep(value)
    requestAnimationFrame(() => heading.current?.focus())
  }
  const allowed = !!workspace.context && !!workspace.project && canCreate(permissions, brief.kind)
  const valid = scratch || !!brief.goal.trim()
  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open) onClose()
      }}
    >
      <DialogContent
        className="home-drawer"
        onOpenAutoFocus={(event) => {
          returnFocus.current =
            document.activeElement instanceof HTMLElement ? document.activeElement : null
          event.preventDefault()
          requestAnimationFrame(() => document.getElementById('brief-goal')?.focus())
        }}
        onCloseAutoFocus={(event) => {
          event.preventDefault()
          if (returnFocus.current?.isConnected) returnFocus.current.focus()
        }}
      >
        <div className="home-drawer-heading">
          <p className="home-kicker">
            {scratch ? tr('ui.start_from_scratch') : tr('ui.guided_creation')} {tr('ui.step')}{' '}
            {step === 'details' ? '1' : '2'} {tr('ui.of_2')}
          </p>
          <DialogTitle ref={heading} tabIndex={-1}>
            {step === 'details'
              ? tr('ui.turn_your_idea_into_a_plan')
              : tr('ui.review_your_starting_brief')}
          </DialogTitle>
          <DialogDescription>
            {workspace.project?.name} {tr('ui.a_starting_brief_for_your_review')}
          </DialogDescription>
        </div>
        <form
          className="home-drawer-form"
          onSubmit={(event) => {
            event.preventDefault()
            if (valid && allowed) moveStep('review')
          }}
        >
          <div className="home-drawer-scroll">
            {step === 'details' ? (
              <>
                <div className="home-field">
                  <label htmlFor="brief-goal">
                    {tr('ui.describe_the_work')}
                    {!scratch && tr('ui.required_suffix')}
                  </label>
                  <textarea
                    id="brief-goal"
                    required={!scratch}
                    maxLength={1200}
                    value={brief.goal}
                    onChange={(event) => setBrief({ ...brief, goal: event.target.value })}
                    placeholder={tr('ui.what_should_this_accomplish')}
                  />
                </div>
                <fieldset className="home-choices">
                  <legend>{tr('ui.what_would_you_like_to_create')}</legend>
                  {(['agent', 'workflow'] as const).map((kind) => {
                    const Icon = kind === 'agent' ? Bot : Workflow
                    return (
                      <label key={kind} className="home-choice">
                        <input
                          type="radio"
                          name="creation-kind"
                          value={kind}
                          checked={brief.kind === kind}
                          disabled={!canCreate(permissions, kind)}
                          onChange={() => setBrief({ ...brief, kind })}
                        />
                        <Icon size={19} aria-hidden="true" />
                        <span>
                          <strong>
                            {kind === 'agent' ? tr('ui.agent_definition') : tr('common.workflow')}
                          </strong>
                          <small>
                            {!canCreate(permissions, kind)
                              ? tr('ui.creation_permission_required')
                              : kind === 'agent'
                                ? tr('ui.one_agent_its_behavior_and_output_contract')
                                : tr('ui.tasks_handoffs_and_human_review')}
                          </small>
                        </span>
                      </label>
                    )
                  })}
                </fieldset>
                <div className="home-field">
                  <label htmlFor="brief-output">{tr('ui.expected_output')}</label>
                  <input
                    id="brief-output"
                    maxLength={220}
                    value={brief.output}
                    onChange={(event) => setBrief({ ...brief, output: event.target.value })}
                    placeholder={tr('ui.a_summary_a_reviewable_draft_or_a_structured_result')}
                  />
                </div>
                <div className="home-field">
                  <label htmlFor="brief-integration">{tr('ui.does_it_need_another_system')}</label>
                  <select
                    id="brief-integration"
                    value={brief.integration}
                    onChange={(event) =>
                      setBrief({
                        ...brief,
                        integration: event.target.value === 'external' ? 'external' : 'none',
                      })
                    }
                  >
                    <option value="none">{tr('ui.not_now')}</option>
                    <option value="external">{tr('ui.yes_integration_review_required')}</option>
                  </select>
                  <small>{tr('ui.no_connections_or_tool_permissions_are_granted_here')}</small>
                </div>
                {brief.integration === 'external' && (
                  <div className="home-field">
                    <label htmlFor="brief-integration-notes">
                      {tr('ui.integration_requirements')}
                    </label>
                    <input
                      id="brief-integration-notes"
                      maxLength={220}
                      value={brief.integrationNotes}
                      onChange={(event) =>
                        setBrief({ ...brief, integrationNotes: event.target.value })
                      }
                      placeholder={tr('ui.which_system_and_what_access_is_needed')}
                    />
                  </div>
                )}
              </>
            ) : (
              <>
                <BriefReview brief={brief} />
                <p className="home-note">
                  {tr(
                    'ui.this_brief_is_kept_only_for_this_navigation_session_the_builder_ui_is_not_available_in_this_release_your_brief_will_be_shown_at_its_destination_for_review',
                  )}
                </p>
              </>
            )}
          </div>
          <div className="home-drawer-footer">
            {step === 'details' ? (
              <>
                <Button variant="secondary" type="button" onClick={onClose}>
                  {tr('ui.cancel')}
                </Button>
                <Button type="submit" disabled={!allowed || !valid}>
                  {tr('ui.review_brief')}
                  <ArrowRight size={15} aria-hidden="true" />
                </Button>
              </>
            ) : (
              <>
                <Button variant="secondary" type="button" onClick={() => moveStep('details')}>
                  {tr('ui.edit_details')}
                </Button>
                <Button
                  type="button"
                  disabled={!allowed}
                  onClick={() => {
                    if (!workspace.context || !workspace.project || !allowed) return
                    const id = stageBrief(
                      {
                        organizationId: workspace.context.organization.id,
                        projectId: workspace.project.id,
                      },
                      workspace.context.user.id,
                      {
                        ...brief,
                        goal: brief.goal.trim(),
                        output: brief.output.trim(),
                        integrationNotes: brief.integrationNotes.trim(),
                      },
                    )
                    onClose()
                    void navigate({
                      to: brief.kind === 'agent' ? '/agents' : '/workflows',
                      state: { homeBriefId: id },
                    })
                  }}
                >
                  {tr('ui.open_builder', {
                    kind: brief.kind === 'agent' ? tr('common.agent') : tr('common.workflow'),
                  })}
                  <ArrowRight size={15} aria-hidden="true" />
                </Button>
              </>
            )}
          </div>
        </form>
      </DialogContent>
    </Dialog>
  )
}
