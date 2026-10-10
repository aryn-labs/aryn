// Presentation labels for audited event types; resource IDs and backend status remain intact.
const events: Record<string, string> = {
  'factory.blueprint.created': 'Agent definition created',
  'factory.version.created': 'Agent version created',
  'factory.version.approved': 'Agent version approved',
  'factory.version.published': 'Agent version published',
  'factory.agent.assigned': 'Agent assigned',
  'factory.assignment.rollback_denied': 'Assignment rollback blocked',
  'bench.evaluation.completed': 'Bench evaluation completed',
  'core.approval.granted': 'Approval recorded',
  'studio.run.assignment': 'Agent run recorded',
  'core.run.initiated': 'Run started',
  'core.run.queued': 'Run queued',
  'core.run.completed': 'Run completed',
  'core.run.failed': 'Run failed',
  'core.run.cancelled': 'Run cancelled',
  'core.run.denied': 'Run request blocked',
  'core.run.budget_exceeded': 'Run budget exceeded',
  'core.run.outcome_unknown': 'Run outcome needs review',
  'core.run.idempotent_cached': 'Previous run result retrieved',
  'core.run.cancellation.requested': 'Run stop requested',
  'core.run.cancellation.unavailable': 'Run stop unavailable',
  'core.run.recovered': 'Run recovery recorded',
}
export function activityLabel(event: string) {
  return events[event] ?? 'Workspace activity recorded'
}
export function statusLabel(status: string) {
  const labels: Record<string, string> = {
    outcome_unknown: 'Outcome needs review',
    waiting_review: 'Awaiting review',
    baseline_integrity_invalid: 'Baseline evidence could not be verified',
    critical_regression: 'Blocking regression detected',
  }
  if (labels[status]) return labels[status]
  const text = status.replaceAll('_', ' ').toLowerCase()
  return text.charAt(0).toUpperCase() + text.slice(1)
}
