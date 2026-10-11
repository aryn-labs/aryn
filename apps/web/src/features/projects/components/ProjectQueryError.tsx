import { useTranslation } from 'react-i18next'
import { DataState, QueryError } from '@/components/feedback/DataState'
import { ApiError } from '@/lib/api/client'

export function ProjectQueryError({ error, retry }: { error: Error; retry: () => void }) {
  const { t } = useTranslation()
  if (error instanceof ApiError && [501, 503].includes(error.status)) {
    return (
      <DataState kind="unavailable" description={t('projects.errorUnavailable')} retry={retry} />
    )
  }
  return <QueryError error={error} retry={retry} />
}
