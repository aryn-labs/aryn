import { ArrowUpRight, CirclePlay, FileText } from 'lucide-react'
import { formatDate } from '@/lib/utils'
import type { HomeResource } from '../lib/home-state'
import { activityLabel, statusLabel } from '../lib/home-labels'
export function RecentActivity({
  items,
  onOpen,
}: {
  items: HomeResource[]
  onOpen: (item: HomeResource) => void
}) {
  if (!items.length) return null
  return (
    <section className="home-section" aria-labelledby="activity-heading">
      <div className="home-section-heading">
        <h2 id="activity-heading">Recent Activity</h2>
        <p>Recorded work and outcomes from your project.</p>
      </div>
      <div className="home-panel">
        {items.map((item) => {
          const Icon = item.kind === 'run' ? CirclePlay : FileText
          const name = item.kind === 'audit' ? activityLabel(item.name) : item.name
          return (
            <button
              key={`${item.kind}:${item.id}`}
              className="home-activity-row"
              aria-label={`Inspect ${name}`}
              onClick={() => onOpen(item)}
            >
              <Icon size={17} aria-hidden="true" />
              <span className="home-row-main">
                <span className="home-row-name">{name}</span>
                <span className="home-row-description">
                  {item.kind === 'run' ? 'Run' : 'Project activity'}
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
