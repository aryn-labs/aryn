import { useTranslation } from 'react-i18next'
import { useRef } from 'react'
import { Link } from '@tanstack/react-router'
import { Dialog, DialogContent, DialogTitle, DialogDescription } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import type { ProviderConsent } from '../hooks/useChatSettings'
export function ProviderConsentDialog({
  provider,
  pending,
  error,
  onConfirm,
  onClose,
}: {
  provider?: ProviderConsent
  pending: boolean
  error: boolean
  onConfirm: () => void
  onClose: () => void
}) {
  const { t } = useTranslation()
  const returnFocus = useRef<HTMLElement | null>(null)
  return (
    <Dialog
      open={Boolean(provider)}
      onOpenChange={(open) => {
        if (!open && !pending) onClose()
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
        }}
        onEscapeKeyDown={(event) => {
          if (pending) event.preventDefault()
        }}
        onPointerDownOutside={(event) => {
          if (pending) event.preventDefault()
        }}
      >
        <DialogTitle>{t('consent.title')}</DialogTitle>
        <DialogDescription className="consent-description">
          {t('consent.description', { provider: provider?.name })}
        </DialogDescription>
        <p className="consent-settings">
          <Link to="/settings" onClick={onClose}>
            {t('consent.manage')}
          </Link>
        </p>
        {error && (
          <p role="alert" className="chat-error">
            {t('consent.failed')}
          </p>
        )}
        <div className="consent-actions">
          <Button variant="secondary" disabled={pending} onClick={onClose}>
            {t('consent.decline')}
          </Button>
          <Button disabled={pending} onClick={onConfirm}>
            {t(pending ? 'settings.saving' : 'consent.confirm')}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}
