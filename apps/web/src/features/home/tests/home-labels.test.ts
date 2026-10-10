import { describe, expect, it } from 'vitest'
import { activityLabel, statusLabel } from '../lib/home-labels'

describe('customer-facing Home labels', () => {
  it('uses friendly labels for audited events without changing their meaning', () => {
    expect(activityLabel('factory.blueprint.created')).toBe('Agent definition created')
    expect(activityLabel('studio.run.assignment')).toBe('Agent run recorded')
    expect(activityLabel('core.run.failed')).toBe('Run failed')
    expect(activityLabel('core.run.recovered')).toBe('Run recovery recorded')
  })
  it('never invents a successful event when the event type is unknown', () => {
    expect(activityLabel('core.run.future_event')).toBe('Workspace activity recorded')
    expect(activityLabel('<script>attack</script>')).toBe('Workspace activity recorded')
  })
  it('keeps outcome uncertainty and blocked evidence explicit', () => {
    expect(statusLabel('outcome_unknown')).toBe('Outcome needs review')
    expect(statusLabel('baseline_integrity_invalid')).toBe(
      'Baseline evidence could not be verified',
    )
    expect(statusLabel('critical_regression')).toBe('Blocking regression detected')
    expect(statusLabel('NEW_STATUS')).toBe('New status')
  })
})
