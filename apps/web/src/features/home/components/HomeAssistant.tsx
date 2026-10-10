import { useRef, useState, type ReactNode } from 'react'
import { ArrowLeft, Bot, MessageSquare, Workflow } from 'lucide-react'
import { Button } from '@/components/ui/button'
import type { CreationKind } from '../lib/home-state'
import { HomeComposer } from './HomeComposer'

// There is no scoped conversational endpoint in the current ARYN API.
// These are unsent user inputs, never assistant messages or an execution request.
export function HomeAssistant({
  compact,
  canAgent,
  canWorkflow,
  onDraft,
  children,
}: {
  compact: boolean
  canAgent: boolean
  canWorkflow: boolean
  onDraft: (kind: CreationKind, goal: string) => void
  children: ReactNode
}) {
  const [input, setInput] = useState('')
  const [message, setMessage] = useState('')
  const [followUp, setFollowUp] = useState('')
  const heading = useRef<HTMLHeadingElement>(null)
  function openConversation(value: string) {
    setMessage(value)
    requestAnimationFrame(() => heading.current?.focus())
  }
  function returnToOverview() {
    setMessage('')
    setFollowUp('')
    requestAnimationFrame(() => document.getElementById('home-goal')?.focus())
  }
  if (!message)
    return (
      <>
        <HomeComposer
          compact={compact}
          value={input}
          onChange={setInput}
          onContinue={openConversation}
        />
        {children}
      </>
    )
  return (
    <section className="home-conversation" aria-labelledby="conversation-heading">
      <div className="home-conversation-heading">
        <h2 id="conversation-heading" tabIndex={-1} ref={heading}>
          <MessageSquare size={20} aria-hidden="true" />
          Assistant
        </h2>
        <Button variant="ghost" size="sm" onClick={returnToOverview}>
          <ArrowLeft size={15} aria-hidden="true" />
          Back to overview
        </Button>
      </div>
      <ol className="home-messages" aria-label="Conversation messages">
        <li className="home-message">
          <div className="home-message-heading">
            <strong>You</strong>
            <span>Not sent</span>
          </div>
          <p>{message}</p>
        </li>
      </ol>
      <div className="home-assistant-unavailable" role="status">
        <h3>Assistant unavailable</h3>
        <p>
          This server has no conversation API. Your message has not been sent and no AI response has
          been generated.
        </p>
      </div>
      {(canAgent || canWorkflow) && (
        <div className="home-draft-actions">
          <p>Use your message as a starting brief instead.</p>
          <div>
            <Button
              variant="secondary"
              disabled={!canAgent}
              onClick={() => onDraft('agent', message)}
            >
              <Bot size={16} aria-hidden="true" />
              Create Agent draft
            </Button>
            <Button
              variant="secondary"
              disabled={!canWorkflow}
              onClick={() => onDraft('workflow', message)}
            >
              <Workflow size={16} aria-hidden="true" />
              Create Workflow draft
            </Button>
          </div>
        </div>
      )}
      <HomeComposer
        compact
        followUp
        value={followUp}
        onChange={setFollowUp}
        onContinue={() => undefined}
      />
    </section>
  )
}
