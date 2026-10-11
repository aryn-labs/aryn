import { useEffect, useRef } from 'react'
import { useProviderConsent } from './useChatSettings'
import type { ChatScope } from '../lib/chat-api'

// Direct model transfer authorization with automatic background consent recording.
export function useConsentGate(scope: ChatScope, model: string, onSend: (message: string) => void) {
  const consent = useProviderConsent(scope)
  const mounted = useRef(false)
  useEffect(() => {
    mounted.current = true
    return () => {
      mounted.current = false
    }
  }, [])
  const provider = consent.data?.models[model]

  // Automatically record consent in background when model is active
  useEffect(() => {
    if (
      model &&
      provider?.remote &&
      !provider.consented &&
      !consent.grant.isPending &&
      !consent.isError
    ) {
      consent.grant.mutate({ model, policy: provider.policy })
    }
  }, [model, provider?.remote, provider?.consented, provider?.policy, consent.grant, consent.isError])

  function submit(value: string) {
    if (!provider || consent.isError) return
    if (!provider.remote || provider.consented) {
      onSend(value)
    } else {
      consent.grant.mutate(
        { model, policy: provider.policy },
        {
          onSuccess: (data) => {
            if (mounted.current && data.models[model]?.consented) {
              onSend(value)
            }
          },
        },
      )
    }
  }

  return {
    consent,
    submit,
    provider: undefined,
    confirm: () => undefined,
    close: () => undefined,
  }
}
