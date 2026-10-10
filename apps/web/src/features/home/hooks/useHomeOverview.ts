import { useQuery } from '@tanstack/react-query'
import { useWorkspace } from '@/app/providers/WorkspaceProvider'
import {
  getHomeAgents,
  getHomeInventory,
  getHomeLifecycle,
  getHomeSummary,
  incidentSchema,
  workflowRunSchema,
  workflowSchema,
} from '../lib/home-api'
import { attentionItems, workActivity, workspaceCondition } from '../lib/home-state'
import { chatKey, chatPath, historySchema, scoped } from '@/features/chat/lib/chat-api'
import { request } from '@/lib/api/client'

export function useHomeOverview() {
  const workspace = useWorkspace()
  const scope = {
    organizationId: workspace.context?.organization.id ?? '',
    projectId: workspace.project?.id ?? '',
  }
  const enabled = !!workspace.context && !!workspace.project
  const key = [workspace.context?.user.id, scope.organizationId, scope.projectId]
  const chatScope = {
    user: workspace.context?.user.id ?? '',
    organization: scope.organizationId,
    project: scope.projectId,
  }
  const conversations = useQuery({
    queryKey: [...chatKey(chatScope), 'recent'],
    queryFn: async ({ signal }) =>
      scoped(
        await request(chatPath(chatScope) + '/conversations', historySchema, { signal }),
        chatScope,
      ),
    enabled,
    retry: false,
  })
  const summary = useQuery({
    queryKey: ['summary', ...key, 'home'],
    enabled,
    queryFn: ({ signal }) => getHomeSummary(scope, signal),
  })
  const agents = useQuery({
    queryKey: ['home', ...key, 'agents'],
    enabled,
    queryFn: ({ signal }) => getHomeAgents(scope, signal),
  })
  const workflows = useQuery({
    queryKey: ['home', ...key, 'workflows'],
    enabled,
    queryFn: ({ signal }) => getHomeInventory(scope, 'workflows?limit=4', workflowSchema, signal),
  })
  const incidents = useQuery({
    queryKey: ['home', ...key, 'incidents'],
    enabled,
    queryFn: ({ signal }) => getHomeInventory(scope, 'relay?limit=8', incidentSchema, signal),
  })
  const canReview =
    enabled && !summary.isError && summary.data?.permissions['version:approve'] === true
  const reviewQueue = useQuery({
    queryKey: ['home', ...key, 'reviews'],
    enabled: canReview,
    queryFn: ({ signal }) =>
      getHomeInventory(scope, 'review-queue?limit=6', workflowRunSchema, signal),
  })
  const checkBench =
    enabled &&
    !summary.isError &&
    (summary.data?.metrics.blueprints?.value ?? 0) > 0 &&
    ['version:create', 'version:approve', 'version:publish'].some(
      (permission) => summary.data?.permissions[permission] === true,
    )
  const lifecycle = useQuery({
    queryKey: ['home', ...key, 'bench'],
    enabled: checkBench,
    queryFn: ({ signal }) => getHomeLifecycle(scope, signal),
  })
  const queries = [
    summary,
    agents,
    workflows,
    incidents,
    conversations,
    ...(canReview ? [reviewQueue] : []),
    ...(checkBench ? [lifecycle] : []),
  ]
  const error = workspace.error ?? [summary, agents].find((query) => query.isError)?.error ?? null
  const loading = workspace.loading || (enabled && queries.some((query) => query.isPending))
  const data =
    !error && !loading && enabled && summary.data && agents.data
      ? {
          summary: summary.data,
          agents: agents.data,
          workflows: workflows.isError ? [] : (workflows.data ?? []),
          incidents: incidents.isError ? [] : (incidents.data ?? []),
          attention: attentionItems(
            summary.data,
            incidents.isError ? [] : (incidents.data ?? []),
            reviewQueue.isError ? [] : (reviewQueue.data ?? []),
            lifecycle.isError ? undefined : lifecycle.data,
          ),
          activity: workActivity(summary.data),
          conversations: conversations.isError ? [] : (conversations.data?.items ?? []),
        }
      : undefined
  const measuredCondition = data
    ? data.attention.length
      ? 'issues'
      : data.conversations.length
        ? 'active'
        : workspaceCondition(
            data.summary,
            data.agents,
            data.workflows,
            data.incidents,
            data.attention,
          )
    : undefined
  const incomplete = queries.some((query) => query.isError)
  const condition = measuredCondition === 'new' && incomplete ? 'unavailable' : measuredCondition
  const services = [
    { label: 'Workflow definitions', query: workflows },
    { label: 'Relay incidents', query: incidents },
    { label: 'Conversation history', query: conversations },
    ...(canReview ? [{ label: 'Workflow output reviews', query: reviewQueue }] : []),
    ...(checkBench ? [{ label: 'Bench comparisons', query: lifecycle }] : []),
  ]
    .filter(({ query }) => query.isError)
    .map(({ label, query }) => ({ label, error: query.error!, retry: () => void query.refetch() }))
  return {
    workspace,
    scope,
    data,
    condition,
    loading,
    error,
    services,
    workflowsError: workflows.error,
    retry: () => {
      if (workspace.error) workspace.retry()
      else queries.filter((query) => query.isError).forEach((query) => void query.refetch())
    },
  }
}
