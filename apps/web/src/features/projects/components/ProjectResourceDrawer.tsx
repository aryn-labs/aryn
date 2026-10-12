import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { useRef } from 'react'
import { Link } from '@tanstack/react-router'
import { Dialog, DialogContent, DialogDescription, DialogTitle } from '@/components/ui/dialog'
import { DataState, QueryError } from '@/components/feedback/DataState'
import { Button } from '@/components/ui/button'
import { request } from '@/lib/api/client'
import {
  assertProjectScope,
  path,
  projectKey,
  projectResourceSchema,
  type ProjectResource,
  type Scope,
} from '../lib/api'
import { resourceTitle, reference } from '../lib/presentation'
const provenanceFields = [
  'workflow_id',
  'workflow_run_id',
  'version_id',
  'agent_version_id',
  'blueprint_id',
  'core_run_id',
  'source_artifact_id',
  'digest',
  'model',
  'division_id',
  'user_id',
  'role',
] as const

export function ProjectResourceDrawer({
  scope,
  selection,
  onClose,
}: {
  scope: Scope
  selection?: Pick<ProjectResource, 'id' | 'kind'>
  onClose: () => void
}) {
  const { t, i18n } = useTranslation()
  const returnFocus = useRef<HTMLElement | null>(null)
  const query = useQuery({
    queryKey: [...projectKey(scope), 'resource', selection?.kind, selection?.id],
    enabled: !!selection && !!scope.organization,
    retry: false,
    queryFn: async ({ signal }) => {
      const data = assertProjectScope(
        await request(
          path(scope.project) +
            '/project-resources/detail/' +
            selection!.kind +
            '/' +
            encodeURIComponent(selection!.id),
          projectResourceSchema,
          { signal },
        ),
        scope,
      )
      if (data.id !== selection!.id || data.kind !== selection!.kind)
        throw new Error('Resource identity differs.')
      return data
    },
  })
  const item = !query.error ? query.data : undefined
  const provenance = item ? provenanceFields.filter((key) => reference(item, key)) : []
  return (
    <Dialog
      open={!!selection}
      onOpenChange={(open) => {
        if (!open) onClose()
      }}
    >
      <DialogContent
        className="project-detail-drawer"
        onOpenAutoFocus={() => {
          returnFocus.current =
            document.activeElement instanceof HTMLElement &&
            document.activeElement !== document.body
              ? document.activeElement
              : null
        }}
        onCloseAutoFocus={(event) => {
          event.preventDefault()
          if (returnFocus.current?.isConnected) returnFocus.current.focus()
          else document.getElementById('main-content')?.focus()
        }}
      >
        <header>
          <p className="project-eyebrow">{t('projects.detail')}</p>
          <DialogTitle>{item ? resourceTitle(item, t) : t('projects.loading')}</DialogTitle>
          <DialogDescription>
            {item ? t('projects.' + item.kind) : t('projects.provenance')}
          </DialogDescription>
        </header>
        <div className="project-drawer-body">
          {query.isPending ? (
            <DataState kind="loading" />
          ) : query.error ? (
            <QueryError error={query.error} retry={() => void query.refetch()} />
          ) : (
            item && (
              <>
                {(item.kind === 'artifact' ||
                  item.kind === 'run' ||
                  item.kind === 'evaluation') && (
                  <section className="project-output-preview">
                    <h3>{t('projects.preview')}</h3>
                    {item.preview?.kind === 'text' ? (
                      <pre className="project-text-preview">{item.preview.text}</pre>
                    ) : (
                      <p>{t('projects.unavailablePreview')}</p>
                    )}
                  </section>
                )}
                <section>
                  <h3>
                    {t(
                      ['artifact', 'run', 'evaluation'].includes(item.kind)
                        ? 'projects.information'
                        : 'projects.detail',
                    )}
                  </h3>
                  <dl className="project-detail-fields">
                    <dt>{t('projects.format')}</dt>
                    <dd>
                      {i18n.exists('projects.' + item.format)
                        ? t('projects.' + item.format)
                        : item.format}
                    </dd>
                    {item.status && (
                      <>
                        <dt>{t('projects.status')}</dt>
                        <dd>
                          {i18n.exists('projects.statuses.' + item.status)
                            ? t('projects.statuses.' + item.status)
                            : t('common.unknown')}
                        </dd>
                      </>
                    )}
                    <dt>{t('projects.date')}</dt>
                    <dd>
                      {new Intl.DateTimeFormat(i18n.language, {
                        dateStyle: 'medium',
                        timeStyle: 'short',
                      }).format(new Date(item.created_at))}
                    </dd>
                    {reference(item, 'version_number') && (
                      <>
                        <dt>{t('projects.version')}</dt>
                        <dd>{reference(item, 'version_number')}</dd>
                      </>
                    )}
                    {item.verified !== null && item.verified !== undefined && (
                      <>
                        <dt>{t('projects.provenance')}</dt>
                        <dd>
                          {t(
                            item.verified
                              ? item.kind === 'run'
                                ? 'projects.claimVerified'
                                : 'projects.verified'
                              : 'projects.unverified',
                          )}
                        </dd>
                      </>
                    )}
                  </dl>
                </section>
                {provenance.length > 0 && (
                  <section>
                    <h3>{t('projects.provenance')}</h3>
                    <dl className="project-detail-fields">
                      {provenance.map((key) => (
                        <div key={key} className="project-reference">
                          <dt>{t('projects.references.' + key)}</dt>
                          <dd>{reference(item, key)}</dd>
                        </div>
                      ))}
                    </dl>
                  </section>
                )}
                <details className="project-technical">
                  <summary>{t('projects.technical')}</summary>
                  <pre>{JSON.stringify({ id: item.id, ...item.references }, null, 2)}</pre>
                </details>
              </>
            )
          )}
        </div>
        <footer>
          {item?.kind === 'assignment' && reference(item, 'blueprint_id') && (
            <Button variant="secondary" asChild>
              <Link
                to="/agents/$projectId/$blueprintId"
                params={{ projectId: scope.project, blueprintId: reference(item, 'blueprint_id')! }}
              >
                {t('agents.open')}
              </Link>
            </Button>
          )}
          <Button variant="secondary" onClick={onClose}>
            {t('projects.close')}
          </Button>
        </footer>
      </DialogContent>
    </Dialog>
  )
}
