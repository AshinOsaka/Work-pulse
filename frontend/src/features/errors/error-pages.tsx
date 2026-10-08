import { useEffect } from 'react'
import { ArrowLeft, Compass, RotateCw, TriangleAlert, WifiOff } from 'lucide-react'
import { isRouteErrorResponse, Link, useRouteError } from 'react-router'

import { EmptyState } from '@/components/common/empty-state'
import { LogoMark } from '@/components/common/logo'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { useDocumentTitle } from '@/hooks/use-document-title'
import { reportError } from '@/lib/error-reporting'

function ErrorLayout({ code, title, description, icon: Icon }: { code: string; title: string; description: string; icon: typeof Compass }) {
  return (
    <div className="relative flex min-h-svh flex-col items-center justify-center overflow-hidden bg-background px-6 text-center">
      <div className="pointer-events-none absolute inset-0 bg-dot-grid text-foreground/40 [mask-image:radial-gradient(ellipse_at_center,black,transparent_65%)]" />
      <div className="relative flex flex-col items-center gap-5">
        <LogoMark className="size-9" />
        <div className="flex items-center gap-2 rounded-full border bg-card px-3 py-1 text-[12px] font-medium text-muted-foreground shadow-xs">
          <Icon className="size-3.5" /> {code}
        </div>
        <div className="space-y-2">
          <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
          <p className="max-w-md text-sm text-muted-foreground">{description}</p>
        </div>
        <Button asChild>
          <Link to="/dashboard">
            <ArrowLeft /> Back to WorkPulse
          </Link>
        </Button>
      </div>
    </div>
  )
}

export function NotFoundPage() {
  useDocumentTitle('Page not found')
  return (
    <ErrorLayout
      code="404"
      icon={Compass}
      title="We couldn't find that page"
      description="The link may be broken, or the page may have moved. Check the address or head back to your dashboard."
    />
  )
}

/**
 * Pages are code-split. Loading one fails when the network is down, or after a deploy replaced the files the open tab
 * refers to. Both are fixed by loading again, so these get their own message instead of "Something went wrong".
 */
export function isChunkLoadError(error: unknown): boolean {
  const message = error instanceof Error ? `${error.name} ${error.message}` : String(error)
  return /dynamically imported module|importing a module script failed|ChunkLoadError|Failed to fetch/i.test(message)
}

/** Errors that reach an error page are reported once (404s aren't errors). */
function useReport(error: unknown, chunk: boolean) {
  useEffect(() => {
    if (isRouteErrorResponse(error) && error.status === 404) return
    reportError(chunk ? 'chunk' : 'render', error)
  }, [error, chunk])
}

/** Reload as soon as the connection is back (the browser fires `online`). */
function useReloadWhenOnline(enabled: boolean) {
  useEffect(() => {
    if (!enabled) return
    const reload = () => window.location.reload()
    window.addEventListener('online', reload)
    return () => window.removeEventListener('online', reload)
  }, [enabled])
}

function reloadButton() {
  return (
    <Button size="sm" variant="outline" onClick={() => window.location.reload()}>
      <RotateCw /> Try again
    </Button>
  )
}

/** Error inside the app shell: the sidebar and top bar stay, so people can carry on elsewhere. */
export function ContentErrorPage() {
  const error = useRouteError()
  const chunk = isChunkLoadError(error)
  useReloadWhenOnline(chunk)
  useReport(error, chunk)
  useDocumentTitle(chunk ? "Couldn't load this page" : 'Something went wrong')
  if (isRouteErrorResponse(error) && error.status === 404) return <NotFoundPage />
  return (
    <Card role="alert">
      {chunk ? (
        <EmptyState
          icon={WifiOff}
          title="Couldn't load this page"
          description={
            navigator.onLine
              ? 'WorkPulse may have been updated. Try again to load the latest version.'
              : "You're offline. This page will load as soon as your connection is back."
          }
          action={reloadButton()}
        />
      ) : (
        <EmptyState
          icon={TriangleAlert}
          title="Something went wrong"
          description="An unexpected error occurred while showing this page. Try again, or use the menu to go elsewhere."
          action={reloadButton()}
        />
      )}
    </Card>
  )
}

export function RouteErrorPage() {
  const error = useRouteError()
  const chunk = isChunkLoadError(error)
  useReloadWhenOnline(chunk)
  useReport(error, chunk)
  useDocumentTitle('Something went wrong')
  if (isRouteErrorResponse(error) && error.status === 404) return <NotFoundPage />
  if (chunk) {
    return (
      <ErrorLayout
        code="Connection"
        icon={WifiOff}
        title="Couldn't load this page"
        description="Check your connection and reload. If you're offline, the page loads by itself when you're back."
      />
    )
  }
  return (
    <ErrorLayout
      code="Unexpected error"
      icon={TriangleAlert}
      title="Something went wrong"
      description="An unexpected error occurred while rendering this page. Reload the page or return to the dashboard."
    />
  )
}
