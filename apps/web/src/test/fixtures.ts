// Explicitly isolated test contracts; never imported by the application.
export const contextFixture = {
  organization: { id: 'org-test', name: 'Test Studio' },
  projects: [
    { id: 'project-one', name: 'First Project' },
    { id: 'project-two', name: 'Second Project' },
  ],
  user: { id: 'user-test', name: 'Test User', role: 'viewer' },
  mode: 'isolated-test',
}
export const runFixture = {
  id: 'run-test',
  name: 'Recorded test run',
  organization_id: 'org-test',
  project_id: 'project-one',
  created_at: '2026-10-09T12:00:00Z',
  status: 'completed',
  verified: true,
  references: {},
}
export function summaryFixture(projectId = 'project-one', withActivity = false) {
  return {
    organization_id: 'org-test',
    project_id: projectId,
    refreshed_at: '2026-10-09T12:00:00Z',
    metrics: Object.fromEntries(
      [
        'blueprints',
        'assigned',
        'published',
        'runs',
        'audits',
        'evaluations',
        'review_candidates',
      ].map((key) => [
        key,
        {
          value: key === 'runs' && withActivity ? 1 : 0,
          definition: 'Isolated test inventory',
          source: 'Test fixture',
          verification: 'recorded_inventory' as const,
        },
      ]),
    ),
    permissions: { 'blueprint:create': false },
    attention: [],
    latest_runs: withActivity ? [{ ...runFixture, project_id: projectId }] : [],
    latest_audits: [],
    review_candidates: [],
  }
}
export const statusFixture = {
  organization_id: 'org-test',
  models: [],
  runtime: { connected: false, ready: false, message: 'Runtime unavailable in isolated test.' },
}
