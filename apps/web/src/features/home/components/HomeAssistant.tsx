import { useState, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from '@tanstack/react-router'
import { Button } from '@/components/ui/button'
import { useChatCapability, useChatScope, useSendTurn } from '@/features/chat/hooks/useChat'
import { useConsentGate } from '@/features/chat/hooks/useConsentGate'
import { ProviderConsentDialog } from '@/features/chat/components/ProviderConsentDialog'
import { ModelPicker } from '@/features/chat/components/ModelPicker'
import { HomeComposer } from './HomeComposer'
import '@/features/chat/chat.css'

export function HomeAssistant({ compact, children }: { compact: boolean; children: ReactNode }) {
  const { t } = useTranslation()
  const scope = useChatScope()
  const capability = useChatCapability(scope)
  const send = useSendTurn(scope)
  const navigate = useNavigate()
  const [input, setInput] = useState('')
  const [selection, setSelection] = useState('')
  const available =
    capability.data?.models.filter((item) => item.available || item.verifiable) ?? []
  const model = selection || (available.length > 0 ? (available[0]?.id ?? '') : '')
  function accepted(conversation: { id: string }) {
    void navigate({ to: '/chat/$conversationId', params: { conversationId: conversation.id } })
  }
  const gate = useConsentGate(scope, model, (message) => {
    if (!send.isPending && !send.uncertain)
      send.mutate(
        { message, model, expected_revision: 0, allow_remote_model: false },
        { onSuccess: accepted },
      )
  })
  const ready = Boolean(
    capability.data?.can_send &&
    available.some((m) => m.id === model) &&
    gate.consent.data?.models[model] &&
    !gate.consent.isError,
  )
  const help = send.uncertain
    ? t('composer.locked')
    : capability.isPending || gate.consent.isPending
      ? t('composer.checking')
      : gate.consent.isError
        ? t('consent.loadFailed')
        : !capability.data?.permitted
          ? t('composer.denied')
          : !model && available.length > 0
            ? t('composer.choose')
            : !ready
              ? t('composer.unavailable')
              : undefined
  return (
    <>
      <HomeComposer
        compact={compact}
        value={input}
        onChange={setInput}
        disabled={!ready || send.uncertain}
        pending={send.isPending}
        readOnly={send.uncertain}
        help={help}
        onContinue={gate.submit}
        controls={
          <ModelPicker
            capability={capability.data}
            model={model}
            onModel={setSelection}
            disabled={send.isPending || send.uncertain}
          />
        }
      />
      {send.isError && (
        <p role="alert" className="chat-error">
          {send.error.message}
          {send.uncertain && (
            <Button
              variant="ghost"
              size="sm"
              disabled={send.isPending}
              onClick={() => send.retryOriginal({ onSuccess: accepted })}
            >
              {t('chat.retry')}
            </Button>
          )}
        </p>
      )}
      {(capability.isError ||
        gate.consent.isError ||
        (!capability.isPending && !capability.data?.can_send)) && (
        <Button
          variant="ghost"
          size="sm"
          onClick={() => {
            void capability.refetch()
            void gate.consent.refetch()
          }}
        >
          {t('chat.check')}
        </Button>
      )}
      {children}
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
