import { useEffect, useRef, useState } from 'react'
import { Link } from '@tanstack/react-router'
import { useInfiniteQuery, useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { Play, Square } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogTitle, DialogDescription } from '@/components/ui/dialog'
import { DataState, QueryError } from '@/components/feedback/DataState'
import {
  base,
  request,
  scoped,
  write,
  WorkflowError,
  pageSchema,
  runSummarySchema,
  runSchema,
  artifactSchema,
  deliverableSchema,
  type Run,
  type Version,
  type Artifact,
  type Graph,
} from './api'
import { checkpointTasks } from './registry'

export function WorkflowRunPanel({
  organization,
  project,
  workflow,
  user,
  csrf,
  permissions,
  versions,
  run,
  runError,
  pendingRun,
  onRun,
  onRefresh,
  onSelect,
  artifactId,
  graph,
  onArtifact,
}: {
  organization: string
  project: string
  workflow: string
  user: string
  csrf?: string
  permissions: Record<string, boolean>
  versions: Omit<Version, 'graph'>[]
  run?: Run
  runError?: Error | null
  pendingRun: boolean
  onRun: (id: string) => void
  onRefresh: () => void
  onSelect: (id: string) => void
  artifactId: string | null
  graph?: Graph
  onArtifact: (id: string) => void
}) {
  const { t } = useTranslation(),
    [input, setInput] = useState(''),
    [versionId, setVersionId] = useState(''),
    [consent, setConsent] = useState(false),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(false)
  const [confirmStop, setConfirmStop] = useState(false)
  const pendingKey = ['aryn-workflow-request', user, organization, project, workflow].join(':')
  type Start = {
    version_id: string
    input: string
    idempotency_key: string
    allow_remote_model: true
  }
  const original = useRef<Start | null>(null)
  const [uncertain, setUncertain] = useState(false)
  useEffect(() => {
    try {
      const stored: unknown = JSON.parse(sessionStorage.getItem(pendingKey) ?? 'null')
      if (
        stored &&
        typeof stored === 'object' &&
        'input' in stored &&
        typeof stored.input === 'string' &&
        stored.input.length <= 8000 &&
        'version_id' in stored &&
        typeof stored.version_id === 'string' &&
        'idempotency_key' in stored &&
        typeof stored.idempotency_key === 'string' &&
        stored.idempotency_key.length <= 128
      ) {
        original.current = {
          input: stored.input,
          version_id: stored.version_id,
          idempotency_key: stored.idempotency_key,
          allow_remote_model: true,
        }
        setUncertain(true)
      }
    } catch {
      /* Private browser storage may be unavailable. */
    }
  }, [pendingKey])
  const history = useInfiniteQuery({
    queryKey: ['workflow-history', user, organization, project, workflow],
    initialPageParam: '',
    retry: false,
    queryFn: async ({ signal, pageParam }) => {
      const page = await request(
        base(project) +
          '/workflows/' +
          encodeURIComponent(workflow) +
          '/runs?' +
          new URLSearchParams({ after: pageParam, limit: '25' }),
        pageSchema(runSummarySchema),
        { signal },
      )
      page.items.forEach((item) => {
        scoped(item, organization, project)
        if (item.workflow_id !== workflow) throw new Error('Workflow scope differs.')
      })
      return page
    },
    getNextPageParam: (last) => last.next ?? undefined,
  })
  async function start() {
    if (!csrf || busy || !permissions['run:create'] || (!uncertain && (!consent || !input.trim())))
      return
    const body = original.current ?? {
      version_id: versionId || versions[0]?.id || '',
      input,
      idempotency_key: crypto.randomUUID(),
      allow_remote_model: true as const,
    }
    original.current = body
    try {
      sessionStorage.setItem(pendingKey, JSON.stringify(body))
    } catch {
      /* Keep the in-memory key. */
    }
    setBusy(true)
    setError(false)
    try {
      const result = scoped(
        await write(
          base(project) + '/workflows/' + encodeURIComponent(workflow) + '/runs',
          body,
          runSchema,
          csrf,
          true,
        ),
        organization,
        project,
      )
      if (result.workflow_id !== workflow || result.version_id !== body.version_id)
        throw new Error('Workflow identity differs.')
      onRun(result.id)
      original.current = null
      setUncertain(false)
      try {
        sessionStorage.removeItem(pendingKey)
      } catch {
        /* No authority depends on storage. */
      }
      await history.refetch()
    } catch (failure) {
      setError(true)
      const ambiguous =
        !(failure instanceof WorkflowError) || failure.status === 0 || failure.status >= 500
      setUncertain(ambiguous)
      if (!ambiguous) {
        original.current = null
        try {
          sessionStorage.removeItem(pendingKey)
        } catch {
          /* Optional storage. */
        }
      }
    } finally {
      setBusy(false)
    }
  }
  async function stop() {
    if (!run || !csrf || busy || !permissions['run:cancel']) return
    setBusy(true)
    setError(false)
    try {
      const result = scoped(
        await write(
          base(project) + '/workflow-runs/' + encodeURIComponent(run.id) + '/stop',
          {},
          runSchema,
          csrf,
        ),
        organization,
        project,
      )
      if (result.id !== run.id) throw new Error('Run identity differs.')
      onRefresh()
      setConfirmStop(false)
      await history.refetch()
    } catch {
      setError(true)
    } finally {
      setBusy(false)
    }
  }
  return (
    <div className="wf-panel">
      <h2>{t('workflows.executionPanel')}</h2>
      <details open={!run}>
        <summary>{t('workflows.run')}</summary>
        <label className="af-field">
          <span>{t('workflows.version')}</span>
          <select
            aria-label={t('workflows.version')}
            value={
              uncertain ? (original.current?.version_id ?? '') : versionId || versions[0]?.id || ''
            }
            disabled={busy || uncertain}
            onChange={(e) => setVersionId(e.target.value)}
          >
            <option value="" disabled>
              {t('workflows.version')}
            </option>
            {versions.map((v) => (
              <option key={v.id} value={v.id}>
                {t('workflows.revision')} {v.revision} · {v.digest.slice(0, 12)}
              </option>
            ))}
            {uncertain &&
              original.current &&
              !versions.some((v) => v.id === original.current!.version_id) && (
                <option value={original.current.version_id}>{original.current.version_id}</option>
              )}
          </select>
        </label>
        <label className="af-field">
          <span>{t('workflows.input')}</span>
          <textarea
            aria-label={t('workflows.input')}
            rows={4}
            maxLength={8000}
            value={uncertain ? (original.current?.input ?? input) : input}
            disabled={busy || uncertain}
            onChange={(e) => setInput(e.target.value)}
          />
        </label>
        <label className="af-check">
          <input
            type="checkbox"
            checked={consent}
            disabled={busy || uncertain}
            onChange={(e) => setConsent(e.target.checked)}
          />
          {t('workflows.consent')}
        </label>
        <div className="wf-actions">
          <Button
            disabled={
              busy ||
              !csrf ||
              !permissions['run:create'] ||
              (!uncertain && (!consent || !input.trim() || !versions.length))
            }
            onClick={() => void start()}
          >
            <Play size={15} />
            {t(uncertain ? 'workflows.retry' : 'workflows.run')}
          </Button>
        </div>
      </details>
      {!versions.length && <p className="af-note">{t('workflows.noVersions')}</p>}
      {uncertain && (
        <p className="af-note" role="alert">
          {t('workflows.uncertain')}
        </p>
      )}
      {error && (
        <p className="af-error" role="alert">
          {t('workflows.genericError')}
        </p>
      )}
      {runError ? (
        <QueryError error={runError} retry={onRefresh} />
      ) : pendingRun ? (
        <DataState kind="loading" />
      ) : run ? (
        <>
          <div className="af-run-state" data-state={run.status} role="status">
            {t('workflows.' + run.status)}
          </div>
          <p className="af-note">{t('workflows.checkpointHelp')}</p>
          <code>{run.id}</code>
          <Button variant="secondary" asChild>
            <Link
              to="/brief"
              search={{ project, tab: 'linked', kind: 'workflow_run', ref: run.id }}
            >
              Brief · {t('intelligence.linked')}
            </Link>
          </Button>
          <Button variant="secondary" asChild>
            <Link to="/runs" search={{ project, run: run.id, runKind: 'workflow' }}>
              {t('operations.runLink')}
            </Link>
          </Button>
          {run.error_code && <p className="af-error">{run.error_code}</p>}
          {['running', 'waiting_review'].includes(run.status) && (
            <>
              <Button
                variant="secondary"
                disabled={busy || !permissions['run:cancel']}
                onClick={() => setConfirmStop(true)}
              >
                <Square size={14} />
                {t('workflows.stop')}
              </Button>
              <p className="af-note">{t('workflows.stopHelp')}</p>
            </>
          )}
          <h3>{t('workflows.trace')}</h3>
          <ol className="wf-timeline">
            {checkpointTasks(graph, run).map((task) => (
              <li key={task.node_id}>
                <button data-state={task.status} onClick={() => onSelect(task.node_id)}>
                  <span>{task.node_id}</span>
                  <span>{t('workflows.' + task.status)}</span>
                </button>
              </li>
            ))}
          </ol>
          <details>
            <summary>{t('workflows.input')}</summary>
            <pre>{run.input}</pre>
          </details>
          {run.artifact_id && (
            <Button variant="secondary" onClick={() => onArtifact(run.artifact_id!)}>
              {t('workflows.output')}
            </Button>
          )}
          {(artifactId || run.artifact_id) && (
            <ArtifactPanel
              key={artifactId ?? run.artifact_id}
              organization={organization}
              project={project}
              workflow={workflow}
              run={run}
              id={artifactId ?? run.artifact_id!}
              user={user}
              csrf={csrf}
              canReview={!!permissions['version:approve']}
              onRefresh={() => {
                onRefresh()
                void history.refetch()
              }}
            />
          )}
        </>
      ) : (
        <p className="af-note">{t('workflows.noRun')}</p>
      )}
      <h3>{t('workflows.history')}</h3>
      <Dialog
        open={confirmStop}
        onOpenChange={(open) => {
          if (!busy) setConfirmStop(open)
        }}
      >
        <DialogContent>
          <DialogTitle>{t('workflows.stop')}</DialogTitle>
          <DialogDescription>{t('workflows.stopHelp')}</DialogDescription>
          <code>{run?.id}</code>
          <div className="af-dialog-actions">
            <Button variant="secondary" disabled={busy} onClick={() => setConfirmStop(false)}>
              {t('agents.cancel')}
            </Button>
            <Button disabled={busy} onClick={() => void stop()}>
              {t('workflows.stop')}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
      {history.error ? (
        <QueryError error={history.error} retry={() => void history.refetch()} />
      ) : (
        <div className="wf-run-list">
          {history.data?.pages
            .flatMap((p) => p.items)
            .map((item) => (
              <button
                key={item.id}
                aria-pressed={run?.id === item.id}
                onClick={() => {
                  onRun(item.id)
                  if (item.artifact_id) onArtifact(item.artifact_id)
                }}
              >
                <span>{t('workflows.' + item.status)}</span>
                <code>{item.id}</code>
              </button>
            ))}
        </div>
      )}
      {history.hasNextPage && (
        <Button
          variant="secondary"
          onClick={() => void history.fetchNextPage()}
          disabled={history.isFetchingNextPage}
        >
          {t('workflows.more')}
        </Button>
      )}
    </div>
  )
}
export function ArtifactPanel({
  organization,
  project,
  workflow,
  run,
  id,
  user,
  csrf,
  canReview,
  onRefresh,
}: {
  organization: string
  project: string
  workflow: string
  run: Run
  id: string
  user: string
  csrf?: string
  canReview: boolean
  onRefresh: () => void
}) {
  const { t } = useTranslation(),
    [reason, setReason] = useState(''),
    [decision, setDecision] = useState<'accepted' | 'rejected' | null>(null),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(false)
  const query = useQuery({
    queryKey: ['workflow-artifact', user, organization, project, workflow, run.id, id],
    retry: false,
    queryFn: async ({ signal }) => {
      const artifact = scoped(
        await request(base(project) + '/outputs/' + encodeURIComponent(id), artifactSchema, {
          signal,
        }),
        organization,
        project,
      )
      if (artifact.id !== id || artifact.workflow_run_id !== run.id)
        throw new Error('Artifact scope differs.')
      const response = await fetch(
        base(project) + '/outputs/' + encodeURIComponent(id) + '/preview',
        { credentials: 'same-origin', signal, headers: { Accept: artifact.mime } },
      )
      if (!response.ok || !response.headers.get('content-type')?.startsWith(artifact.mime))
        throw new Error('Artifact unavailable.')
      const content = await response.text()
      if (new TextEncoder().encode(content).length !== artifact.length)
        throw new Error('Artifact size differs.')
      const hash = [
        ...new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(content))),
      ]
        .map((v) => v.toString(16).padStart(2, '0'))
        .join('')
      if (hash !== artifact.digest) throw new Error('Artifact digest differs.')
      return { artifact, content }
    },
  })
  const receipts = useQuery({
    queryKey: ['workflow-deliverables', user, organization, project, workflow, run.id, run.status],
    enabled: ['completed', 'rejected'].includes(run.status),
    retry: false,
    queryFn: async ({ signal }) => {
      const receipt = scoped(
        await request(
          base(project) + '/workflow-runs/' + encodeURIComponent(run.id) + '/review',
          deliverableSchema,
          { signal },
        ),
        organization,
        project,
      )
      if (receipt.workflow_run_id !== run.id) throw new Error('Receipt scope differs.')
      return [receipt]
    },
  })
  const data = !query.error ? query.data : undefined
  async function review(artifact: Artifact) {
    if (
      !csrf ||
      !decision ||
      !canReview ||
      !reason.trim() ||
      busy ||
      artifact.id !== run.artifact_id
    )
      return
    setBusy(true)
    setError(false)
    try {
      const receipt = scoped(
        await write(
          base(project) + '/workflow-runs/' + encodeURIComponent(run.id) + '/review',
          { digest: artifact.digest, decision, reason: reason.trim() },
          deliverableSchema,
          csrf,
        ),
        organization,
        project,
      )
      if (receipt.workflow_run_id !== run.id || receipt.digest !== artifact.digest)
        throw new Error('Receipt identity differs.')
      setDecision(null)
      onRefresh()
    } catch {
      setError(true)
    } finally {
      setBusy(false)
    }
  }
  return (
    <section className="wf-inspector-result">
      <h3>{t('workflows.artifact')}</h3>
      {query.isPending ? (
        <DataState kind="loading" />
      ) : query.error ? (
        <QueryError error={query.error} retry={() => void query.refetch()} />
      ) : (
        data && (
          <>
            <code>{data.artifact.id}</code>
            <dl className="af-detail-list">
              <dt>{t('workflows.digest')}</dt>
              <dd>
                <code>{data.artifact.digest}</code>
              </dd>
              <dt>{t('workflows.actualModel')}</dt>
              <dd>{data.artifact.model ?? t('agents.notRecorded')}</dd>
              <dt>{t('workflows.pinnedVersion')}</dt>
              <dd>
                <code>{data.artifact.agent_version_id ?? t('agents.notRecorded')}</code>
              </dd>
              <dt>{t('workflows.coreRun')}</dt>
              <dd>
                <code>{data.artifact.core_run_id ?? t('agents.notRecorded')}</code>
              </dd>
            </dl>
            <h3>{t('workflows.preview')}</h3>
            {data.artifact.mime === 'text/html' ? (
              <iframe
                title={t('workflows.preview')}
                sandbox=""
                referrerPolicy="no-referrer"
                srcDoc={data.content}
              />
            ) : (
              <pre>{(JSON.parse(data.content) as { text: string }).text}</pre>
            )}
            <a
              className="button button-secondary"
              href={base(project) + '/outputs/' + encodeURIComponent(id) + '/download'}
              download
            >
              {t('workflows.download')}
            </a>
            {run.status === 'waiting_review' && run.artifact_id === id && canReview && (
              <>
                <h3>{t('workflows.review')}</h3>
                <label className="af-field">
                  <span>{t('workflows.reviewReason')}</span>
                  <textarea
                    maxLength={1000}
                    value={reason}
                    onChange={(e) => setReason(e.target.value)}
                  />
                </label>
                <div className="wf-actions">
                  {(['accepted', 'rejected'] as const).map((value) => (
                    <Button
                      key={value}
                      variant={value === 'accepted' ? 'default' : 'secondary'}
                      disabled={!canReview || !csrf || busy || !reason.trim()}
                      onClick={() => setDecision(value)}
                    >
                      {t(value === 'accepted' ? 'workflows.accept' : 'workflows.reject')}
                    </Button>
                  ))}
                </div>
              </>
            )}
            {receipts.data?.map((receipt) => (
              <section key={receipt.id}>
                <h3>{t('workflows.receipt')}</h3>
                <p>
                  {t('workflows.' + receipt.decision)} · {receipt.reviewer}
                </p>
                <p>{receipt.reason}</p>
                <time>{receipt.created_at}</time>
                <code>{receipt.digest}</code>
              </section>
            ))}
            {receipts.error && (
              <QueryError error={receipts.error} retry={() => void receipts.refetch()} />
            )}
            {error && (
              <p role="alert" className="af-error">
                {t('workflows.genericError')}
              </p>
            )}
            <Dialog
              open={!!decision}
              onOpenChange={(open) => {
                if (!open && !busy) setDecision(null)
              }}
            >
              <DialogContent>
                <DialogTitle>{t('workflows.confirmReview')}</DialogTitle>
                <DialogDescription>{t('workflows.reviewConfirmHelp')}</DialogDescription>
                <code className="af-hash">{data.artifact.digest}</code>
                <p>{reason}</p>
                <div className="af-dialog-actions">
                  <Button variant="secondary" disabled={busy} onClick={() => setDecision(null)}>
                    {t('agents.cancel')}
                  </Button>
                  <Button disabled={busy} onClick={() => void review(data.artifact)}>
                    {t(decision === 'accepted' ? 'workflows.accept' : 'workflows.reject')}
                  </Button>
                </div>
              </DialogContent>
            </Dialog>
          </>
        )
      )}
    </section>
  )
}
