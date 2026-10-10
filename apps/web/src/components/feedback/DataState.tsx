import { translate as tr } from '@/i18n'
import { useTranslation } from 'react-i18next'
import { AlertCircle, Inbox, LoaderCircle, LockKeyhole, Unplug } from 'lucide-react'
import { ApiError } from '@/lib/api/client'
import { Button } from '@/components/ui/button'
export function DataState({
  kind = 'empty',
  title,
  description,
  retry,
}: {
  kind?: 'loading' | 'empty' | 'error' | 'unauthorized' | 'unavailable'
  title?: string
  description?: string
  retry?: () => void
}) {
  useTranslation()

  const Icon = {
    loading: LoaderCircle,
    empty: Inbox,
    error: AlertCircle,
    unauthorized: LockKeyhole,
    unavailable: Unplug,
  }[kind]
  return (
    <div
      className="data-state"
      role={kind === 'error' || kind === 'unauthorized' ? 'alert' : 'status'}
    >
      <span className="state-icon">
        <Icon size={23} className={kind === 'loading' ? 'animate-spin' : ''} />
      </span>
      <h3>
        {title ??
          {
            loading: tr('ui.loading_workspace'),
            empty: tr('ui.nothing_here_yet'),
            error: tr('ui.unable_to_load_data'),
            unauthorized: tr('ui.access_required'),
            unavailable: tr('ui.not_available_yet'),
          }[kind]}
      </h3>
      {description && <p>{description}</p>}
      {retry && (
        <Button variant="secondary" size="sm" onClick={retry}>
          {tr('ui.try_again')}
        </Button>
      )}
    </div>
  )
}
export function QueryError({ error, retry }: { error: Error; retry: () => void }) {
  useTranslation()

  const unauthorized = error instanceof ApiError && (error.status === 401 || error.status === 403)
  return (
    <>
      <DataState
        kind={unauthorized ? 'unauthorized' : 'error'}
        description={error.message}
        retry={retry}
      />
      {error instanceof ApiError && error.loginUrl && (
        <div className="text-center pb-6">
          <Button asChild>
            <a href={error.loginUrl}>{tr('ui.sign_in_to_aryn')}</a>
          </Button>
        </div>
      )}
    </>
  )
}
