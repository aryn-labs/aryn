import { useEffect, useRef } from 'react'
import { useMutation, useQueryClient, type InfiniteData } from '@tanstack/react-query'
import { useWorkspace } from '@/app/providers/WorkspaceProvider'
import { ApiError } from '@/lib/api/client'
import {
  chatKey,
  changeConversation,
  MetadataUnknownError,
  type ChatScope,
  type ConversationChange,
  type ConversationMetadata,
  type historySchema,
} from '../lib/chat-api'
import type { z } from '@/lib/types/validation'

type History = z.infer<typeof historySchema>
type Change = {
  id: string
  method: 'PATCH' | 'DELETE'
  input: Omit<ConversationChange, 'idempotency_key'>
}
export function useConversationChange(scope: ChatScope, onDeleted: (id: string) => void) {
  const { csrf } = useWorkspace()
  const client = useQueryClient()
  const mounted = useRef(false)
  const inFlight = useRef(false)
  const controller = useRef<AbortController | null>(null)
  const original = useRef<{
    signature: string
    value: Change
    input: ConversationChange
    uncertain: boolean
  } | null>(null)
  useEffect(() => {
    mounted.current = true
    return () => {
      mounted.current = false
      controller.current?.abort()
    }
  }, [])
  const mutation = useMutation({
    mutationFn: async (value: Change) => {
      if (!mounted.current || !csrf || !scope.user || !scope.project)
        throw new ApiError(401, 'errors.session')
      const signature = JSON.stringify(value)
      if (original.current?.uncertain && original.current.signature !== signature)
        throw new MetadataUnknownError()
      if (original.current?.signature !== signature)
        original.current = {
          signature,
          value,
          input: { ...value.input, idempotency_key: crypto.randomUUID() },
          uncertain: false,
        }
      controller.current = new AbortController()
      try {
        return await changeConversation(
          scope,
          csrf,
          value.id,
          value.method,
          original.current.input,
          controller.current.signal,
        )
      } catch (error) {
        if (error instanceof MetadataUnknownError) original.current.uncertain = true
        throw error
      }
    },
    onSuccess: async (result: ConversationMetadata) => {
      if (!mounted.current) return
      original.current = null
      const key = chatKey(scope)
      // Abort old reads before applying an acknowledgement so stale pages cannot restore a deleted row.
      await Promise.all(
        ['history', 'recent', result.id].map((part) =>
          client.cancelQueries({ queryKey: [...key, part] }),
        ),
      )
      if (!mounted.current) return
      const update = (data: History): History => ({
        ...data,
        items: result.deleted
          ? data.items.filter((item) => item.id !== result.id)
          : data.items.map((item) => (item.id === result.id ? { ...item, ...result } : item)),
      })
      client.setQueryData<InfiniteData<History>>([...key, 'history'], (data) =>
        data ? { ...data, pages: data.pages.map(update) } : data,
      )
      client.setQueryData<History>([...key, 'recent'], (data) => (data ? update(data) : data))
      if (result.deleted) {
        onDeleted(result.id)
        client.removeQueries({ queryKey: [...key, result.id], exact: true })
      } else {
        client.setQueryData([...key, result.id], (data: Record<string, unknown> | undefined) =>
          data ? { ...data, ...result } : data,
        )
        void client.invalidateQueries({ queryKey: [...key, result.id], exact: true })
      }
      void client.invalidateQueries({ queryKey: [...key, 'history'] })
      void client.invalidateQueries({ queryKey: [...key, 'recent'] })
    },
    onSettled: () => {
      inFlight.current = false
    },
    retry: false,
  })
  return {
    ...mutation,
    uncertain: Boolean(original.current?.uncertain),
    mutate(value: Change, options?: Parameters<typeof mutation.mutate>[1]) {
      if (inFlight.current) return
      inFlight.current = true
      mutation.mutate(value, options)
    },
    retryOriginal(options?: Parameters<typeof mutation.mutate>[1]) {
      if (!original.current || inFlight.current) return
      inFlight.current = true
      mutation.mutate(original.current.value, options)
    },
  }
}
