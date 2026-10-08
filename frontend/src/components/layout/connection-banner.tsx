import { WifiOff } from 'lucide-react'

import { useOnline } from '@/hooks/use-online'

/**
 * Shown while the browser is offline. Data requests pause meanwhile (TanStack Query's online manager) and resume
 * by themselves when the connection returns, so people know why pages aren't updating.
 */
export function ConnectionBanner() {
  const online = useOnline()
  if (online) return null
  return (
    <output className="flex items-center gap-2.5 border-b bg-muted px-4 py-2.5 text-[13px] sm:px-6">
      <WifiOff className="size-4 shrink-0 text-muted-foreground" aria-hidden />
      <span className="min-w-0">
        <span className="font-medium">You're offline.</span>{' '}
        <span className="text-muted-foreground">WorkPulse will reconnect and refresh this page when your connection is back.</span>
      </span>
    </output>
  )
}
