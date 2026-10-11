import { Link } from '@tanstack/react-router'
import { MessageSquare, ArrowUpRight } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { HomeResourceRow } from './HomeResourceRow'
import type { HomeResource } from '../lib/home-state'
export type RecentConversation = {
  id: string
  title: string
  model: string
  updated_at: string | number
  projectId?: string
  projectName?: string
}
export function ContinueWorking({
  agents,
  workflows,
  conversations = [],
  onOpen,
}: {
  agents: HomeResource[]
  workflows: HomeResource[]
  conversations?: RecentConversation[]
  onOpen: (item: HomeResource) => void
  workflowsError?: Error | null
}) {
  const { t } = useTranslation()
  const items = [
    ...agents.map((item) => ({
      kind: 'resource' as const,
      item,
      time: Date.parse(item.createdAt ?? '') || 0,
    })),
    ...workflows.map((item) => ({ kind: 'resource' as const, item, time: 0 })),
    ...conversations.map((item) => ({
      kind: 'conversation' as const,
      item,
      time: new Date(item.updated_at).getTime(),
    })),
  ]
    .sort((a, b) => b.time - a.time)
    .slice(0, 4)
  if (!items.length) return null
  return (
    <section className="home-section" aria-labelledby="continue-heading">
      <div className="home-section-heading">
        <h2 id="continue-heading">{t('home.continue')}</h2>
      </div>
      <div className="home-panel">
        {items.map((entry) =>
          entry.kind === 'resource' ? (
            <HomeResourceRow
              key={`${entry.item.projectId ?? ''}:${entry.item.kind}:${entry.item.id}`}
              item={entry.item}
              onOpen={onOpen}
            />
          ) : (
            <Link
              key={`${entry.item.projectId ?? ''}:conv:${entry.item.id}`}
              to="/chat/$conversationId"
              params={{ conversationId: entry.item.id }}
              className="home-resource-row"
            >
              <span className="home-row-icon">
                <MessageSquare size={17} aria-hidden="true" />
              </span>
              <span className="home-row-main">
                <span className="home-row-name">
                  {entry.item.title.length > 52
                    ? entry.item.title.slice(0, 48) + '…'
                    : entry.item.title}
                </span>
                <span className="home-row-description">
                  {t('common.conversation')}
                  {entry.item.projectName && (
                    <span className="home-row-project"> · {entry.item.projectName}</span>
                  )}
                </span>
              </span>
              <ArrowUpRight size={14} aria-hidden="true" />
            </Link>
          ),
        )}
      </div>
    </section>
  )
}
