import { useId } from 'react'
import { Clock, Minus, TrendingDown, TrendingUp } from 'lucide-react'
import { Area, AreaChart, ResponsiveContainer } from 'recharts'

import { Skeleton } from '@/components/ui/misc'
import { WidgetCard, WidgetError } from '@/features/dashboard/components/widget'
import { formatClock } from '@/features/dashboard/components/org/shared'
import { useCountUp } from '@/hooks/use-count-up'
import { usePrefersReducedMotion } from '@/hooks/use-now'
import type { DayProductivity, ProductivityMetrics } from '@/types/api'

interface Props {
  totals: ProductivityMetrics | undefined
  /** Per-day values over the selected range, for the matching mini trend beside each total. */
  days?: DayProductivity[]
  isPending: boolean
  isError: boolean
  error: unknown
  isRefreshing: boolean
  onRetry: () => void
}

/** A small smooth trend (same monotone style as the Productivity Trend chart) with no axes. */
function Sparkline({ data, color, delay }: { data: number[]; color: string; delay: number }) {
  const reduced = usePrefersReducedMotion()
  const gid = `wh-${useId().replace(/:/g, '')}`
  if (data.length < 2) return null
  const points = data.map((v, i) => ({ i, v }))
  return (
    <div className="ml-auto h-9 w-20 shrink-0 sm:w-24" aria-hidden>
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={points} margin={{ top: 4, right: 0, bottom: 0, left: 0 }}>
          <defs>
            <linearGradient id={gid} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={color} stopOpacity={0.25} />
              <stop offset="100%" stopColor={color} stopOpacity={0} />
            </linearGradient>
          </defs>
          <Area
            type="monotone"
            dataKey="v"
            stroke={color}
            strokeWidth={2}
            fill={`url(#${gid})`}
            dot={false}
            isAnimationActive={!reduced}
            animationBegin={delay}
            animationDuration={800}
            animationEasing="ease-out"
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  )
}

function Row({
  icon: Icon,
  value,
  label,
  tone,
  color,
  series,
  index,
}: {
  icon: typeof Clock
  value: number
  label: string
  tone: string
  color: string
  series: number[]
  index: number
}) {
  const shown = useCountUp(value)
  return (
    <div className="flex items-center gap-3 rounded-lg border bg-card px-4 py-3">
      <span className={`flex size-8 shrink-0 items-center justify-center rounded-lg ${tone}`}>
        <Icon className="size-4" aria-hidden />
      </span>
      <div className="min-w-0">
        <p className="text-lg font-semibold tabular leading-tight">{formatClock(shown)}</p>
        <p className="text-[12px] text-muted-foreground">{label}</p>
      </div>
      <Sparkline data={series} color={color} delay={index * 120} />
    </div>
  )
}

export function WorkHoursCard({ totals, days, isPending, isError, error, isRefreshing, onRetry }: Props) {
  const series = (pick: (m: ProductivityMetrics) => number) => (days ?? []).map((d) => pick(d.metrics) / 3600)
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
          <Row
            icon={Clock}
            value={totals.active_seconds}
            label="Total Active Hours"
            tone="bg-primary/10 text-primary"
            color="var(--primary)"
            series={series((m) => m.active_seconds)}
            index={0}
          />
          <Row
            icon={TrendingUp}
            value={totals.productive_seconds}
            label="Total Productive Hours"
            tone="bg-cat-productive/15 text-cat-productive"
            color="var(--cat-productive)"
            series={series((m) => m.productive_seconds)}
            index={1}
          />
          <Row
            icon={TrendingDown}
            value={totals.unproductive_seconds}
            label="Total Unproductive Hours"
            tone="bg-cat-unproductive/15 text-cat-unproductive"
            color="var(--cat-unproductive)"
            series={series((m) => m.unproductive_seconds)}
            index={2}
          />
          {/* Neutral here is the catch-all: time that is neither productive nor unproductive, i.e.
              rule-neutral apps plus anything not yet classified by a rule (so the card is never empty). */}
          <Row
            icon={Minus}
            value={totals.neutral_seconds + totals.unclassified_seconds}
            label="Total Neutral Hours"
            tone="bg-cat-neutral/15 text-cat-neutral"
            color="var(--cat-neutral)"
            series={series((m) => m.neutral_seconds + m.unclassified_seconds)}
            index={3}
          />
        </div>
      )}
    </WidgetCard>
  )
}
