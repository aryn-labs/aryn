import { z } from '@/lib/types/validation'
import { ApiError, request } from '@/lib/api/client'

const timestamp = z.union([z.string(), z.number()])
const scope = { organization_id: z.string(), project_id: z.string() }
export const capabilitySchema = z.object({
  ...scope,
  models: z.array(
    z.object({
      id: z.string(),
      name: z.string(),
      available: z.boolean(),
      verifiable: z.boolean().optional(),
    }),
  ),
  can_send: z.boolean(),
  permitted: z.boolean(),
  reason: z.string().nullable(),
  remote_consent_required: z.boolean(),
  streaming: z.literal(false),
  cancellation: z.literal(false),
  max_message_length: z.number(),
})
export const conversationSchema = z.object({
  ...scope,
  id: z.string(),
  title: z.string(),
  model: z.string(),
  revision: z.number().int(),
  metadata_revision: z.number().int().nonnegative().default(0),
  can_rename: z.boolean().default(false),
  can_delete: z.boolean().default(false),
  created_at: timestamp,
  updated_at: timestamp,
  status: z.enum(['processing', 'completed', 'failed', 'cancelled', 'outcome_unknown', 'empty']),
  can_send: z.boolean(),
  error_code: z.string().nullable(),
  streaming: z.literal(false),
  cancellation: z.literal(false),
  messages: z.array(
    z.object({
      id: z.string(),
      role: z.enum(['user', 'assistant']),
      content: z.string(),
      created_at: timestamp,
      model: z.string().optional(),
    }),
  ),
})
export const historySchema = z.object({
  ...scope,
  items: z.array(
    z.object({
      id: z.string(),
      title: z.string(),
      model: z.string(),
      updated_at: timestamp,
      metadata_revision: z.number().int().nonnegative().default(0),
      can_rename: z.boolean().default(false),
      can_delete: z.boolean().default(false),
    }),
  ),
  next_cursor: z.string().nullable(),
})
export type Conversation = z.infer<typeof conversationSchema>
export type ChatCapability = z.infer<typeof capabilitySchema>
export type ChatScope = { organization: string; project: string; user: string }
export type HistoryItem = z.infer<typeof historySchema>['items'][number]
export type ConversationChange = {
  idempotency_key: string
  expected_metadata_revision: number
  title?: string
}
const metadataSchema = z.object({
  ...scope,
  id: z.string(),
  title: z.string(),
  metadata_revision: z.number().int().positive(),
  deleted: z.boolean(),
})
export type ConversationMetadata = z.infer<typeof metadataSchema>
export class MetadataUnknownError extends ApiError {
  constructor() {
    super(0, 'errors.metadata_unknown')
  }
}
export async function changeConversation(
  selected: ChatScope,
  csrf: string,
  id: string,
  method: 'PATCH' | 'DELETE',
  input: ConversationChange,
  signal: AbortSignal,
) {
  let response: Response
  try {
    response = await fetch(`${chatPath(selected)}/conversations/${encodeURIComponent(id)}`, {
      method,
      credentials: 'same-origin',
      signal,
      headers: {
        Accept: 'application/json',
        'Content-Type': 'application/json',
        'X-CSRF-Token': csrf,
      },
      body: JSON.stringify(input),
    })
  } catch {
    throw new MetadataUnknownError()
  }
  const body: unknown = await response.json().catch(() => null)
  if (!response.ok) {
    const code = body && typeof body === 'object' && 'error_code' in body ? body.error_code : ''
    if (response.status >= 500 && code !== 'conversation_metadata_unavailable')
      throw new MetadataUnknownError()
    throw new ApiError(
      response.status,
      code === 'conversation_changed' || code === 'idempotency_conflict'
        ? `errors.${code}`
        : response.status === 403
          ? 'errors.denied'
          : response.status === 401
            ? 'errors.session'
            : 'errors.metadata_failed',
    )
  }
  const parsed = metadataSchema.safeParse(body)
  if (!parsed.success || parsed.data.id !== id || parsed.data.deleted !== (method === 'DELETE'))
    throw new MetadataUnknownError()
  try {
    return scoped(parsed.data, selected)
  } catch {
    throw new MetadataUnknownError()
  }
}
export type TurnInput = {
  message: string
  model: string
  idempotency_key: string
  expected_revision: number
  allow_remote_model: boolean
}
export const chatKey = (scope: ChatScope) =>
  ['chat', scope.user, scope.organization, scope.project] as const
export const chatPath = (scope: ChatScope) =>
  `/api/projects/${encodeURIComponent(scope.project)}/chat`
export function scoped<T extends { organization_id: string; project_id: string }>(
  value: T,
  selected: ChatScope,
): T {
  if (value.organization_id !== selected.organization || value.project_id !== selected.project)
    throw new ApiError(502, 'The conversation does not belong to this workspace.')
  return value
}
const errors = new Set([
  'remote_consent_required',
  'consent_policy_changed',
  'consent_history_unavailable',
  'conversation_changed',
  'idempotency_conflict',
  'previous_outcome_unresolved',
  'conversation_limit',
  'runtime_unavailable',
  'model_unverified',
  'model_verification_unresolved',
  'model_identity_invalid',
  'model_unavailable',
  'rate_limited',
])
export class DeliveryUnknownError extends ApiError {
  constructor(status = 0) {
    super(status, 'errors.unknown')
  }
}
export async function sendTurn(
  selected: ChatScope,
  csrf: string,
  input: TurnInput,
  id?: string,
  signal?: AbortSignal,
) {
  const path =
    chatPath(selected) + '/conversations' + (id ? `/${encodeURIComponent(id)}/messages` : '')
  let response: Response
  try {
    response = await fetch(path, {
      method: 'POST',
      credentials: 'same-origin',
      signal,
      headers: {
        Accept: 'application/json',
        'Content-Type': 'application/json',
        'X-CSRF-Token': csrf,
      },
      body: JSON.stringify(input),
    })
  } catch {
    throw new DeliveryUnknownError()
  }
  const body: unknown = await response.json().catch(() => null)
  if (!response.ok) {
    const code =
      body &&
      typeof body === 'object' &&
      'error_code' in body &&
      typeof body.error_code === 'string'
        ? body.error_code
        : ''
    if (response.status >= 500 && !errors.has(code)) throw new DeliveryUnknownError(response.status)
    throw new ApiError(
      response.status,
      errors.has(code)
        ? 'errors.' + code
        : response.status === 403
          ? 'errors.denied'
          : response.status === 401
            ? 'errors.session'
            : 'errors.failed',
    )
  }
  const parsed = conversationSchema.safeParse(body)
  if (!parsed.success) throw new DeliveryUnknownError(502)
  let result: Conversation
  try {
    result = scoped(parsed.data, selected)
  } catch {
    throw new DeliveryUnknownError(502)
  }
  if (id && result.id !== id) throw new DeliveryUnknownError(502)
  return result
}
export async function getConversation(selected: ChatScope, id: string, signal: AbortSignal) {
  const result = scoped(
    await request(
      `${chatPath(selected)}/conversations/${encodeURIComponent(id)}`,
      conversationSchema,
      { signal },
    ),
    selected,
  )
  if (result.id !== id) throw new ApiError(502, 'The conversation response could not be verified.')
  return result
}
