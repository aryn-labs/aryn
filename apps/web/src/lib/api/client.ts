import type { z } from '@/lib/types/validation'

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
    public readonly loginUrl?: string,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}
export async function request<T>(
  path: string,
  schema: z.ZodType<T>,
  options: RequestInit = {},
): Promise<T> {
  let response: Response
  try {
    response = await fetch(path, {
      ...options,
      credentials: 'same-origin',
      headers: { Accept: 'application/json', ...options.headers },
    })
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error
    throw new ApiError(0, 'ARYN API is unreachable. Check your connection and try again.')
  }
  if (!response.ok) {
    const body: unknown = await response.json().catch(() => null)
    // Do not surface arbitrary proxy responses or sensitive dependency details.
    const loginUrl =
      body && typeof body === 'object' && 'login_url' in body && body.login_url === '/auth/login'
        ? '/auth/login'
        : undefined
    throw new ApiError(
      response.status,
      response.status === 401
        ? 'Your session is unavailable or has expired.'
        : response.status === 403
          ? 'ARYN Core denied access to this workspace.'
          : response.status === 404
            ? 'This resource is unavailable.'
            : 'ARYN could not load this data. Try again.',
      loginUrl,
    )
  }
  const parsed = schema.safeParse(await response.json().catch(() => null))
  if (!parsed.success)
    throw new ApiError(502, 'The API response does not match the workspace contract.')
  return parsed.data
}
