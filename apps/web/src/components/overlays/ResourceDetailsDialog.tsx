import { useRef } from 'react'
import { useShell } from '@/app/providers/ShellProvider'
import { useResourceDetail } from '@/hooks/use-workspace-queries'
import { Dialog, DialogContent, DialogTitle, DialogDescription } from '@/components/ui/dialog'
import { DataState, QueryError } from '@/components/feedback/DataState'
import { formatDate } from '@/lib/utils'

export function ResourceDetailsDialog() {
  const { selection, inspect } = useShell()
  const detail = useResourceDetail(selection?.resource, selection?.item.id)
  const returnFocus = useRef<HTMLElement | null>(null)

  return (
    <Dialog
      open={!!selection}
      onOpenChange={(open) => {
        if (!open) inspect(null)
      }}
    >
      <DialogContent
        onOpenAutoFocus={() => {
          returnFocus.current =
            document.activeElement instanceof HTMLElement ? document.activeElement : null
        }}
        onCloseAutoFocus={(event) => {
          event.preventDefault()
          if (returnFocus.current?.isConnected) returnFocus.current.focus()
          else document.querySelector<HTMLButtonElement>('[aria-label="Global search"]')?.focus()
        }}
      >
        <DialogTitle>Resource details</DialogTitle>
        <DialogDescription>Details reported by ARYN for the selected resource.</DialogDescription>
        {detail.isLoading ? (
          <DataState kind="loading" title="Loading resource" />
        ) : detail.error ? (
          <QueryError error={detail.error} retry={() => void detail.refetch()} />
        ) : (
          selection &&
          detail.data && (
            <dl className="detail-list">
              <dt>Name</dt>
              <dd>{detail.data.name}</dd>
              <dt>Resource</dt>
              <dd>{selection.resource}</dd>
              <dt>Status</dt>
              <dd>{detail.data.status ?? 'Unavailable'}</dd>
              <dt>Recorded</dt>
              <dd>{formatDate(detail.data.created_at)}</dd>
              <dt>Verification</dt>
              <dd>
                {detail.data.verified == null
                  ? 'Unavailable'
                  : detail.data.verified
                    ? 'Verified by backend'
                    : 'Unverified'}
              </dd>
              <dt>Resource ID</dt>
              <dd className="mono">{detail.data.id}</dd>
              {detail.data.description && (
                <>
                  <dt>Description</dt>
                  <dd>{detail.data.description}</dd>
                </>
              )}
            </dl>
          )
        )}
      </DialogContent>
    </Dialog>
  )
}
