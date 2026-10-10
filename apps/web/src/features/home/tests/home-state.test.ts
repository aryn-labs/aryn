import { describe, expect, it } from 'vitest'
import {
  attentionItems,
  canCreate,
  readBrief,
  stageBrief,
  workspaceCondition,
} from '../lib/home-state'
import { assertScope, homeSummarySchema } from '../lib/home-api'
import { homeFixture } from './fixtures'
describe('Home API-derived state', () => {
  it.each(['new', 'active', 'issues'] as const)(
    'derives %s from actual inventory contracts',
    (scenario) => {
      const data = homeFixture(scenario)
      const attention = attentionItems(data.summary, data.incidents, data.reviews, data.lifecycle)
      expect(
        workspaceCondition(data.summary, data.agents, data.workflows, data.incidents, attention),
      ).toBe(scenario)
    },
  )
  it('does not confuse unavailable or incomplete metrics with a new workspace', () => {
    const data = homeFixture('new')
    data.summary.metrics.blueprints!.value = null
    expect(workspaceCondition(data.summary, [], [], [], [])).toBe('unavailable')
    expect(homeSummarySchema.safeParse({ ...data.summary, attention: undefined }).success).toBe(
      false,
    )
  })
  it('prioritizes current issues without exposing unpermitted decisions or informational incidents', () => {
    const data = homeFixture('issues')
    expect(
      attentionItems(data.summary, data.incidents, data.reviews, data.lifecycle).map(
        (item) => item.kind,
      ),
    ).toEqual(['bench', 'incident', 'run', 'version', 'workflow-run'])
    data.summary.permissions['version:approve'] = false
    data.summary.permissions['version:create'] = false
    data.summary.permissions['version:publish'] = false
    data.summary.permissions['run:create'] = false
    expect(
      attentionItems(
        data.summary,
        [{ ...data.incidents[0]!, severity: 'low' }],
        data.reviews,
        data.lifecycle,
      ).map((item) => item.kind),
    ).toEqual(['run'])
  })
  it('rejects unverified review candidates and closed / running incidents', () => {
    const data = homeFixture('issues')
    data.summary.review_candidates[0]!.verified = false
    const incidents = [
      { ...data.incidents[0]!, status: 'CLOSED' as const },
      { ...data.incidents[0]!, status: 'EXECUTING' as const },
    ]
    expect(attentionItems(data.summary, incidents, [], undefined).map((item) => item.kind)).toEqual(
      ['run'],
    )
    data.summary.attention[0]!.route = 'https://external.invalid/runs/run-test'
    expect(attentionItems(data.summary, [], [], undefined)).toEqual([])
  })
  it('reads effective permissions without deriving authority from role labels', () => {
    expect(canCreate({}, 'agent')).toBe(false)
    expect(canCreate({ 'blueprint:create': false, 'version:create': true }, 'agent')).toBe(false)
    expect(canCreate({ 'version:create': true }, 'workflow')).toBe(true)
  })
  it('rejects foreign organization and project envelopes', () => {
    const scope = { organizationId: 'org-test', projectId: 'project-one' }
    expect(() =>
      assertScope({ organization_id: 'foreign', project_id: 'project-one' }, scope),
    ).toThrow('different workspace')
    expect(() =>
      assertScope({ organization_id: 'org-test', project_id: 'foreign' }, scope),
    ).toThrow('different workspace')
  })
  it('keeps a brief transient and bound to organization, project, and user', () => {
    const scope = { organizationId: 'org-test', projectId: 'project-one' }
    const brief = {
      kind: 'agent' as const,
      goal: 'Review sources',
      output: 'Cited brief',
      integration: 'none' as const,
      integrationNotes: '',
    }
    const id = stageBrief(scope, 'user-one', brief)
    expect(readBrief(id, scope, 'user-one')).toEqual(brief)
    expect(readBrief(id, scope, 'user-two')).toBeUndefined()
    expect(readBrief(id, scope, 'user-one')).toBeUndefined()
    expect(localStorage.getItem('home-brief')).toBeNull()
  })
})
