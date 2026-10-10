import {
  ArrowUpRight,
  Bot,
  CirclePlay,
  FileText,
  FlaskConical,
  ShieldCheck,
  Workflow,
  Radio,
} from 'lucide-react'
import type { HomeResource } from '../lib/home-state'
import { formatDate } from '@/lib/utils'
import { statusLabel } from '../lib/home-labels'
import { useTranslation } from 'react-i18next'
const icons = {
  agent: Bot,
  workflow: Workflow,
  run: CirclePlay,
  audit: FileText,
  version: ShieldCheck,
  incident: Radio,
  'workflow-run': Workflow,
  bench: FlaskConical,
}
export function HomeResourceRow({
  item,
  description,
  label,
  onOpen,
}: {
  item: HomeResource
  description?: string
  label?: string
  onOpen: (item: HomeResource) => void
}) {
  const { t } = useTranslation()
  const Icon = icons[item.kind]
  return (
    <button
      className={`home-resource-row ${item.kind === 'agent' ? 'home-agent-row' : ''}`}
      aria-label={t('common.inspect', { name: item.name })}
      onClick={() => onOpen(item)}
    >
      <span className="home-row-icon">
        <Icon size={17} aria-hidden="true" />
      </span>
      <span className="home-row-main">
        <span className="home-row-name">{item.name}</span>
        <span className="home-row-description">
          {description ??
            label ??
            t(`common.${item.kind}`, {
              defaultValue:
                item.kind === 'bench'
                  ? 'Bench'
                  : item.kind === 'incident'
                    ? 'Relay'
                    : t('common.run'),
            })}
          {item.createdAt ? ` · ${formatDate(item.createdAt)}` : ''}
        </span>
      </span>
      <span className="home-row-end">
        {item.status && <span className="home-status">{statusLabel(item.status)}</span>}
        <ArrowUpRight size={14} aria-hidden="true" />
      </span>
    </button>
  )
}
