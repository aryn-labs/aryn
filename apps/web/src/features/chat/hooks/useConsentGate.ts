import { useEffect, useRef, useState } from 'react'
import { useProviderConsent } from './useChatSettings'
import type { ChatScope } from '../lib/chat-api'

// Only the signed server receipt authorizes subsequent transfers.
export function useConsentGate(scope: ChatScope, model: string, onSend: (message: string) => void) {
  const consent = useProviderConsent(scope)
  const [message, setMessage] = useState<string | null>(null)
  const mounted = useRef(false)
  useEffect(() => {
    mounted.current = true
    return () => {
      mounted.current = false
    }
  }, [])
  const provider = consent.data?.models[model]
  function submit(value: string) {
    if (!provider || consent.isError || consent.grant.isPending) return
    if (!provider.remote || provider.consented) onSend(value)
    else {
      consent.grant.reset()
      setMessage(value)
    }
  }
  function confirm() {
    if (!provider || message === null || consent.grant.isPending) return
    consent.grant.mutate(
      { model, policy: provider.policy },
      {
        onSuccess: (data) => {
          if (mounted.current && data.models[model]?.consented) {
            setMessage(null)
            onSend(message)
          }
        },
      },
    )
  }
  return {
    consent,
    submit,
    provider: message !== null ? provider : undefined,
    confirm,
    close: () => setMessage(null),
  }
}
