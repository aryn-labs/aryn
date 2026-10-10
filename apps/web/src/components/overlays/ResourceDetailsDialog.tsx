import { translate as tr } from '@/i18n'
import { useTranslation } from 'react-i18next'
import { useRef } from 'react'
import { useShell } from '@/app/providers/ShellProvider'
import { useResourceDetail } from '@/hooks/use-workspace-queries'
import { Dialog, DialogContent, DialogTitle, DialogDescription } from '@/components/ui/dialog'
import { DataState, QueryError } from '@/components/feedback/DataState'
import { formatDate } from '@/lib/utils'

export function ResourceDetailsDialog() {
  useTranslation()

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
          else document.querySelector<HTMLButtonElement>('.global-search-trigger')?.focus()
        }}
      >
        <DialogTitle>{tr('ui.resource_details')}</DialogTitle>
        <DialogDescription>
          {tr('ui.details_reported_by_aryn_for_the_selected_resource')}
        </DialogDescription>
        {detail.isLoading ? (
          <DataState kind="loading" title={tr('ui.loading_resource')} />
        ) : detail.error ? (
          <QueryError error={detail.error} retry={() => void detail.refetch()} />
        ) : (
          selection &&
          detail.data && (
            <dl className="detail-list">
              <dt>{tr('ui.name')}</dt>
              <dd>{detail.data.name}</dd>
              <dt>{tr('ui.resource')}</dt>
              <dd>{selection.resource}</dd>
              <dt>{tr('ui.status')}</dt>
              <dd>{detail.data.status ?? 'Unavailable'}</dd>
              <dt>{tr('ui.recorded')}</dt>
              <dd>{formatDate(detail.data.created_at)}</dd>
              <dt>{tr('ui.verification')}</dt>
              <dd>
                {detail.data.verified == null
                  ? 'Unavailable'
                  : detail.data.verified
                    ? tr('ui.verified_by_backend')
                    : 'Unverified'}
              </dd>
              <dt>{tr('ui.resource_id')}</dt>
              <dd className="mono">{detail.data.id}</dd>
              {detail.data.description && (
                <>
                  <dt>{tr('ui.description')}</dt>
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
