import { Clock, Code, Webhook, Plug } from 'lucide-react'
import type { TriggerCapabilities } from './api'
export const triggerRegistry = [
  { kind: 'interval', icon: Clock, admission: 'core_schedule', preview: true },
  { kind: 'daily', icon: Clock, admission: 'core_schedule', preview: true },
  { kind: 'weekly', icon: Clock, admission: 'core_schedule', preview: true },
  { kind: 'cron', icon: Code, admission: 'core_cron', preview: true },
  { kind: 'webhook', icon: Webhook, admission: 'authenticated_signal', preview: false },
  { kind: 'mcp', icon: Plug, admission: 'unavailable_adapter', preview: false },
] as const
export function triggerAvailable(kind: string, capabilities?: TriggerCapabilities) {
  return (
    !!capabilities &&
    kind !== 'mcp' &&
    capabilities.kinds.includes(kind) &&
    (kind !== 'webhook' || capabilities.webhook_available)
  )
}
