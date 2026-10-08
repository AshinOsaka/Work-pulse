import { API_BASE_URL } from '@/lib/api-client'

/**
 * Error tracking hook for the web app: uncaught errors, unhandled promise rejections and errors caught by the route
 * error pages are sent to the API (`POST /api/client-errors`), which logs them and forwards them to the configured
 * error tracker. Only the page path is sent (never the query string, which can hold one-time tokens), each distinct
 * error once per minute, and at most 20 per page load.
 */

type Kind = 'error' | 'unhandledrejection' | 'render' | 'chunk'

const RELEASE = (import.meta.env.VITE_APP_VERSION as string | undefined) ?? 'dev'
const MAX_PER_LOAD = 20
const REPEAT_MS = 60_000
const recent = new Map<string, number>()
let sent = 0

function describe(error: unknown): { message: string; stack?: string } {
  if (error instanceof Error) return { message: `${error.name}: ${error.message}`, stack: error.stack }
  return { message: typeof error === 'string' ? error : JSON.stringify(error) ?? String(error) }
}

export function reportError(kind: Kind, error: unknown, source?: string): void {
  const { message, stack } = describe(error)
  const key = `${kind}|${message}`
  const now = Date.now()
  if (sent >= MAX_PER_LOAD || now - (recent.get(key) ?? 0) < REPEAT_MS) return
  recent.set(key, now)
  sent += 1
  const body = JSON.stringify({
    kind,
    message: message.slice(0, 1000),
    page: window.location.pathname.slice(0, 300),
    source: source?.split('?')[0].slice(0, 300),
    stack: stack?.slice(0, 8000),
    release: RELEASE,
  })
  // keepalive: the report still goes out if the page is being unloaded. Failures are ignored (no reporting loops).
  void fetch(`${API_BASE_URL}/client-errors`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body,
    keepalive: true,
    credentials: 'omit',
  }).catch(() => undefined)
}

export function installErrorReporting(): void {
  window.addEventListener('error', (event) => {
    // Resource load errors (images, scripts) have no `error`; the route error pages handle failed page chunks.
    if (event.error) reportError('error', event.error, event.filename)
  })
  window.addEventListener('unhandledrejection', (event) => reportError('unhandledrejection', event.reason))
}
