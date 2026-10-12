import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { FlaskConical, ShieldCheck, ArrowUpRight, GitBranch } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogTitle } from '@/components/ui/dialog'
import { z } from '@/lib/types/validation'
import { basePath, post, type Lifecycle, type Version } from './api'

export function LifecyclePanel({
  lifecycle,
  projectId,
  blueprintId,
  csrf,
  busy,
  dirty,
  onCandidate,
  onRefresh,
  onSource,
  onVersion,
  versionId,
}: {
  lifecycle: Lifecycle
  projectId: string
  blueprintId: string
  csrf?: string
  busy: boolean
  dirty: boolean
  onCandidate: () => void
  onRefresh: () => Promise<void>
  onSource: (version: Version) => void
  onVersion: (id: string) => void
  versionId: string
}) {
  const { t, i18n } = useTranslation()
  const [action, setAction] = useState<
    'bench' | 'baseline' | 'approve' | 'publish' | 'assign' | null
  >(null)
  const [reason, setReason] = useState(''),
    [role, setRole] = useState(''),
    [division, setDivision] = useState('')
  const [consent, setConsent] = useState(false),
    [pending, setPending] = useState(false),
    [error, setError] = useState(false),
    [success, setSuccess] = useState(false)
  const version = lifecycle.versions.find((item) => item.id === versionId)
  const evaluation = lifecycle.evaluations.find(
    (item) => item.version_id === versionId && item.verified && item.passed,
  )
  const baseline = lifecycle.accepted_baselines.find((item) => item.blueprint_id === blueprintId)
  async function execute() {
    if (!action || !version || !csrf || pending) return
    setPending(true)
    setError(false)
    setSuccess(false)
    const path = basePath(projectId)
    try {
      const body =
        action === 'bench'
          ? { allow_remote_model: consent }
          : action === 'baseline'
            ? {
                evaluation_id: evaluation?.id,
                expected_baseline_id: baseline?.baseline_id ?? null,
                reason,
              }
            : action === 'approve'
              ? { comments: reason, payload_hash: version.payload_hash }
              : action === 'assign'
                ? {
                    blueprint_id: blueprintId,
                    version_id: version.id,
                    role_name: role,
                    division_id: division || null,
                  }
                : {}
      const url =
        action === 'baseline'
          ? `${path}/blueprints/${blueprintId}/baseline`
          : action === 'assign'
            ? `${path}/assignments`
            : `${path}/versions/${version.id}/${action}`
      await post(url, z.unknown(), csrf, body)
      await onRefresh()
      setAction(null)
      setSuccess(true)
    } catch {
      setError(true)
    } finally {
      setPending(false)
    }
  }
  return (
    <div className="af-lifecycle">
      <header>
        <GitBranch size={20} />
        <div>
          <h2>{t('agents.versions')}</h2>
          <p>{t('agents.lifecycleHelp')}</p>
        </div>
        <Button
          disabled={busy || !csrf || !lifecycle.permissions['version:create']}
          onClick={onCandidate}
        >
          {t('agents.candidate')}
        </Button>
      </header>
      <p className="af-note">
        {t('agents.immutable')} {t('agents.candidateHelp')}
      </p>
      {!lifecycle.versions.length ? (
        <p>{t('agents.noVersions')}</p>
      ) : (
        <div className="af-version-grid">
          <div className="af-version-list">
            {lifecycle.versions.map((item) => (
              <button
                key={item.id}
                aria-pressed={versionId === item.id}
                onClick={() => onVersion(item.id)}
              >
                <GitBranch size={16} />
                <span>
                  <strong>v{item.version_number}</strong>
                  <small>{item.model}</small>
                </span>
                <span className="af-state" data-state={item.status}>
                  {t('agents.' + item.status)}
                </span>
              </button>
            ))}
          </div>
          {version && (
            <section className="af-version-detail">
              <h3>
                v{version.version_number}{' '}
                <span className="af-state" data-state={version.status}>
                  {t('agents.' + version.status)}
                </span>
              </h3>
              <p>
                <ShieldCheck size={15} />
                {t(version.integrity_valid ? 'agents.integrity' : 'agents.unverified')}
              </p>
              <code>{version.payload_hash}</code>
              <div className="af-evaluation-results">
                <h4>{t('agents.benchResults')}</h4>
                {lifecycle.evaluations.filter((item) => item.version_id === version.id).length ===
                0 ? (
                  <p>{t('agents.noEvaluation')}</p>
                ) : (
                  lifecycle.evaluations
                    .filter((item) => item.version_id === version.id)
                    .map((item) => (
                      <p key={item.id}>
                        <strong>
                          {t(
                            !item.verified
                              ? 'agents.unverified'
                              : item.passed
                                ? 'agents.completed'
                                : 'agents.failed',
                          )}
                        </strong>{' '}
                        · {Math.round(item.score * 100)}%
                        {item.total_scenarios !== undefined && (
                          <>
                            {' '}
                            · {item.passed_scenarios ?? 0}/{item.total_scenarios}
                          </>
                        )}
                        {item.evaluated_at && (
                          <time dateTime={item.evaluated_at}>
                            {' '}
                            ·{' '}
                            {new Intl.DateTimeFormat(i18n.language, {
                              dateStyle: 'short',
                              timeStyle: 'short',
                            }).format(new Date(item.evaluated_at))}
                          </time>
                        )}
                      </p>
                    ))
                )}
              </div>
              {version.regression?.promotion_blocked && (
                <p className="af-note">{version.regression.reason}</p>
              )}
              <div className="af-lifecycle-actions">
                <Button
                  variant="secondary"
                  disabled={
                    busy ||
                    !version.configuration_loaded ||
                    !version.integrity_valid ||
                    !lifecycle.permissions['version:create']
                  }
                  onClick={() => onSource(version)}
                >
                  {t('agents.source')}
                </Button>
                <Button
                  variant="secondary"
                  disabled={
                    busy ||
                    pending ||
                    !['draft', 'rejected'].includes(version.status) ||
                    !version.integrity_valid ||
                    !lifecycle.permissions['run:create']
                  }
                  onClick={() => {
                    setAction('bench')
                    setConsent(false)
                    setError(false)
                  }}
                >
                  <FlaskConical size={15} />
                  {t('agents.bench')}
                </Button>
                <Button
                  variant="secondary"
                  disabled={
                    busy ||
                    pending ||
                    !evaluation ||
                    !lifecycle.permissions['bench:accept_baseline']
                  }
                  onClick={() => {
                    setAction('baseline')
                    setReason('')
                    setError(false)
                  }}
                >
                  {t('agents.baseline')}
                </Button>
                <Button
                  variant="secondary"
                  disabled={
                    busy ||
                    pending ||
                    version.status !== 'draft' ||
                    !version.bench_eligible ||
                    !lifecycle.permissions['version:approve']
                  }
                  onClick={() => {
                    setAction('approve')
                    setReason('')
                    setError(false)
                  }}
                >
                  {t('agents.approve')}
                </Button>
                <Button
                  disabled={
                    busy ||
                    pending ||
                    version.status !== 'approved' ||
                    !version.governance_valid ||
                    !lifecycle.permissions['version:publish']
                  }
                  onClick={() => {
                    setAction('publish')
                    setError(false)
                  }}
                >
                  <ArrowUpRight size={15} />
                  {t('agents.publish')}
                </Button>
                <Button
                  variant="secondary"
                  disabled={
                    busy ||
                    pending ||
                    version.status !== 'published' ||
                    !version.governance_valid ||
                    !lifecycle.permissions['agent:assign']
                  }
                  onClick={() => {
                    setAction('assign')
                    setRole('')
                    setDivision('')
                    setError(false)
                  }}
                >
                  {t('agents.assign')}
                </Button>
              </div>
              {dirty && <p className="af-note">{t('agents.sourceHelp')}</p>}
              <details>
                <summary>{t('agents.rawId')}</summary>
                <code>{version.id}</code>
              </details>
            </section>
          )}
        </div>
      )}
      <section className="af-assignment-list">
        <h2>{t('agents.assignments')}</h2>
        {!lifecycle.assignments.length ? (
          <p>{t('agents.noAssignments')}</p>
        ) : (
          lifecycle.assignments.map((assignment) => (
            <div key={assignment.id}>
              <strong>{assignment.role_name}</strong>
              <span>
                v
                {lifecycle.versions.find((item) => item.id === assignment.version_id)
                  ?.version_number ?? assignment.version_id}
              </span>
              <span>{assignment.status}</span>
              <span>
                {t(assignment.activation_verified ? 'agents.integrity' : 'agents.unverified')}
              </span>
            </div>
          ))
        )}
      </section>
      {success && <p role="status">{t('agents.actionSuccess')}</p>}
      <Dialog
        open={!!action}
        onOpenChange={(open) => {
          if (!open && !pending) setAction(null)
        }}
      >
        <DialogContent>
          <DialogTitle>{action ? t('agents.' + action) : t('agents.confirmAction')}</DialogTitle>
          <DialogDescription>{t('agents.lifecycleHelp')}</DialogDescription>
          <p>
            v{version?.version_number} · {version?.model}
          </p>
          <code className="af-hash">{version?.payload_hash}</code>
          {action === 'bench' && (
            <label className="af-check">
              <input
                type="checkbox"
                checked={consent}
                onChange={(event) => setConsent(event.target.checked)}
                disabled={pending}
              />
              {t('agents.consent')}
            </label>
          )}
          {(action === 'approve' || action === 'baseline') && (
            <label className="af-field">
              <span>{t('agents.reason')}</span>
              <textarea
                minLength={5}
                maxLength={2000}
                value={reason}
                disabled={pending}
                onChange={(event) => setReason(event.target.value)}
              />
            </label>
          )}
          {action === 'assign' && (
            <>
              <label className="af-field">
                <span>{t('agents.roleName')}</span>
                <input
                  value={role}
                  minLength={2}
                  maxLength={64}
                  disabled={pending}
                  onChange={(event) => setRole(event.target.value)}
                />
              </label>
              <label className="af-field">
                <span>{t('agents.division')}</span>
                <input
                  value={division}
                  maxLength={64}
                  disabled={pending}
                  onChange={(event) => setDivision(event.target.value)}
                />
              </label>
            </>
          )}
          {error && (
            <p role="alert" className="af-error">
              {t('agents.genericError')}
            </p>
          )}
          <div className="af-dialog-actions">
            <Button variant="secondary" disabled={pending} onClick={() => setAction(null)}>
              {t('agents.cancel')}
            </Button>
            <Button
              disabled={
                pending ||
                (action === 'bench' && !consent) ||
                ((action === 'approve' || action === 'baseline') && reason.trim().length < 5) ||
                (action === 'assign' && role.trim().length < 2)
              }
              onClick={() => void execute()}
            >
              {t(pending ? 'agents.saving' : 'agents.continue')}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  )
}
