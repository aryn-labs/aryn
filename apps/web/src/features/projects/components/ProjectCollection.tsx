import { useDeferredValue, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Search } from 'lucide-react'
import { DataState } from '@/components/feedback/DataState'
import { Button } from '@/components/ui/button'
import { useProjectCollection } from '../hooks/useProjects'
import type { Collection, ProjectResource, Scope } from '../lib/api'
import { ProjectsSkeleton } from '../ProjectsPage'
import { ResourceRows } from './ResourceRows'
import { resourceTitle } from '../lib/presentation'
import { ProjectQueryError } from './ProjectQueryError'

export function ProjectCollection({
  scope,
  collection,
  onOpen,
}: {
  scope: Scope
  collection: Collection
  onOpen: (item: ProjectResource) => void
}) {
  const { t, i18n } = useTranslation()
  const [search, setSearch] = useState(''),
    [format, setFormat] = useState('')
  const q = useDeferredValue(search.trim())
  const query = useProjectCollection(scope, collection, { q, format })
  const items = query.data?.pages.flatMap((page) => page.items) ?? []
  const searchable = collection === 'work' || collection === 'results'
  const emptyKey = {
    work: 'emptyWork',
    team: 'emptyTeam',
    results: 'emptyResults',
    activity: 'emptyActivity',
  }[collection]
  return (
    <section className="project-collection" aria-label={t('projects.' + collection)}>
      <h2>{t('projects.' + collection)}</h2>
      {searchable && (
        <div className="project-collection-tools">
          <label className="project-search">
            <Search size={17} aria-hidden="true" />
            <input
              value={search}
              maxLength={120}
              aria-label={t(
                collection === 'results' ? 'projects.searchResults' : 'projects.searchWork',
              )}
              placeholder={t(
                collection === 'results' ? 'projects.searchResults' : 'projects.searchWork',
              )}
              onChange={(event) => setSearch(event.target.value)}
            />
          </label>
        </div>
      )}
      {collection === 'results' && (query.data?.pages[0]?.formats.length ?? 0) > 0 && (
        <div className="project-format-filters" aria-label={t('projects.format')}>
          <button type="button" aria-pressed={!format} onClick={() => setFormat('')}>
            {t('projects.all')}
          </button>
          {query.data?.pages[0]?.formats.map((value) => (
            <button
              type="button"
              key={value}
              aria-pressed={format === value}
              onClick={() => setFormat(value)}
            >
              {i18n.exists('projects.' + value) ? t('projects.' + value) : value}
            </button>
          ))}
        </div>
      )}
      {query.isPending ? (
        <ProjectsSkeleton />
      ) : query.error ? (
        <ProjectQueryError error={query.error} retry={() => void query.refetch()} />
      ) : !items.length ? (
        <DataState title={t(emptyKey ? 'projects.' + emptyKey : 'projects.emptyResults')} />
      ) : collection === 'team' ? (
        <ProjectTeam items={items} onOpen={onOpen} />
      ) : collection === 'activity' ? (
        <ol className="project-activity-list">
          {items.map((item) => (
            <li key={item.id}>
              <button type="button" onClick={() => onOpen(item)}>
                <span className="project-activity-dot" aria-hidden="true" />
                <span>
                  <strong>{resourceTitle(item, t)}</strong>
                  <span>
                    {item.verified === false
                      ? t('projects.unverified')
                      : t('projects.activityRecorded')}
                  </span>
                </span>
                <time dateTime={item.created_at}>
                  {new Intl.DateTimeFormat(i18n.language, {
                    dateStyle: 'medium',
                    timeStyle: 'short',
                  }).format(new Date(item.created_at))}
                </time>
              </button>
            </li>
          ))}
        </ol>
      ) : (
        <ResourceRows items={items} results={collection === 'results'} onOpen={onOpen} />
      )}
      {query.hasNextPage && (
        <Button
          variant="secondary"
          disabled={query.isFetchingNextPage}
          onClick={() => void query.fetchNextPage()}
        >
          {t(query.isFetchingNextPage ? 'projects.loading' : 'projects.more')}
        </Button>
      )}
    </section>
  )
}
function ProjectTeam({
  items,
  onOpen,
}: {
  items: ProjectResource[]
  onOpen: (item: ProjectResource) => void
}) {
  const { t } = useTranslation()
  const divisions = items.filter((item) => item.kind === 'division')
  const assignments = items.filter((item) => item.kind === 'assignment')
  const members = items.filter((item) => item.kind === 'member')
  const known = new Set(divisions.map((item) => item.id))
  const ungrouped = assignments.filter((item) => !item.references.division_id)
  const unknown = assignments.filter(
    (item) =>
      typeof item.references.division_id === 'string' && !known.has(item.references.division_id),
  )
  return (
    <div className="project-team-grid">
      {divisions.map((division) => (
        <section key={division.id}>
          <button type="button" className="project-division-title" onClick={() => onOpen(division)}>
            {division.name}
          </button>
          {division.description && <p>{division.description}</p>}
          {assignments.some((item) => item.references.division_id === division.id) && (
            <ResourceRows
              items={assignments.filter((item) => item.references.division_id === division.id)}
              onOpen={onOpen}
            />
          )}
        </section>
      ))}
      {members.length > 0 && (
        <section>
          <h3>{t('projects.humanMembers')}</h3>
          <ResourceRows items={members} onOpen={onOpen} />
        </section>
      )}
      {ungrouped.length > 0 && (
        <section>
          <h3>{t('projects.ungrouped')}</h3>
          <ResourceRows items={ungrouped} onOpen={onOpen} />
        </section>
      )}
      {unknown.length > 0 && (
        <section>
          <h3>{t('projects.assignment')}</h3>
          <ResourceRows items={unknown} onOpen={onOpen} />
        </section>
      )}
    </div>
  )
}
