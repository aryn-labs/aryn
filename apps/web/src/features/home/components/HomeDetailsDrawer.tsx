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
    name: item.kind === 'audit' ? activityLabel(data.name) : data.name,
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
  const returnFocus = useRef<HTMLElement | null>(null)
  const query = useQuery({
    queryKey: ['home', scope.organizationId, scope.projectId, 'detail', item.kind, item.id],
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
          <DialogTitle>Resource details</DialogTitle>
          <DialogDescription>
            {projectName} · Details reported by ARYN for the selected resource.
          </DialogDescription>
        </div>
        <div className="home-drawer-scroll">
          {query.isPending ? (
            <DataState kind="loading" title="Loading resource" />
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
                  <dt>Resource ID</dt>
                  <dd className="mono">{item.id}</dd>
                  <dt>Project</dt>
                  <dd>{projectName}</dd>
                  {detail.status && (
                    <>
                      <dt>Status</dt>
                      <dd>{statusLabel(detail.status)}</dd>
                    </>
                  )}
                  {detail.revision && (
                    <>
                      <dt>Revision</dt>
                      <dd>{detail.revision}</dd>
                    </>
                  )}
                  {detail.createdAt && (
                    <>
                      <dt>Recorded</dt>
                      <dd>{formatDate(detail.createdAt)}</dd>
                    </>
                  )}
                  {detail.description && (
                    <>
                      <dt>Description</dt>
                      <dd>{detail.description}</dd>
                    </>
                  )}
                  {detail.relatedId && (
                    <>
                      <dt>Related resource</dt>
                      <dd className="mono">{detail.relatedId}</dd>
                    </>
                  )}
                  {detail.reason && (
                    <>
                      <dt>Reason</dt>
                      <dd>{statusLabel(detail.reason)}</dd>
                    </>
                  )}
                  {detail.payloadHash && (
                    <>
                      <dt>Payload hash</dt>
                      <dd className="mono">{detail.payloadHash}</dd>
                    </>
                  )}
                  {detail.verified != null && (
                    <>
                      <dt>Verification</dt>
                      <dd>{detail.verified ? 'Verified by backend' : 'Unverified'}</dd>
                    </>
                  )}
                </dl>
                {detail.demo && (
                  <p className="home-note">
                    This is a recorded disposable test incident. It does not report production
                    infrastructure health.
                  </p>
                )}
                {['version', 'workflow-run', 'incident', 'bench', 'run'].includes(item.kind) && (
                  <p className="home-note">
                    Review the recorded evidence. Decision and execution tools are unavailable in
                    this Home release.
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
