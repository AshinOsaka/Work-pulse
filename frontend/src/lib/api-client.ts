import { useAuthStore } from '@/stores/auth-store'
import type { ApiErrorBody, AuthResponse, FieldErrorDetail } from '@/types/api'

export const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? '/api'

export class ApiError extends Error {
  readonly status: number
  readonly code: string
  readonly details: unknown
  readonly requestId: string | null

  constructor(status: number, code: string, message: string, details?: unknown, requestId?: string | null) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
    this.details = details
    this.requestId = requestId ?? null
  }

  /** Field-level validation messages keyed by field name. */
  get fieldErrors(): Record<string, string> {
    if (this.code !== 'validation_error' || !Array.isArray(this.details)) return {}
    const errors: Record<string, string> = {}
    for (const detail of this.details as FieldErrorDetail[]) {
      if (detail.field && !errors[detail.field]) errors[detail.field] = detail.message
    }
    return errors
  }
}

export function errorMessage(error: unknown, fallback = 'Something went wrong. Please try again.'): string {
  if (error instanceof ApiError) return error.message
  if (error instanceof Error && error.message) return error.message
  return fallback
}

interface RequestOptions {
  method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE'
  body?: unknown
  /** Attach the bearer token and transparently refresh it on 401. */
  auth?: boolean
  signal?: AbortSignal
  /** Extra headers, e.g. the content type of a raw upload. */
  headers?: Record<string, string>
}

async function toApiError(response: Response): Promise<ApiError> {
  try {
    const body = (await response.json()) as Partial<ApiErrorBody>
    if (body.error) {
      return new ApiError(response.status, body.error.code, body.error.message, body.error.details, body.request_id)
    }
  } catch {
    /* non-JSON error body */
  }
  const message =
    response.status >= 500 ? 'The server is unavailable. Please try again shortly.' : response.statusText || 'Request failed.'
  return new ApiError(response.status, `http_${response.status}`, message)
}

async function send(path: string, options: RequestOptions, token: string | null): Promise<Response> {
  // Files and blobs are sent as the raw request body; everything else as JSON.
  const raw = options.body instanceof Blob
  const headers: Record<string, string> = { Accept: 'application/json' }
  if (options.body !== undefined && !raw) headers['Content-Type'] = 'application/json'
  Object.assign(headers, options.headers)
  if (token) headers.Authorization = `Bearer ${token}`
  try {
    return await fetch(`${API_BASE_URL}${path}`, {
      method: options.method ?? 'GET',
      headers,
      body: raw ? (options.body as Blob) : options.body !== undefined ? JSON.stringify(options.body) : undefined,
      credentials: 'include',
      signal: options.signal,
    })
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error
    throw new ApiError(0, 'network_error', 'Unable to reach the server. Check your connection.')
  }
}

let refreshInFlight: Promise<AuthResponse | null> | null = null

/**
 * Exchange the refresh cookie for a new session. Concurrent callers share one
 * request — essential because refresh tokens are single-use (rotation).
 */
export function refreshSession(): Promise<AuthResponse | null> {
  refreshInFlight ??= (async () => {
    try {
      const response = await send('/auth/refresh', { method: 'POST' }, null)
      if (!response.ok) return null
      const session = (await response.json()) as AuthResponse
      useAuthStore.getState().setSession(session)
      return session
    } catch {
      return null
    } finally {
      refreshInFlight = null
    }
  })()
  return refreshInFlight
}

export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const useAuth = options.auth ?? true
  let response = await send(path, options, useAuth ? useAuthStore.getState().accessToken : null)

  if (response.status === 401 && useAuth) {
    const session = await refreshSession()
    if (!session) {
      useAuthStore.getState().clearSession()
      throw await toApiError(response)
    }
    response = await send(path, options, session.access_token)
  }

  if (!response.ok) throw await toApiError(response)
  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}

/** Like `apiRequest`, but hands back the open response so the caller can read a streamed body (server-sent events). */
export async function apiStream(path: string, body: unknown, signal?: AbortSignal): Promise<Response> {
  const options: RequestOptions = { method: 'POST', body, signal, headers: { Accept: 'text/event-stream' } }
  let response = await send(path, options, useAuthStore.getState().accessToken)
  if (response.status === 401) {
    const session = await refreshSession()
    if (!session) {
      useAuthStore.getState().clearSession()
      throw await toApiError(response)
    }
    response = await send(path, options, session.access_token)
  }
  if (!response.ok) throw await toApiError(response)
  return response
}

export const api = {
  get: <T>(path: string, opts?: Omit<RequestOptions, 'method' | 'body'>) => apiRequest<T>(path, { ...opts, method: 'GET' }),
  post: <T>(path: string, body?: unknown, opts?: Omit<RequestOptions, 'method' | 'body'>) =>
    apiRequest<T>(path, { ...opts, method: 'POST', body }),
  put: <T>(path: string, body?: unknown, opts?: Omit<RequestOptions, 'method' | 'body'>) =>
    apiRequest<T>(path, { ...opts, method: 'PUT', body }),
  patch: <T>(path: string, body?: unknown, opts?: Omit<RequestOptions, 'method' | 'body'>) =>
    apiRequest<T>(path, { ...opts, method: 'PATCH', body }),
  delete: <T>(path: string, opts?: Omit<RequestOptions, 'method' | 'body'>) =>
    apiRequest<T>(path, { ...opts, method: 'DELETE' }),
}

type QueryValue = string | number | boolean | null | undefined | readonly (string | number)[]

/** Builds `?a=1&b=x&b=y`, skipping empty values; arrays become repeated keys. */
export function toQuery(params: Record<string, QueryValue>): string {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === '') continue
    if (Array.isArray(value)) value.forEach((v) => search.append(key, String(v)))
    else search.set(key, String(value))
  }
  const query = search.toString()
  return query ? `?${query}` : ''
}

/** Maps an API error's `details.field` (domain errors) or validation details to a field message. */
export function errorField(error: unknown): { field: string; message: string } | null {
  if (!(error instanceof ApiError)) return null
  const details = error.details as { field?: unknown } | null
  if (details && typeof details === 'object' && typeof details.field === 'string') {
    return { field: details.field, message: error.message }
  }
  return null
}
