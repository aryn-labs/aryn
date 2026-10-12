import { useEffect, useRef, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { Play, ShieldCheck, Check, AlertCircle, LoaderCircle } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { ApiError, request } from '@/lib/api/client'
import { basePath, post, previewSchema, scoped, terminal, type Preview } from './api'

export function PreviewPanel({
  organization,
  project,
  blueprint,
  user,
  generation,
  layoutGeneration,
  csrf,
  ready,
  save,
  onPreview,
}: {
  organization: string
  project: string
  blueprint: string
  user: string
  generation: number
  layoutGeneration: number
  csrf?: string
  ready: boolean
  save: () => Promise<{ generation: number; layoutGeneration: number }>
  onPreview: (preview?: Preview) => void
}) {
  const { t, i18n } = useTranslation()
  const client = useQueryClient()
  const storageKey = ['aryn-preview', user, organization, project, blueprint].join(':')
  const [prompt, setPrompt] = useState(''),
    [consent, setConsent] = useState(false),
    [pending, setPending] = useState(false),
    [error, setError] = useState(false)
  const [runId, setRunId] = useState(() => {
    try {
      return sessionStorage.getItem(storageKey) ?? ''
    } catch {
      return ''
    }
  })
  const original = useRef<Parameters<typeof start>[0] | null>(null)
  const mounted = useRef(true)
  useEffect(() => {
    mounted.current = true
    return () => {
      mounted.current = false
    }
  }, [])
  const history = useQuery({
    queryKey: ['agent-preview', user, organization, project, blueprint, runId],
    enabled: !!runId,
    retry: false,
    refetchOnWindowFocus: true,
    queryFn: async ({ signal }) => {
      const value = scoped(
        await request(
          basePath(project, blueprint) + '/preview-runs/' + encodeURIComponent(runId),
          previewSchema,
          { signal },
        ),
        organization,
        project,
      )
      if (value.blueprint_id !== blueprint || value.result.run_id !== runId)
        throw new Error('Preview identity differs')
      return value
    },
    refetchInterval: (query) =>
      query.state.error ? false : terminal(query.state.data?.result.status) ? false : 700,
  })
  useEffect(() => {
    onPreview(history.isError ? undefined : history.data)
  }, [history.data, history.isError, onPreview])
  async function start(body: {
    expected_generation: number
    expected_layout_generation: number
    prompt: string
    idempotency_key: string
    allow_remote_model: true
  }) {
    const value = scoped(
      await post(basePath(project, blueprint) + '/preview-runs', previewSchema, csrf!, body),
      organization,
      project,
    )
    if (!mounted.current) return
    client.setQueryData(
      ['agent-preview', user, organization, project, blueprint, value.result.run_id],
      value,
    )
    setRunId(value.result.run_id)
    try {
      sessionStorage.setItem(storageKey, value.result.run_id)
    } catch {
      /* An ID is optional; never persist prompts. */
    }
    original.current = null
    onPreview(value)
  }
  async function run() {
    if (!csrf || pending) return
    setPending(true)
    setError(false)
    try {
      if (!original.current) {
        const saved = await save()
        original.current = {
          expected_generation: saved.generation,
          expected_layout_generation: saved.layoutGeneration,
          prompt,
          idempotency_key: crypto.randomUUID(),
          allow_remote_model: true,
        }
      }
      await start(original.current)
    } catch (failure) {
      // Definitive rejection allows correction. Transport failures retain the same
      // idempotency key because dispatch may have succeeded before losing a response.
      if (failure instanceof ApiError && failure.status >= 400 && failure.status < 500)
        original.current = null
      if (mounted.current) setError(true)
    } finally {
      if (mounted.current) setPending(false)
    }
  }
  const value = history.isError ? undefined : history.data
  const result = value?.result
  const active = !!result && !terminal(result.status)
  return (
    <div className="af-preview">
      <header>
        <span className="af-node-icon">
          <Play size={17} />
        </span>
        <div>
          <h2>{t('agents.test')}</h2>
          <p>{t('agents.governed')}</p>
        </div>
      </header>
      <label className="af-field">
        <span>{t('agents.prompt')}</span>
        <textarea
          rows={4}
          value={prompt}
          disabled={pending || active || !!original.current}
          minLength={5}
          maxLength={12000}
          placeholder={t('agents.promptPlaceholder')}
          onChange={(event) => setPrompt(event.target.value)}
        />
      </label>
      <label className="af-check">
        <input
          type="checkbox"
          checked={consent}
          disabled={pending || active}
          onChange={(event) => setConsent(event.target.checked)}
        />
        {t('agents.consent')}
      </label>
      <Button
        className="af-run-button"
        disabled={pending || active || !ready || !consent || prompt.trim().length < 5 || !csrf}
        onClick={() => void run()}
      >
        {pending || active ? <LoaderCircle size={16} className="af-spin" /> : <Play size={16} />}
        {t(pending ? 'agents.loading' : 'agents.start')}
      </Button>
      {(error || history.isError) && (
        <div className="af-error" role="alert">
          {t('agents.genericError')} {t('agents.outcome_unknown')}
          {history.isError && (
            <Button variant="secondary" onClick={() => void history.refetch()}>
              {t('agents.restoreRun')}
            </Button>
          )}
        </div>
      )}
      <p className="af-note">
        <ShieldCheck size={15} />
        {t('agents.telemetry')}
      </p>
      {!result ? (
        <p className="af-preview-empty">{runId ? t('agents.loading') : t('agents.noRun')}</p>
      ) : (
        <>
          <div className="af-run-state" data-state={result.status}>
            <span className="af-small-dot" />
            {t('agents.' + result.status)}
          </div>
          {value.working_copy_generation !== generation && (
            <p className="af-note">{t('agents.staleRun')}</p>
          )}
          <details>
            <summary>{t('agents.recordedInput')}</summary>
            <pre className="af-recorded-input">{value.input}</pre>
          </details>
          <h3>{t('agents.trace')}</h3>
          <ol className="af-trace">
            {value.events.map((event) => (
              <li key={event.id}>
                <span>
                  {event.type === 'run.completed' ? (
                    <Check size={13} />
                  ) : event.type.includes('failed') || event.type.includes('unknown') ? (
                    <AlertCircle size={13} />
                  ) : (
                    <span className="af-small-dot" />
                  )}
                </span>
                <div>
                  <strong>{t('agents.' + event.type)}</strong>
                  <time dateTime={event.occurred_at}>
                    {new Intl.DateTimeFormat(i18n.language, {
                      hour: '2-digit',
                      minute: '2-digit',
                      second: '2-digit',
                      fractionalSecondDigits: 3,
                    }).format(new Date(event.occurred_at))}{' '}
                    · Core
                  </time>
                </div>
              </li>
            ))}
          </ol>
          {result.error_code && (
            <p className="af-error">
              {t('agents.' + result.status)} · {result.error_code}
            </p>
          )}
          {result.status === 'completed' && result.execution_claim_verified && (
            <section className="af-output">
              <h3>{t('agents.result')}</h3>
              <textarea readOnly aria-label={t('agents.result')} value={result.output} rows={8} />
            </section>
          )}
          <dl className="af-detail-list">
            <dt>{t('agents.actualModel')}</dt>
            <dd>{result.actual_model ?? t('agents.notRecorded')}</dd>
            <dt>{t('agents.provider')}</dt>
            <dd>{result.provider ?? t('agents.notRecorded')}</dd>
            <dt>{t('agents.elapsed')}</dt>
            <dd>
              {result.completed_at
                ? `${Math.round((result.completed_at - result.created_at) * 1000)} ms`
                : t('agents.notRecorded')}
            </dd>
            <dt>{t('agents.usage')}</dt>
            <dd>
              {result.usage.availability === 'measured'
                ? `${result.usage.total_tokens} (${result.usage.input_tokens} + ${result.usage.output_tokens})`
                : t('agents.notRecorded')}
            </dd>
            <dt>{t('agents.recordedCost')}</dt>
            <dd>
              {result.usage.cost_usd === null
                ? t('agents.notRecorded')
                : `${result.usage.cost_usd} USD`}
            </dd>
          </dl>
          <details>
            <summary>{t('agents.runId')}</summary>
            <code>{result.run_id}</code>
            <p>{value.definition_hash}</p>
          </details>
          {active && <p className="af-note">{t('agents.stopUnavailable')}</p>}
        </>
      )}
      <p className="af-note">{t('agents.diagnostic')}</p>
      <span className="sr-only">{layoutGeneration}</span>
    </div>
  )
}
