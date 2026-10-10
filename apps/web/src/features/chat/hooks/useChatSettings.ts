import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useWorkspace } from '@/app/providers/WorkspaceProvider'
import { request, ApiError } from '@/lib/api/client'
import { z } from '@/lib/types/validation'
import { chatKey, chatPath, scoped, type ChatScope } from '../lib/chat-api'

const provider = z.object({
  provider_id: z.string(),
  name: z.string(),
  policy: z.string(),
  remote: z.boolean(),
  consented: z.boolean(),
})
export const consentSchema = z.object({
  organization_id: z.string(),
  project_id: z.string(),
  actor_id: z.string(),
  models: z.record(z.string(), provider),
})
export type ProviderConsent = z.infer<typeof provider>
const preferencesSchema = z.object({
  organization_id: z.string(),
  actor_id: z.string(),
  locale: z.enum(['id-ID', 'en-US']),
})

function own<T extends { actor_id: string; organization_id: string }>(
  data: T,
  scope: ChatScope,
): T {
  if (data.actor_id !== scope.user || data.organization_id !== scope.organization)
    throw new ApiError(502, 'Personal preferences could not be verified.')
  return data
}
export function useProviderConsent(scope: ChatScope) {
  const { csrf } = useWorkspace()
  const client = useQueryClient()
  const key = [...chatKey(scope), 'provider-consent']
  const query = useQuery({
    queryKey: key,
    queryFn: async ({ signal }) =>
      own(
        scoped(
          await request(chatPath(scope) + '/provider-consent', consentSchema, { signal }),
          scope,
        ),
        scope,
      ),
    enabled: Boolean(scope.user && scope.project),
    retry: false,
    staleTime: 0,
  })
  const grant = useMutation({
    mutationFn: async ({ model, policy }: { model: string; policy: string }) => {
      if (!csrf) throw new ApiError(401, 'Session unavailable.')
      return own(
        scoped(
          await request(chatPath(scope) + '/provider-consent', consentSchema, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf },
            body: JSON.stringify({ model, policy }),
          }),
          scope,
        ),
        scope,
      )
    },
    onSuccess: (data) => client.setQueryData(key, data),
    onError: () => {
      void client.invalidateQueries({ queryKey: key })
    },
    retry: false,
  })
  const revoke = useMutation({
    mutationFn: async (id: string) => {
      if (!csrf) throw new ApiError(401, 'Session unavailable.')
      return request(
        chatPath(scope) + '/provider-consent/' + encodeURIComponent(id),
        z.object({ revoked: z.literal(true) }),
        { method: 'DELETE', headers: { 'X-CSRF-Token': csrf } },
      )
    },
    onSuccess: () => client.invalidateQueries({ queryKey: key }),
    retry: false,
  })
  return { ...query, grant, revoke }
}
export function useLocalePreference(scope: ChatScope) {
  const { csrf } = useWorkspace()
  const client = useQueryClient()
  // Preference storage is personal/organization-wide. Its authorized request
  // still uses a project URL, so changing project must cancel the previous read.
  const key = ['locale', scope.user, scope.organization, scope.project]
  const query = useQuery({
    queryKey: key,
    queryFn: async ({ signal }) =>
      own(await request(chatPath(scope) + '/preferences', preferencesSchema, { signal }), scope),
    enabled: Boolean(scope.user && scope.project),
    retry: false,
    placeholderData: (previous) =>
      previous?.actor_id === scope.user && previous.organization_id === scope.organization
        ? previous
        : undefined,
  })
  const save = useMutation({
    mutationFn: async (locale: 'id-ID' | 'en-US') => {
      if (!csrf) throw new ApiError(401, 'Session unavailable.')
      return own(
        await request(chatPath(scope) + '/preferences', preferencesSchema, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf },
          body: JSON.stringify({ locale }),
        }),
        scope,
      )
    },
    onSuccess: (data) => {
      client.setQueriesData({ queryKey: ['locale', scope.user, scope.organization] }, data)
      client.setQueryData(key, data)
    },
    retry: false,
  })
  return { ...query, save }
}
