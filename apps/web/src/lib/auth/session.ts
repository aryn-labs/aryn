import { request } from '@/lib/api/client'
import { z } from '@/lib/types/validation'
export const sessionSchema = z.object({
  csrf: z.string().min(1),
  mode: z.enum(['development', 'oidc']),
})
export function getSession(signal?: AbortSignal) {
  return request('/api/session', sessionSchema, { method: 'POST', signal })
}
export function logout(csrf: string) {
  return request('/api/logout', z.object({ logged_out: z.boolean() }), {
    method: 'POST',
    headers: { 'X-CSRF-Token': csrf },
  })
}
