// Imported only by Vitest / Playwright. These records never enter the product bundle.
import { contextFixture, runFixture, summaryFixture } from '../../../test/fixtures'
import type { HomeSummary } from '../lib/home-api'
export type HomeScenario = 'new' | 'active' | 'issues'
export function homeFixture(scenario: HomeScenario, projectId = 'project-one', writable = true) {
  const base = { organization_id: 'org-test', project_id: projectId }
  const agents =
    scenario === 'new'
      ? []
      : [
          {
            ...base,
            id: 'agent-one',
            name: 'Research assistant',
            description: 'Review sources and prepare a cited brief.',
            created_at: '2026-10-09T10:00:00Z',
            references: {},
          },
        ]
  const workflows =
    scenario === 'new'
      ? []
      : [{ ...base, id: 'workflow-one', name: 'Research review', revision: 3 }]
  const summary: HomeSummary = {
    ...summaryFixture(projectId, scenario !== 'new'),
    permissions: {
      'blueprint:create': writable,
      'version:create': writable,
      'version:approve': writable,
      'version:publish': writable,
      'run:create': writable,
    },
    attention: [],
  }
  summary.metrics.blueprints!.value = agents.length
  if (scenario === 'issues') {
    summary.latest_runs = [{ ...runFixture, ...base, status: 'failed' }]
    summary.attention = [
      {
        code: 'failed',
        count: 1,
        description: 'Run failed; review the captured error and evidence.',
        route: '/runs/run-test',
      },
    ]
    summary.review_candidates = [
      {
        ...runFixture,
        ...base,
        id: 'version-review',
        name: '1.1.0',
        status: 'draft',
        references: {
          blueprint_id: 'agent-one',
          registry: { bench_passed: true },
          payload_hash: 'a'.repeat(64),
        },
      },
    ]
  }
  const incidents =
    scenario === 'issues'
      ? [
          {
            ...base,
            id: 'incident-one',
            title: 'Disposable service needs review',
            target_id: 'fixture-one',
            status: 'DEGRADED' as const,
            severity: 'high' as const,
            demo: true as const,
            created_at: '2026-10-09T10:00:00Z',
            updated_at: '2026-10-09T12:00:00Z',
          },
        ]
      : []
  const lifecycle = {
    ...base,
    permissions: summary.permissions,
    versions:
      scenario === 'issues'
        ? [
            {
              id: 'version-blocked',
              blueprint_id: 'agent-one',
              version_number: '1.0.1',
              status: 'draft',
              created_at: '2026-10-09T10:00:00Z',
              integrity_valid: true,
              regression: {
                ...base,
                comparison_id: 'comparison-one',
                blueprint_id: 'agent-one',
                candidate: { version_id: 'version-blocked', evaluation_id: 'evaluation-one' },
                promotion_blocked: true,
                reason: 'critical_regression',
                compared_at: '2026-10-09T12:00:00Z',
              },
            },
          ]
        : [],
  }
  const reviews =
    scenario === 'issues'
      ? [
          {
            ...base,
            id: 'workflow-review',
            workflow_id: 'workflow-one',
            version_id: 'workflow-version',
            status: 'waiting_review' as const,
          },
        ]
      : []
  return { context: contextFixture, summary, agents, workflows, incidents, lifecycle, reviews }
}
