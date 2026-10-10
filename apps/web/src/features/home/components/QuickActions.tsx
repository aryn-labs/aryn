import { Bot, LayoutGrid, Workflow } from 'lucide-react'
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
  return (
    <div className="home-quick-actions" role="group" aria-label="Quick actions">
      <button className="home-pill" disabled={!canAgent} onClick={() => onCreate('agent')}>
        <Bot size={15} aria-hidden="true" />
        Create Agent
      </button>
      <button className="home-pill" disabled={!canWorkflow} onClick={() => onCreate('workflow')}>
        <Workflow size={15} aria-hidden="true" />
        Build Workflow
      </button>
      <button
        className="home-pill"
        disabled={!canAgent && !canWorkflow}
        onClick={() => onCreate(undefined, true)}
      >
        <LayoutGrid size={15} aria-hidden="true" />
        Start from Scratch
      </button>
    </div>
  )
}
