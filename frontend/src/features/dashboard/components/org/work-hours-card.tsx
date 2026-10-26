import { Clock, Minus, TrendingDown, TrendingUp } from 'lucide-react'

import { Skeleton } from '@/components/ui/misc'
import { WidgetCard, WidgetError } from '@/features/dashboard/components/widget'
import { formatClock } from '@/features/dashboard/components/org/shared'
import type { ProductivityMetrics } from '@/types/api'

interface Props {
  totals: ProductivityMetrics | undefined
  isPending: boolean
  isError: boolean
  error: unknown
  isRefreshing: boolean
  onRetry: () => void
}

function Row({ icon: Icon, value, label, tone }: { icon: typeof Clock; value: number; label: string; tone: string }) {
  return (
    <div className="flex items-center gap-3 rounded-lg border bg-card px-4 py-3">
      <span className={`flex size-8 shrink-0 items-center justify-center rounded-lg ${tone}`}>
        <Icon className="size-4" aria-hidden />
      </span>
      <div className="min-w-0">
        <p className="text-lg font-semibold tabular leading-tight">{formatClock(value)}</p>
        <p className="text-[12px] text-muted-foreground">{label}</p>
      </div>
    </div>
  )
}

export function WorkHoursCard({ totals, isPending, isError, error, isRefreshing, onRetry }: Props) {
  return (
    <WidgetCard
      title={
        <span className="inline-flex items-center gap-2">
          <Clock className="size-4 text-primary" aria-hidden /> Work Hours
        </span>
      }
      description="Active, productive, unproductive and neutral time"
      refreshing={isRefreshing}
    >
      {isError ? (
        <WidgetError error={error} onRetry={onRetry} />
      ) : isPending || !totals ? (
        <div className="space-y-2 p-5">
          {[0, 1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-14" />
          ))}
        </div>
      ) : (
        <div className="space-y-2 p-5">
          <Row icon={Clock} value={totals.active_seconds} label="Total Active Hours" tone="bg-primary/10 text-primary" />
          <Row icon={TrendingUp} value={totals.productive_seconds} label="Total Productive Hours" tone="bg-cat-productive/15 text-cat-productive" />
          <Row icon={TrendingDown} value={totals.unproductive_seconds} label="Total Unproductive Hours" tone="bg-cat-unproductive/15 text-cat-unproductive" />
          <Row icon={Minus} value={totals.neutral_seconds} label="Total Neutral Hours" tone="bg-cat-neutral/15 text-cat-neutral" />
        </div>
      )}
    </WidgetCard>
  )
}
