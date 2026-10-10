import { useWorkspace } from '@/app/providers/WorkspaceProvider'
import { translate as tr } from '@/i18n'
import { useTranslation } from 'react-i18next'
import { useRef } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Dialog, DialogContent, DialogDescription, DialogTitle } from '@/components/ui/dialog'
import { DataState, QueryError } from '@/components/feedback/DataState'
import { formatDate } from '@/lib/utils'
import { ApiError } from '@/lib/api/client'
import {
  assertScope,
  homeRequest,
  incidentSchema,
  lifecycleSchema,
  resourceSchema,
  workflowRunSchema,
  workflowSchema,
  type HomeScope,
} from '../lib/home-api'
import type { HomeResource } from '../lib/home-state'
import { activityLabel, statusLabel } from '../lib/home-labels'

type Detail = {
  name: string
  status?: string | null
  createdAt?: string
  description?: string | null
  verified?: boolean | null
  relatedId?: string
  revision?: number
  reason?: string
  payloadHash?: string
  demo?: boolean
}
async function loadDetail(
  scope: HomeScope,
  item: HomeResource,
  signal: AbortSignal,
): Promise<Detail> {
  const id = encodeURIComponent(item.id)
  if (item.kind === 'workflow') {
    const data = await homeRequest(scope, `workflows/${id}`, workflowSchema, signal)
    assertScope(data, scope)
    if (data.id !== item.id) throw new Error('Workflow identity differs.')
    return { name: data.name, revision: data.revision }
  }
  if (item.kind === 'workflow-run') {
    const data = await homeRequest(scope, `workflow-runs/${id}`, workflowRunSchema, signal)
    assertScope(data, scope)
    if (data.id !== item.id) throw new Error('Workflow run identity differs.')
    return {
      name: 'Workflow output review',
      status: data.status,
      relatedId: data.workflow_id,
      reason: data.error_code ?? undefined,
    }
  }
  if (item.kind === 'incident') {
    const data = await homeRequest(scope, `relay/${id}`, incidentSchema, signal)
    assertScope(data, scope)
    if (data.id !== item.id) throw new Error('Incident identity differs.')
    return {
      name: data.title,
      status: data.status,
      createdAt: data.updated_at,
      relatedId: data.target_id,
      description: `${data.severity} severity`,
      demo: data.demo,
    }
  }
  if (item.kind === 'bench') {
    const data = await homeRequest(
      scope,
      `lifecycle?limit=8&version_id=${id}`,
      lifecycleSchema,
      signal,
    )
    assertScope(data, scope)
    const version = data.versions.find((version) => version.id === item.id)
    if (!version?.regression)
      throw new ApiError(404, 'Bench comparison is unavailable for this version.')
    assertScope(version.regression, scope)
    if (
      version.regression.candidate.version_id !== item.id ||
      version.regression.blueprint_id !== version.blueprint_id
    )
      throw new Error('Bench comparison identity differs.')
    return {
      name: `Version ${version.version_number}`,
      status: version.regression.promotion_blocked ? 'Promotion blocked' : 'Promotion not blocked',
      reason: version.regression.reason,
      relatedId: version.blueprint_id,
      createdAt: version.regression.compared_at,
    }
  }
  const collection = { agent: 'blueprints', run: 'runs', audit: 'audits', version: 'versions' }[
    item.kind
  ]
  const data = await homeRequest(scope, `resources/${collection}/${id}`, resourceSchema, signal)
  assertScope(data, scope)
  if (data.id !== item.id) throw new Error('Resource identity differs.')
  return {
    name:
      item.kind === 'audit'
        ? activityLabel(data.name)
        : item.kind === 'run' && data.name === data.id
          ? 'Run activity'
          : data.name,
    status: data.status,
    createdAt: data.created_at,
    description: data.description,
    verified: data.verified,
    relatedId:
      typeof data.references.blueprint_id === 'string' ? data.references.blueprint_id : undefined,
    payloadHash:
      typeof data.references.payload_hash === 'string' ? data.references.payload_hash : undefined,
  }
}
export function HomeDetailsDrawer({
  item,
  scope,
  projectName,
  onClose,
}: {
  item: HomeResource
  scope: HomeScope
  projectName: string
  onClose: () => void
}) {
  useTranslation()

  const { context } = useWorkspace()
  const returnFocus = useRef<HTMLElement | null>(null)
  const query = useQuery({
    queryKey: [
      'home',
      context?.user.id,
      scope.organizationId,
      scope.projectId,
      'detail',
      item.kind,
      item.id,
    ],
    queryFn: ({ signal }) => loadDetail(scope, item, signal),
    staleTime: 0,
  })
  const detail = !query.isError ? query.data : undefined
  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open) onClose()
      }}
    >
      <DialogContent
        className="home-drawer"
        onOpenAutoFocus={() => {
          returnFocus.current =
            document.activeElement instanceof HTMLElement ? document.activeElement : null
        }}
        onCloseAutoFocus={(event) => {
          event.preventDefault()
          if (returnFocus.current?.isConnected) returnFocus.current.focus()
        }}
      >
        <div className="home-drawer-heading">
          <p className="home-kicker">{item.kind.replaceAll('-', ' ')}</p>
          <DialogTitle>{tr('ui.resource_details')}</DialogTitle>
          <DialogDescription>
            {projectName} {tr('ui.details_reported_by_aryn_for_the_selected_resource_177')}
          </DialogDescription>
        </div>
        <div className="home-drawer-scroll">
          {query.isPending ? (
            <DataState kind="loading" title={tr('ui.loading_resource')} />
          ) : query.error ? (
            query.error instanceof ApiError && query.error.status === 404 ? (
              <DataState
                kind="unavailable"
                description={query.error.message}
                retry={() => void query.refetch()}
              />
            ) : (
              <QueryError error={query.error} retry={() => void query.refetch()} />
            )
          ) : (
            detail && (
              <>
                <h3 className="home-detail-name">{detail.name}</h3>
                <dl className="home-recap">
                  <dt>{tr('ui.resource_id')}</dt>
                  <dd className="mono">{item.id}</dd>
                  <dt>{tr('ui.project')}</dt>
                  <dd>{projectName}</dd>
                  {detail.status && (
                    <>
                      <dt>{tr('ui.status')}</dt>
                      <dd>{statusLabel(detail.status)}</dd>
                    </>
                  )}
                  {detail.revision && (
                    <>
                      <dt>{tr('ui.revision')}</dt>
                      <dd>{detail.revision}</dd>
                    </>
                  )}
                  {detail.createdAt && (
                    <>
                      <dt>{tr('ui.recorded')}</dt>
                      <dd>{formatDate(detail.createdAt)}</dd>
                    </>
                  )}
                  {detail.description && (
                    <>
                      <dt>{tr('ui.description')}</dt>
                      <dd>{detail.description}</dd>
                    </>
                  )}
                  {detail.relatedId && (
                    <>
                      <dt>{tr('ui.related_resource')}</dt>
                      <dd className="mono">{detail.relatedId}</dd>
                    </>
                  )}
                  {detail.reason && (
                    <>
                      <dt>{tr('ui.reason')}</dt>
                      <dd>{statusLabel(detail.reason)}</dd>
                    </>
                  )}
                  {detail.payloadHash && (
                    <>
                      <dt>{tr('ui.payload_hash')}</dt>
                      <dd className="mono">{detail.payloadHash}</dd>
                    </>
                  )}
                  {detail.verified != null && (
                    <>
                      <dt>{tr('ui.verification')}</dt>
                      <dd>{detail.verified ? tr('ui.verified_by_backend') : 'Unverified'}</dd>
                    </>
                  )}
                </dl>
                {detail.demo && (
                  <p className="home-note">
                    {tr(
                      'ui.this_is_a_recorded_disposable_test_incident_it_does_not_report_production_infrastructure_health',
                    )}
                  </p>
                )}
                {['version', 'workflow-run', 'incident', 'bench', 'run'].includes(item.kind) && (
                  <p className="home-note">
                    {tr(
                      'ui.review_the_recorded_evidence_decision_and_execution_tools_are_unavailable_in_this_home_release',
                    )}
                  </p>
                )}
              </>
            )
          )}
        </div>
      </DialogContent>
    </Dialog>
  )
}
