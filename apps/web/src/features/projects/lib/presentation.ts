import { activityLabel } from '@/features/home/lib/home-labels'
import type { ProjectResource } from './api'

export function resourceTitle(item: ProjectResource, t: (key: string) => string) {
  if (item.kind === 'audit')
    return item.name === 'core.project.created'
      ? t('projects.eventCreated')
      : item.name === 'core.project.updated'
        ? t('projects.eventUpdated')
        : activityLabel(item.name)
  return item.name || t('projects.' + item.kind)
}
export function reference(item: ProjectResource, key: string) {
  const value = item.references[key]
  return typeof value === 'string' || typeof value === 'number' ? String(value) : undefined
}
