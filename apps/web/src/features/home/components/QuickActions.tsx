import { Bot, Plug, Workflow } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Dialog, DialogContent, DialogTitle, DialogDescription } from '@/components/ui/dialog'
import type { CreationKind } from '../lib/home-state'
export function QuickActions({
  canAgent,
  canWorkflow,
  onCreate,
}: {
  canAgent: boolean
  canWorkflow: boolean
  onCreate: (kind?: CreationKind, scratch?: boolean) => void
}) {
  const { t } = useTranslation()
  const [unavailable, setUnavailable] = useState(false)
  return (
    <>
      <div className="home-quick-actions" role="group" aria-label={t('home.quick')}>
        <button className="home-pill" disabled={!canAgent} onClick={() => onCreate('agent')}>
          <Bot size={15} aria-hidden="true" />
          {t('home.createAgent')}
        </button>
        <button className="home-pill" disabled={!canWorkflow} onClick={() => onCreate('workflow')}>
          <Workflow size={15} aria-hidden="true" />
          {t('home.createWorkflow')}
        </button>
        <button className="home-pill" onClick={() => setUnavailable(true)}>
          <Plug size={15} aria-hidden="true" />
          {t('home.connect')}
        </button>
      </div>
      <Dialog open={unavailable} onOpenChange={setUnavailable}>
        <DialogContent>
          <DialogTitle>{t('home.connect')}</DialogTitle>
          <DialogDescription className="consent-description">
            {t('home.toolsUnavailable')}
          </DialogDescription>
        </DialogContent>
      </Dialog>
    </>
  )
}
