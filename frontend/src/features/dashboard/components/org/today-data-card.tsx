import { Zap } from 'lucide-react'

import { Skeleton } from '@/components/ui/misc'
import { WidgetCard, WidgetError } from '@/features/dashboard/components/widget'
import { formatClock } from '@/features/dashboard/components/org/shared'
import { formatTime } from '@/lib/format'
import type { EmployeeActivityDay } from '@/types/api'

interface Props {
  data: EmployeeActivityDay | undefined
  isPending: boolean
  isError: boolean
  error: unknown
  isRefreshing: boolean
  onRetry: () => void
}

function Tile({ value, label }: { value: string; label: string }) {
  return (
    <div className="flex flex-col items-center justify-center gap-1 rounded-xl border bg-card p-5 text-center">
      <p className="text-xl font-semibold tabular">{value}</p>
      <p className="text-[12px] text-muted-foreground">{label}</p>
    </div>
  )
}

export function TodayDataCard({ data, isPending, isError, error, isRefreshing, onRetry }: Props) {
  const segments = data?.segments ?? []
  const start = segments[0]?.started_at
  const last = segments.at(-1)?.ended_at

  return (
    <WidgetCard
      title={
        <span className="inline-flex items-center gap-2">
          <Zap className="size-4 text-primary" aria-hidden /> Today's Data
        </span>
      }
      description="Start time, last active time and active hours today"
      refreshing={isRefreshing}
    >
      {isError ? (
        <WidgetError error={error} onRetry={onRetry} />
      ) : isPending ? (
        <div className="grid gap-3 p-5 sm:grid-cols-3">
          <Skeleton className="h-24" />
          <Skeleton className="h-24" />
          <Skeleton className="h-24" />
        </div>
      ) : (
        <div className="grid gap-3 p-5 sm:grid-cols-3">
          <Tile value={start ? formatTime(start) : '—'} label="Start Time" />
          <Tile value={last ? formatTime(last) : '—'} label="Last Active Time" />
          <Tile value={formatClock(data?.active_seconds ?? 0)} label="Total Active Hours" />
        </div>
      )}
    </WidgetCard>
  )
}
