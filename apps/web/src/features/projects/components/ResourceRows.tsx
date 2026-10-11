import { useTranslation } from 'react-i18next'
import {
  Bot,
  Folder,
  Users,
  FileText,
  PlayCircle,
  Workflow,
  AlertTriangle,
  ChevronRight,
  Activity,
  FlaskConical,
} from 'lucide-react'
import type { ProjectResource } from '../lib/api'
import { resourceTitle, reference } from '../lib/presentation'
export function ResourceRows({
  items,
  onOpen,
  results = false,
}: {
  items: ProjectResource[]
  onOpen: (item: ProjectResource) => void
  results?: boolean
}) {
  const { t, i18n } = useTranslation()
  return (
    <div className={`project-resource-list${results ? ' project-results-list' : ''}`}>
      {results && (
        <div className="project-results-columns" aria-hidden="true">
          <span>{t('projects.nameColumn')}</span>
          <span>{t('projects.format')}</span>
          <span>{t('projects.source')}</span>
          <span>{t('projects.status')}</span>
        </div>
      )}
      {items.map((item) => {
        const Icon = {
          assignment: Bot,
          member: Users,
          division: Folder,
          run: PlayCircle,
          workflow: Workflow,
          'workflow-run': Workflow,
          artifact: FileText,
          evaluation: FlaskConical,
          audit: Activity,
        }[item.kind]
        const title = resourceTitle(item, t)
        const status =
          item.status && i18n.exists('projects.statuses.' + item.status)
            ? t('projects.statuses.' + item.status)
            : undefined
        return (
          <button
            type="button"
            className={`project-resource-row${results ? ' project-result-row' : ''}`}
            key={`${item.kind}:${item.id}`}
            onClick={() => onOpen(item)}
            aria-label={[title, t('projects.' + item.kind), status].filter(Boolean).join(' · ')}
          >
            <Icon size={19} aria-hidden="true" />
            <span className="project-row-text">
              <strong title={title}>{title}</strong>
              {!results && (
                <span>
                  {t('projects.' + item.kind)}
                  {item.kind === 'artifact' &&
                    ` · ${i18n.exists('projects.' + item.format) ? t('projects.' + item.format) : item.format}`}
                  {reference(item, 'version_number') && ` · v${reference(item, 'version_number')}`}
                  {reference(item, 'role') &&
                    ` · ${t('projects.roles.' + reference(item, 'role'))}`}
                  {reference(item, 'role_name') && ` · ${reference(item, 'role_name')}`}
                  {(item.kind === 'run' || item.kind === 'workflow-run') &&
                    ` · ${new Intl.DateTimeFormat(i18n.language, { dateStyle: 'short', timeStyle: 'short' }).format(new Date(item.created_at))}`}
                </span>
              )}
            </span>
            {results && (
              <>
                <span className="project-result-format">
                  {i18n.exists('projects.' + item.format)
                    ? t('projects.' + item.format)
                    : item.format}
                </span>
                <span className="project-result-source">
                  {reference(item, 'source_name') ?? t('projects.' + item.kind)}
                </span>
              </>
            )}
            <span
              className={`project-row-status ${['failed', 'outcome_unknown', 'waiting_review'].includes(item.status ?? '') ? 'project-status-warning' : ['active', 'completed', 'passed', 'approved'].includes(item.status ?? '') ? 'project-status-success' : ''}`}
            >
              {item.verified === false ? (
                <>
                  <AlertTriangle size={14} aria-label={t('projects.unverified')} />
                  {status}
                </>
              ) : (
                status
              )}
            </span>
            <ChevronRight size={15} aria-hidden="true" />
          </button>
        )
      })}
    </div>
  )
}
