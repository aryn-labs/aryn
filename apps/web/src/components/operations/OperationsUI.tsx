import { useState, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { Dialog, DialogContent, DialogTitle, DialogDescription } from '@/components/ui/dialog'
import './operations.css'
import { Button } from '@/components/ui/button'

export function OperationsBoundary() {
  const { t } = useTranslation(),
    [open, setOpen] = useState(false)
  return (
    <>
      <Button variant="secondary" onClick={() => setOpen(true)}>
        {t('operations.boundary')}
      </Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogTitle>{t('operations.boundary')}</DialogTitle>
          <DialogDescription>{t('operations.observation')}</DialogDescription>
          {[
            'localBoundary',
            'noTelemetry',
            'retryHelp',
            'unknown',
            'webhookAuth',
            'webhookUnavailable',
          ].map((key) => (
            <p className="op-note" key={key}>
              {t('operations.' + key)}
            </p>
          ))}
        </DialogContent>
      </Dialog>
    </>
  )
}

export function Status({ value }: { value: string }) {
  const { t } = useTranslation()
  return (
    <span className="op-status" data-state={value}>
      <span aria-hidden="true">●</span>
      {t('operations.states.' + value, { defaultValue: value })}
    </span>
  )
}
export function OperationsDrawer({
  title,
  description,
  children,
  onClose,
}: {
  title: string
  description: string
  children: ReactNode
  onClose: () => void
}) {
  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open) onClose()
      }}
    >
      <DialogContent className="op-drawer">
        <header>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>{description}</DialogDescription>
        </header>
        <div className="op-drawer-body">{children}</div>
      </DialogContent>
    </Dialog>
  )
}
export function Facts({ values }: { values: [string, ReactNode][] }) {
  const { t } = useTranslation()
  return (
    <dl className="op-facts">
      {values.map(([label, value]) => (
        <div key={label}>
          <dt>{label}</dt>
          <dd>{value ?? t('operations.unavailable')}</dd>
        </div>
      ))}
    </dl>
  )
}
export function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="op-field">
      <span>{label}</span>
      {children}
    </label>
  )
}
export function Tabs({
  items,
  value,
  onChange,
}: {
  items: [string, string][]
  value: string
  onChange: (value: string) => void
}) {
  return (
    <nav className="op-tabs" aria-label={items.map((item) => item[1]).join(', ')}>
      {items.map(([id, title]) => (
        <button key={id} aria-pressed={id === value} onClick={() => onChange(id)}>
          {title}
        </button>
      ))}
    </nav>
  )
}
