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
  return (
    <dl className="home-recap">
      <dt>Objective</dt>
      <dd>{brief.goal || 'To be defined in Builder'}</dd>
      <dt>Artifact</dt>
      <dd>{brief.kind === 'agent' ? 'Agent definition' : 'Workflow graph'}</dd>
      <dt>Expected output</dt>
      <dd>{brief.output || 'To be defined in Builder'}</dd>
      <dt>Integration needs</dt>
      <dd>
        {brief.integration === 'external'
          ? brief.integrationNotes || 'Integration review required'
          : 'No integration requested'}
      </dd>
      <dt>Next step</dt>
      <dd>
        Review the definition. Publishing, approvals, and execution remain separate decisions.
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
            {scratch ? 'START FROM SCRATCH' : 'GUIDED CREATION'} · STEP{' '}
            {step === 'details' ? '1' : '2'} OF 2
          </p>
          <DialogTitle ref={heading} tabIndex={-1}>
            {step === 'details' ? 'Turn your idea into a plan' : 'Review your starting brief'}
          </DialogTitle>
          <DialogDescription>
            {workspace.project?.name} · A starting brief for your review.
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
                  <label htmlFor="brief-goal">Describe the work{!scratch && ' (required)'}</label>
                  <textarea
                    id="brief-goal"
                    required={!scratch}
                    maxLength={1200}
                    value={brief.goal}
                    onChange={(event) => setBrief({ ...brief, goal: event.target.value })}
                    placeholder="What should this accomplish?"
                  />
                </div>
                <fieldset className="home-choices">
                  <legend>What would you like to create?</legend>
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
                          <strong>{kind === 'agent' ? 'Agent definition' : 'Workflow'}</strong>
                          <small>
                            {!canCreate(permissions, kind)
                              ? 'Creation permission required'
                              : kind === 'agent'
                                ? 'One agent, its behavior and output contract'
                                : 'Tasks, handoffs, and human review'}
                          </small>
                        </span>
                      </label>
                    )
                  })}
                </fieldset>
                <div className="home-field">
                  <label htmlFor="brief-output">Expected output</label>
                  <input
                    id="brief-output"
                    maxLength={220}
                    value={brief.output}
                    onChange={(event) => setBrief({ ...brief, output: event.target.value })}
                    placeholder="A summary, a reviewable draft, or a structured result"
                  />
                </div>
                <div className="home-field">
                  <label htmlFor="brief-integration">Does it need another system?</label>
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
                    <option value="none">Not now</option>
                    <option value="external">Yes — integration review required</option>
                  </select>
                  <small>No connections or tool permissions are granted here.</small>
                </div>
                {brief.integration === 'external' && (
                  <div className="home-field">
                    <label htmlFor="brief-integration-notes">Integration requirements</label>
                    <input
                      id="brief-integration-notes"
                      maxLength={220}
                      value={brief.integrationNotes}
                      onChange={(event) =>
                        setBrief({ ...brief, integrationNotes: event.target.value })
                      }
                      placeholder="Which system and what access is needed?"
                    />
                  </div>
                )}
              </>
            ) : (
              <>
                <BriefReview brief={brief} />
                <p className="home-note">
                  This brief is kept only for this navigation session. The builder UI is not
                  available in this release; your brief will be shown at its destination for review.
                </p>
              </>
            )}
          </div>
          <div className="home-drawer-footer">
            {step === 'details' ? (
              <>
                <Button variant="secondary" type="button" onClick={onClose}>
                  Cancel
                </Button>
                <Button type="submit" disabled={!allowed || !valid}>
                  Review brief
                  <ArrowRight size={15} aria-hidden="true" />
                </Button>
              </>
            ) : (
              <>
                <Button variant="secondary" type="button" onClick={() => moveStep('details')}>
                  Edit details
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
                  Open {brief.kind === 'agent' ? 'Agent' : 'Workflow'} Builder
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
