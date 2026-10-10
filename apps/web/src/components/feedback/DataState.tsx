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
            loading: 'Loading workspace',
            empty: 'Nothing here yet',
            error: 'Unable to load data',
            unauthorized: 'Access required',
            unavailable: 'Not available yet',
          }[kind]}
      </h3>
      {description && <p>{description}</p>}
      {retry && (
        <Button variant="secondary" size="sm" onClick={retry}>
          Try again
        </Button>
      )}
    </div>
  )
}
export function QueryError({ error, retry }: { error: Error; retry: () => void }) {
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
            <a href={error.loginUrl}>Sign in to ARYN</a>
          </Button>
        </div>
      )}
    </>
  )
}
