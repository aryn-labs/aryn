import type { ResourceItem } from '@/lib/types/workspace'
import type {
  HomeIncident,
  HomeLifecycle,
  HomeScope,
  HomeSummary,
  HomeWorkflow,
  HomeWorkflowRun,
} from './home-api'

export type CreationKind = 'agent' | 'workflow'
export type CreationBrief = {
  kind: CreationKind
  goal: string
  output: string
  integration: 'none' | 'external'
  integrationNotes: string
}
export type HomeResource = {
  id: string
  name: string
  kind: 'agent' | 'workflow' | 'run' | 'audit' | 'version' | 'incident' | 'workflow-run' | 'bench'
  status?: string | null
  description?: string | null
  createdAt?: string
  revision?: number
  relatedId?: string
}
export type AttentionItem = HomeResource & { reason: string; priority: number; label: string }
export function canCreate(permissions: Record<string, boolean>, kind: CreationKind) {
  return permissions[kind === 'agent' ? 'blueprint:create' : 'version:create'] === true
}
export function resourceItem(item: ResourceItem, kind: HomeResource['kind']): HomeResource {
  return {
    id: item.id,
    name: item.name,
    kind,
    status: item.status,
    description: item.description,
    createdAt: item.created_at,
  }
}
export function workActivity(summary: HomeSummary) {
  return [
    ...summary.latest_runs.map((item) => resourceItem(item, 'run')),
    ...summary.latest_audits
      .filter((item) =>
        /^(?:(?:core|studio|factory)\.)?(agent|blueprint|version|workflow|run|bench|relay|approval|assignment|brief)[.:_]/i.test(
          item.name,
        ),
      )
      .map((item) => resourceItem(item, 'audit')),
  ]
    .sort((a, b) => Date.parse(b.createdAt ?? '') - Date.parse(a.createdAt ?? ''))
    .slice(0, 5)
}
export function attentionItems(
  summary: HomeSummary,
  incidents: HomeIncident[],
  reviews: HomeWorkflowRun[],
  lifecycle?: HomeLifecycle,
): AttentionItem[] {
  const items: AttentionItem[] = []
  for (const problem of summary.attention) {
    if (!['failed', 'outcome_unknown'].includes(problem.code) || problem.count < 1) continue
    const match = /^\/runs\/([^/]+)$/.exec(problem.route)
    if (!match?.[1]) continue
    let id: string
    try {
      id = decodeURIComponent(match[1])
    } catch {
      continue
    }
    const run = summary.latest_runs.find((item) => item.id === id && item.status === problem.code)
    items.push({
      ...(run
        ? resourceItem(run, 'run')
        : { id, name: 'Run requiring review', kind: 'run' as const, status: problem.code }),
      reason: problem.description,
      label: 'Run review',
      priority: problem.code === 'outcome_unknown' ? 95 : 75,
    })
  }
  for (const version of lifecycle?.versions ?? []) {
    if (
      version.regression?.promotion_blocked &&
      version.integrity_valid &&
      !['published', 'deprecated', 'rejected'].includes(version.status) &&
      (lifecycle?.permissions['version:create'] ||
        lifecycle?.permissions['version:approve'] ||
        lifecycle?.permissions['version:publish'])
    )
      items.push({
        id: version.id,
        kind: 'bench',
        name: `Version ${version.version_number}`,
        status: 'Promotion blocked',
        reason: version.regression.reason,
        createdAt: version.regression.compared_at,
        relatedId: version.blueprint_id,
        label:
          version.regression.reason === 'critical_regression'
            ? 'Bench regression'
            : 'Bench gate review',
        priority: 90,
      })
  }
  for (const incident of incidents) {
    const allowed =
      incident.status === 'PROPOSED' || incident.status === 'OUTCOME_UNKNOWN'
        ? summary.permissions['version:approve'] === true
        : summary.permissions['run:create'] === true
    if (
      !allowed ||
      incident.severity === 'low' ||
      !['OPEN', 'INVESTIGATING', 'PROPOSED', 'DEGRADED', 'OUTCOME_UNKNOWN'].includes(
        incident.status,
      )
    )
      continue
    items.push({
      id: incident.id,
      name: incident.title,
      kind: 'incident',
      status: incident.status,
      reason: `Disposable test incident · ${incident.severity} severity · target ${incident.target_id}`,
      createdAt: incident.updated_at,
      relatedId: incident.target_id,
      label: 'Relay incident',
      priority: incident.severity === 'high' ? 85 : 65,
    })
  }
  if (summary.permissions['version:approve']) {
    for (const version of summary.review_candidates) {
      const registry = version.references.registry
      if (
        !version.verified ||
        version.status !== 'draft' ||
        !registry ||
        typeof registry !== 'object' ||
        !('bench_passed' in registry) ||
        registry.bench_passed !== true ||
        items.some((item) => item.id === version.id)
      )
        continue
      items.push({
        ...resourceItem(version, 'version'),
        relatedId:
          typeof version.references.blueprint_id === 'string'
            ? version.references.blueprint_id
            : undefined,
        reason:
          'Verified Bench candidate is ready for human review. Inspect the exact version before any decision.',
        label: 'Approval review',
        priority: 60,
      })
    }
    for (const review of reviews.filter((item) => item.status === 'waiting_review'))
      items.push({
        id: review.id,
        name: 'Workflow output review',
        kind: 'workflow-run',
        status: review.status,
        relatedId: review.workflow_id,
        reason: 'The workflow is waiting for a human decision on its output.',
        label: 'Output review',
        priority: 60,
      })
  }
  return items
    .sort(
      (a, b) =>
        b.priority - a.priority || Date.parse(b.createdAt ?? '') - Date.parse(a.createdAt ?? ''),
    )
    .slice(0, 6)
}
export function workspaceCondition(
  summary: HomeSummary,
  agents: ResourceItem[],
  workflows: HomeWorkflow[],
  incidents: HomeIncident[],
  attention: AttentionItem[],
) {
  if (attention.length) return 'issues' as const
  if (
    agents.length ||
    workflows.length ||
    incidents.length ||
    workActivity(summary).length ||
    summary.review_candidates.length
  )
    return 'active' as const
  const inventories = ['blueprints', 'runs', 'evaluations', 'published', 'assigned']
  const knownEmpty = inventories.every(
    (key) =>
      summary.metrics[key]?.verification === 'recorded_inventory' &&
      summary.metrics[key]?.value === 0,
  )
  if (knownEmpty) return 'new' as const
  if (inventories.some((key) => (summary.metrics[key]?.value ?? 0) > 0)) return 'active' as const
  return 'unavailable' as const
}

// A brief is transient UI input, not a saved domain draft. Only an opaque id enters history.
type Handoff = HomeScope & { userId: string; id: string; brief: CreationBrief; expires: number }
let handoff: Handoff | undefined
export function stageBrief(scope: HomeScope, userId: string, brief: CreationBrief) {
  handoff = {
    ...scope,
    userId,
    brief: { ...brief },
    id: crypto.randomUUID(),
    expires: Date.now() + 30 * 60_000,
  }
  return handoff.id
}
export function readBrief(id: string | undefined, scope: HomeScope, userId: string) {
  if (
    !handoff ||
    handoff.expires < Date.now() ||
    handoff.organizationId !== scope.organizationId ||
    handoff.projectId !== scope.projectId ||
    handoff.userId !== userId
  ) {
    handoff = undefined
    return undefined
  }
  return handoff.id === id ? handoff.brief : undefined
}
