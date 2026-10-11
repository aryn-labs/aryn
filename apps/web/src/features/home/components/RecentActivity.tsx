import { ArrowUpRight, CirclePlay, FileText } from 'lucide-react'
import { formatDate } from '@/lib/utils'
import type { HomeResource } from '../lib/home-state'
import { activityLabel, statusLabel } from '../lib/home-labels'
import { useTranslation } from 'react-i18next'
export function RecentActivity({
  items,
  onOpen,
}: {
  items: HomeResource[]
  onOpen: (item: HomeResource) => void
}) {
  const { t } = useTranslation()
  if (!items.length) return null
  return (
    <section className="home-section" aria-labelledby="activity-heading">
      <div className="home-section-heading">
        <h2 id="activity-heading">{t('home.activity')}</h2>
      </div>
      <div className="home-panel">
        {items.slice(0, 4).map((item) => {
          const Icon = item.kind === 'run' ? CirclePlay : FileText
          const name = item.kind === 'audit' ? activityLabel(item.name) : item.name
          return (
            <button
              key={`${item.projectId ?? ''}:${item.kind}:${item.id}`}
              className="home-activity-row"
              aria-label={t('common.inspect', { name })}
              onClick={() => onOpen(item)}
            >
              <Icon size={17} aria-hidden="true" />
              <span className="home-row-main">
                <span className="home-row-name">{name}</span>
                <span className="home-row-description">
                  {t(item.kind === 'run' ? 'common.run' : 'common.activity')}
                  {item.projectName && (
                    <span className="home-row-project"> · {item.projectName}</span>
                  )}
                  {item.status ? ` · ${statusLabel(item.status)}` : ''}
                </span>
              </span>
              {item.createdAt && (
                <time dateTime={item.createdAt}>{formatDate(item.createdAt)}</time>
              )}
              <ArrowUpRight size={14} aria-hidden="true" />
            </button>
          )
        })}
      </div>
    </section>
  )
}
