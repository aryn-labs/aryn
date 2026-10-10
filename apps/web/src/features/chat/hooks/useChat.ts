import { useEffect, useRef } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useWorkspace } from '@/app/providers/WorkspaceProvider'
import { request } from '@/lib/api/client'
import {
  capabilitySchema,
  chatKey,
  chatPath,
  scoped,
  sendTurn,
  DeliveryUnknownError,
  type ChatScope,
  type TurnInput,
} from '../lib/chat-api'

export function useChatScope(): ChatScope {
  const { context, project } = useWorkspace()
  return {
    user: context?.user.id ?? '',
    organization: context?.organization.id ?? '',
    project: project?.id ?? '',
  }
}
export function useChatCapability(scope: ChatScope) {
  return useQuery({
    queryKey: [...chatKey(scope), 'capability'],
    queryFn: async ({ signal }) =>
      scoped(await request(chatPath(scope) + '/capability', capabilitySchema, { signal }), scope),
    enabled: Boolean(scope.user && scope.project),
    retry: false,
    staleTime: 10_000,
  })
}
export function useSendTurn(scope: ChatScope, id?: string) {
  const { csrf } = useWorkspace()
  const client = useQueryClient()
  const pending = useRef<{ signature: string; input: TurnInput; uncertain: boolean } | null>(null)
  const controller = useRef<AbortController | null>(null)
  const inFlight = useRef(false)
  const mounted = useRef(false)
  useEffect(() => {
    mounted.current = true
    return () => {
      mounted.current = false
      controller.current?.abort()
    }
  }, [])
  const mutation = useMutation({
    mutationFn: async (value: Omit<TurnInput, 'idempotency_key'>) => {
      if (!mounted.current || !csrf || !scope.project || !scope.user)
        throw new Error('Select an accessible project and sign in first.')
      const signature = JSON.stringify(value)
      if (pending.current?.uncertain && pending.current.signature !== signature)
        throw new DeliveryUnknownError()
      if (pending.current?.signature !== signature)
        pending.current = {
          signature,
          input: { ...value, idempotency_key: crypto.randomUUID() },
          uncertain: false,
        }
      controller.current = new AbortController()
      let result
      try {
        result = await sendTurn(scope, csrf, pending.current.input, id, controller.current.signal)
      } catch (error) {
        if (error instanceof DeliveryUnknownError) pending.current.uncertain = true
        throw error
      }
      if (controller.current.signal.aborted)
        throw new Error('Workspace changed. Check conversation history.')
      return result
    },
    onSuccess(result) {
      pending.current = null
      client.setQueryData([...chatKey(scope), result.id], result)
      void client.invalidateQueries({ queryKey: [...chatKey(scope), 'history'] })
    },
    onSettled() {
      inFlight.current = false
    },
    retry: false,
  })
  return {
    ...mutation,
    mutate(
      value: Parameters<typeof mutation.mutate>[0],
      options?: Parameters<typeof mutation.mutate>[1],
    ) {
      // React state updates are asynchronous; latch the first submit in this event turn.
      if (inFlight.current) return
      inFlight.current = true
      mutation.mutate(value, options)
    },
    uncertain: Boolean(pending.current?.uncertain),
    retryOriginal(options?: Parameters<typeof mutation.mutate>[1]) {
      if (pending.current && !inFlight.current) {
        inFlight.current = true
        mutation.mutate(
          JSON.parse(pending.current.signature) as Omit<TurnInput, 'idempotency_key'>,
          options,
        )
      }
    },
  }
}
