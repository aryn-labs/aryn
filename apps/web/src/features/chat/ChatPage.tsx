import { translate as tr } from '@/i18n'
import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useParams } from '@tanstack/react-router'
import { useQuery } from '@tanstack/react-query'
import { History, Plus } from 'lucide-react'
import { useWorkspace } from '@/app/providers/WorkspaceProvider'
import { Button } from '@/components/ui/button'
import { DataState, QueryError } from '@/components/feedback/DataState'
import { HomeComposer } from '@/features/home/components/HomeComposer'
import { chatKey, getConversation } from './lib/chat-api'
import { useChatCapability, useChatScope, useSendTurn } from './hooks/useChat'
import { ChatHistory } from './components/ChatHistory'
import { ChatMessages } from './components/ChatMessages'
import { ModelPicker } from './components/ModelPicker'
import { ProviderConsentDialog } from './components/ProviderConsentDialog'
import { useConsentGate } from './hooks/useConsentGate'
import './chat.css'

export function ChatPage() {
  const { t } = useTranslation()
  const { conversationId } = useParams({ strict: false })
  const scope = useChatScope()
  return (
    <main
      id="main-content"
      tabIndex={-1}
      className="chat-workspace"
      aria-label={t('chat.assistant')}
    >
      <ChatContent
        key={`${scope.user}:${scope.organization}:${scope.project}:${conversationId}`}
        id={conversationId ?? ''}
      />
    </main>
  )
}
function ChatContent({ id }: { id: string }) {
  const { t } = useTranslation()
  const workspace = useWorkspace()
  const scope = useChatScope()
  const capability = useChatCapability(scope)
  const [input, setInput] = useState('')
  const [historyOpen, setHistoryOpen] = useState(false)
  const send = useSendTurn(scope, id)
  const viewport = useRef<HTMLDivElement>(null)
  const pinned = useRef(true)
  const conversation = useQuery({
    queryKey: [...chatKey(scope), id],
    queryFn: ({ signal }) => getConversation(scope, id, signal),
    enabled: Boolean(id && scope.user && scope.project),
    retry: false,
    refetchInterval: (query) => (query.state.data?.status === 'processing' ? 1000 : false),
  })
  const data = conversation.data
  const [selectedModel, setSelectedModel] = useState('')
  const currentModel = selectedModel || data?.model || ''
  const gate = useConsentGate(scope, currentModel, (message) => {
    if (!data || send.isPending || send.uncertain) return
    send.mutate(
      { message, model: currentModel, expected_revision: data.revision, allow_remote_model: false },
      {
        onSuccess: (updated) => {
          setInput('')
          setSelectedModel(updated.model)
          requestAnimationFrame(() => document.getElementById('chat-message')?.focus())
        },
      },
    )
  })
  useEffect(() => {
    if (pinned.current && viewport.current)
      viewport.current.scrollTop = viewport.current.scrollHeight
  }, [data?.messages.length, data?.status])
  if (workspace.error) return <QueryError error={workspace.error} retry={workspace.retry} />
  if (!workspace.loading && !scope.user)
    return (
      <DataState
        kind="unauthorized"
        title={tr('ui.conversation_unavailable')}
        description={tr('ui.sign_in_and_select_the_conversation_s_project')}
      />
    )
  if (!workspace.loading && !scope.project)
    return (
      <DataState
        kind="unavailable"
        title={tr('ui.select_a_project')}
        description={tr('ui.select_an_accessible_project_to_restore_its_conversations')}
      />
    )
  if (workspace.loading || conversation.isPending)
    return (
      <DataState
        kind="loading"
        title={tr('ui.loading_conversation')}
        description={tr('ui.restoring_saved_messages')}
      />
    )
  if (conversation.isError)
    return <QueryError error={conversation.error} retry={() => void conversation.refetch()} />
  if (!data || !scope.user)
    return (
      <DataState
        kind="unauthorized"
        title={tr('ui.conversation_unavailable')}
        description={tr('ui.sign_in_and_select_the_conversation_s_project')}
      />
    )
  const ready =
    data.can_send &&
    Boolean(capability.data?.can_send) &&
    Boolean(gate.consent.data?.models[currentModel]) &&
    !gate.consent.isError &&
    capability.data?.models.some((m) => m.id === currentModel && (m.available || m.verifiable))
  return (
    <>
      <header className="chat-header">
        <div>
          <h1>{t('chat.assistant')}</h1>
          <p className="chat-subtitle">
            {data.title.length > 52 ? data.title.slice(0, 48) + '…' : data.title}
          </p>
        </div>
        <div className="chat-header-actions">
          <Button
            variant="ghost"
            size="icon"
            aria-label={t('chat.history')}
            onClick={() => setHistoryOpen(true)}
          >
            <History size={18} />
          </Button>
          <Button variant="secondary" size="sm" asChild>
            <Link to="/">
              <Plus size={16} aria-hidden="true" /> {t('chat.new')}
            </Link>
          </Button>
        </div>
      </header>
      <div
        className="chat-scroll"
        ref={viewport}
        onScroll={() => {
          const node = viewport.current
          if (node) pinned.current = node.scrollHeight - node.scrollTop - node.clientHeight < 80
        }}
      >
        <div className="chat-reading">
          <ChatMessages conversation={data} />
          <div role="status" aria-live="polite" className="chat-process-status">
            {data.status === 'processing' ? (
              t('chat.generating')
            ) : data.status === 'completed' ? (
              <span className="sr-only">{t('chat.received')}</span>
            ) : (
              t('chat.unresolved')
            )}
          </div>
        </div>
      </div>
      <div className="chat-input-area">
        <div className="chat-reading">
          {send.isError && (
            <p className="chat-error" role="alert">
              {send.error.message}{' '}
              <button onClick={() => void conversation.refetch()}>{t('chat.refresh')}</button>
              {send.uncertain && (
                <button
                  disabled={send.isPending}
                  onClick={() => send.retryOriginal({ onSuccess: () => setInput('') })}
                >
                  {t('chat.retry')}
                </button>
              )}
            </p>
          )}
          {!ready && data.status === 'completed' && (
            <p className="chat-availability">
              {capability.isPending
                ? t('composer.checking')
                : gate.consent.isError
                  ? t('consent.loadFailed')
                  : t('composer.unavailable')}{' '}
              <button
                onClick={() => {
                  void capability.refetch()
                  void gate.consent.refetch()
                }}
              >
                {t('chat.check')}
              </button>
            </p>
          )}
          <HomeComposer
            compact
            followUp
            value={input}
            onChange={setInput}
            disabled={!ready || send.uncertain}
            pending={send.isPending}
            readOnly={send.uncertain}
            help={
              send.uncertain
                ? t('composer.locked')
                : !ready
                  ? t(data.status === 'processing' ? 'chat.generating' : 'composer.unavailable')
                  : undefined
            }
            onContinue={gate.submit}
            controls={
              <ModelPicker
                capability={capability.data}
                model={currentModel}
                onModel={setSelectedModel}
                disabled={send.isPending || send.uncertain || data.status === 'processing'}
              />
            }
          />
        </div>
      </div>
      <ChatHistory scope={scope} open={historyOpen} onClose={() => setHistoryOpen(false)} />
      <ProviderConsentDialog
        provider={gate.provider}
        pending={gate.consent.grant.isPending}
        error={gate.consent.grant.isError}
        onConfirm={gate.confirm}
        onClose={gate.close}
      />
    </>
  )
}
