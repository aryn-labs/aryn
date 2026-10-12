import {
  useState,
  useId,
  cloneElement,
  isValidElement,
  type ReactNode,
  type ReactElement,
} from 'react'
import { Link } from '@tanstack/react-router'
import { useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { ArrowLeft, RefreshCw, ShieldCheck } from 'lucide-react'
import { useWorkspace } from '@/app/providers/WorkspaceProvider'
import { StandardLayout } from '@/app/shell/MainWorkspace'
import { DataState, QueryError } from '@/components/feedback/DataState'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogTitle } from '@/components/ui/dialog'
import { Facts, Tabs } from '@/components/operations/OperationsUI'
import { base, write } from '@/features/intelligence/api'
import { useCopy, useFilters, useDialogFocus } from './hooks'
import { ApiError } from '@/lib/api/client'
import { z } from '@/lib/types/validation'
import './intelligence.css'
export { Facts, Tabs }
export function Field({ label, children }: { label: string; children: ReactNode }) {
  const id = useId(),
    labelId = id + '-label'
  return (
    <label className="op-field" htmlFor={id}>
      <span id={labelId}>{label}</span>
      {isValidElement(children)
        ? cloneElement(children as ReactElement<{ id?: string; 'aria-labelledby'?: string }>, {
            id,
            'aria-labelledby': labelId,
          })
        : children}
    </label>
  )
}
export function Badge({
  value,
  tone,
}: {
  value: string
  tone?: 'good' | 'warn' | 'bad' | 'neutral'
}) {
  const c = useCopy()
  const good = ['SUPPORTED', 'VERIFIED', 'RECOVERED', 'CLOSED', 'passed', 'support', 'fresh']
  const bad = [
    'FAILED',
    'DEGRADED',
    'OUTCOME_UNKNOWN',
    'failed',
    'policy_violation',
    'invalid_evidence',
    'conflict',
  ]
  const warn = [
    'CONFLICTING',
    'INSUFFICIENT_EVIDENCE',
    'UNVERIFIED',
    'PROPOSED',
    'stale',
    'unverifiable',
    'runtime_error',
  ]
  const label = ['passed', 'failed', 'support', 'conflict', 'neutral', 'fresh', 'stale'].includes(
    value,
  )
    ? c(value)
    : value === 'VERIFIED'
      ? c('verified')
      : value === 'UNVERIFIED'
        ? c('unverified')
        : value
  return (
    <span
      className="intel-badge"
      data-tone={
        tone ??
        (good.includes(value)
          ? 'good'
          : bad.includes(value)
            ? 'bad'
            : warn.includes(value)
              ? 'warn'
              : 'neutral')
      }
    >
      <span className="intel-status-dot" aria-hidden="true" />
      {label}
    </span>
  )
}
export function Notice({ children, warning = false }: { children: ReactNode; warning?: boolean }) {
  return (
    <div className="intel-notice" data-warning={warning}>
      <ShieldCheck size={17} aria-hidden="true" />
      <div>{children}</div>
    </div>
  )
}
export function Panel({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="intel-panel">
      <h2>{title}</h2>
      {children}
    </section>
  )
}
export function JsonFacts({ data }: { data: Record<string, unknown> }) {
  const c = useCopy()
  return (
    <Facts
      values={Object.entries(data).map(([k, v]) => [
        k,
        v === null || v === undefined
          ? c('unavailable')
          : typeof v === 'object'
            ? JSON.stringify(v)
            : String(v),
      ])}
    />
  )
}
export function DateValue({ value }: { value: string }) {
  const { i18n } = useTranslation()
  const date = new Date(value)
  return (
    <time dateTime={value}>
      {Number.isNaN(+date)
        ? '—'
        : new Intl.DateTimeFormat(i18n.language, {
            dateStyle: 'medium',
            timeStyle: 'short',
          }).format(date)}
    </time>
  )
}
export function IntelligenceLayout({
  module,
  tab,
  tabs,
  onTab,
  children,
  actions,
  refresh,
  back,
}: {
  module: 'bench' | 'brief' | 'relay'
  tab?: string
  tabs?: string[]
  onTab?: (v: string) => void
  children: ReactNode
  actions?: ReactNode
  refresh?: () => void
  back?: boolean
}) {
  const c = useCopy(),
    cache = useQueryClient(),
    workspace = useWorkspace()
  return (
    <StandardLayout title={c(module)}>
      <div className="intel-page">
        <header className="intel-header">
          <div>
            {back && (
              <Link
                className="intel-back"
                to={'/' + module}
                search={{ project: workspace.project?.id }}
              >
                <ArrowLeft size={14} />
                {c('back')}
              </Link>
            )}
            <p className="intel-eyebrow">ARYN · {c(module)}</p>
            <h1>{c(module)}</h1>
            <p>{c(module + 'Description')}</p>
          </div>
          <div className="intel-actions">
            {
              <Button
                variant="secondary"
                onClick={
                  refresh ??
                  (() => void cache.invalidateQueries({ queryKey: ['intelligence-catalog'] }))
                }
              >
                <RefreshCw size={15} />
                {c('refresh')}
              </Button>
            }
            {actions}
          </div>
        </header>
        {tabs && onTab && (
          <Tabs items={tabs.map((v) => [v, c(v)])} value={tab ?? tabs[0] ?? ''} onChange={onTab} />
        )}
        {children}
      </div>
    </StandardLayout>
  )
}
export function QueryState({
  query,
  empty,
}: {
  query: { isPending: boolean; error: Error | null; refetch: () => unknown }
  empty?: boolean
}) {
  const c = useCopy()
  return query.error ? (
    <QueryError error={query.error} retry={() => void query.refetch()} />
  ) : query.isPending ? (
    <DataState kind="loading" />
  ) : empty ? (
    <DataState title={c('empty')} description={c('emptyHelp')} />
  ) : null
}
export function More({
  query,
}: {
  query: { hasNextPage: boolean; isFetching: boolean; fetchNextPage: () => unknown }
}) {
  const c = useCopy()
  return query.hasNextPage ? (
    <Button
      className="intel-more"
      variant="secondary"
      disabled={query.isFetching}
      onClick={() => void query.fetchNextPage()}
    >
      {c('loadMore')}
    </Button>
  ) : null
}
export function CatalogFilters({
  filters,
  states = [],
  children,
}: {
  filters: ReturnType<typeof useFilters>
  states?: readonly string[]
  children?: ReactNode
}) {
  const c = useCopy(),
    workspace = useWorkspace()
  return (
    <div className="intel-filters">
      <Field label={c('search')}>
        <input value={filters.q} maxLength={100} onChange={(e) => filters.setQ(e.target.value)} />
      </Field>
      <Field label={c('project')}>
        <select value={filters.project} onChange={(e) => filters.setProject(e.target.value)}>
          <option value="">{c('allProjects')}</option>
          {workspace.context?.projects.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
            </option>
          ))}
        </select>
      </Field>
      {states.length > 0 && (
        <Field label={c('status')}>
          <select value={filters.status} onChange={(e) => filters.setStatus(e.target.value)}>
            <option value="">{c('allStatuses')}</option>
            {states.map((v) => (
              <option key={v} value={v}>
                {v === 'passed' || v === 'failed' ? c(v) : v}
              </option>
            ))}
          </select>
        </Field>
      )}
      {children}
    </div>
  )
}
export function ScopeGuard({ project, children }: { project: string; children: ReactNode }) {
  const w = useWorkspace()
  return w.error ? (
    <QueryError error={w.error} retry={w.retry} />
  ) : w.loading ? (
    <DataState kind="loading" />
  ) : !w.context?.projects.some((p) => p.id === project) ? (
    <DataState kind="unauthorized" />
  ) : (
    children
  )
}
export function ResourceLink({
  project,
  kind,
  id,
  children,
}: {
  project: string
  kind: string
  id: string
  children?: ReactNode
}) {
  const label = children ?? id
  if (kind === 'incident')
    return (
      <Link to="/relay/$projectId/$incidentId" params={{ projectId: project, incidentId: id }}>
        {label}
      </Link>
    )
  if (kind === 'bundle')
    return (
      <Link to="/brief/$projectId/$bundleId" params={{ projectId: project, bundleId: id }}>
        {label}
      </Link>
    )
  if (kind === 'source')
    return (
      <Link to="/brief/$projectId/sources/$sourceId" params={{ projectId: project, sourceId: id }}>
        {label}
      </Link>
    )
  if (kind === 'evaluation')
    return (
      <Link
        to="/bench/$projectId/evaluations/$evaluationId"
        params={{ projectId: project, evaluationId: id }}
      >
        {label}
      </Link>
    )
  if (kind === 'replay')
    return (
      <Link to="/bench/$projectId/replays/$replayId" params={{ projectId: project, replayId: id }}>
        {label}
      </Link>
    )
  if (kind === 'capsule')
    return (
      <Link
        to="/bench/$projectId/capsules/$capsuleId"
        params={{ projectId: project, capsuleId: id }}
      >
        {label}
      </Link>
    )
  if (kind === 'run' || kind === 'workflow_run')
    return (
      <Link
        to="/runs"
        search={{ project, run: id, runKind: kind === 'run' ? 'agent' : 'workflow' }}
      >
        {label}
      </Link>
    )
  if (kind === 'artifact')
    return (
      <Link
        to="/projects/$projectId/results"
        params={{ projectId: project }}
        search={{ selection: 'artifact:' + id }}
      >
        {label}
      </Link>
    )
  return <code>{label}</code>
}
export function MutationDialog({
  title,
  description,
  project,
  path,
  body,
  allowed,
  children,
  onSuccess,
  onClose,
}: {
  title: string
  description: string
  project: string
  path: string
  body: unknown
  allowed: boolean
  children?: ReactNode
  onSuccess: (result: unknown) => Promise<void> | void
  onClose: () => void
}) {
  const c = useCopy(),
    w = useWorkspace(),
    [busy, setBusy] = useState(false),
    [error, setError] = useState<Error | null>(null),
    focus = useDialogFocus()
  async function submit() {
    if (!w.csrf || !allowed || busy) return
    setBusy(true)
    setError(null)
    try {
      const data = await write(base(project) + path, body, z.unknown(), w.csrf)
      await onSuccess(data)
      onClose()
    } catch (e) {
      setError(e instanceof Error ? e : new Error(c('mutationError')))
    } finally {
      setBusy(false)
    }
  }
  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open && !busy) onClose()
      }}
    >
      <DialogContent className="intel-dialog" closeDisabled={busy} {...focus}>
        <DialogTitle>{title}</DialogTitle>
        <DialogDescription>{description}</DialogDescription>
        {children}
        {!allowed && <Notice warning>{c('noPermission')}</Notice>}
        {error && (
          <p role="alert">
            {error instanceof ApiError && error.status === 409
              ? c('conflictError')
              : c('mutationError')}
          </p>
        )}
        <div className="intel-actions">
          <Button variant="secondary" disabled={busy} onClick={onClose}>
            {c('cancel')}
          </Button>
          <Button disabled={!allowed || !w.csrf || busy} onClick={() => void submit()}>
            {busy ? '…' : c('confirm')}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}
