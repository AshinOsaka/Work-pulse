import { BarChart3 } from 'lucide-react'
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'

import { Skeleton } from '@/components/ui/misc'
import { ChartTooltipBox, LegendItem, WidgetCard, WidgetError, WidgetUnavailable } from '@/features/dashboard/components/widget'
import { dayLabel, formatShort } from '@/features/dashboard/components/org/shared'
import { usePrefersReducedMotion } from '@/hooks/use-now'
import type { DayProductivity } from '@/types/api'

interface Props {
  days: DayProductivity[] | undefined
  isPending: boolean
  isError: boolean
  error: unknown
  isRefreshing: boolean
  onRetry: () => void
}

interface Point {
  date: string
  active: number
  productive: number
  neutral: number
}

// The same colours as the Work hours widget, so each measure reads the same everywhere.
const SERIES = [
  { key: 'active', label: 'Active', color: 'var(--primary)' },
  { key: 'productive', label: 'Productive', color: 'var(--cat-productive)' },
  { key: 'neutral', label: 'Neutral', color: 'var(--cat-neutral)' },
] as const

function DayTooltip({ active, payload }: { active?: boolean; payload?: { payload?: Point }[] }) {
  const point = payload?.[0]?.payload
  if (!active || !point) return null
  return (
    <ChartTooltipBox
      title={dayLabel(point.date, true)}
      rows={SERIES.map((s) => ({ label: s.label, value: formatShort(point[s.key] * 3600), color: s.color }))}
    />
  )
}

/** Active, productive and neutral hours side by side for each day of the range. */
export function DailyWorkHoursCard({ days, isPending, isError, error, isRefreshing, onRetry }: Props) {
  const reduced = usePrefersReducedMotion()
  const points: Point[] = (days ?? []).map((d) => ({
    date: d.day,
    active: d.metrics.active_seconds / 3600,
    productive: d.metrics.productive_seconds / 3600,
    neutral: d.metrics.neutral_seconds / 3600,
  }))
  const hasData = points.some((p) => p.active + p.productive + p.neutral > 0)

  return (
    <WidgetCard
      title={
        <span className="inline-flex items-center gap-2">
          <BarChart3 className="size-4 text-primary" aria-hidden /> Daily Work Hours
        </span>
      }
      description="Active, productive and neutral hours day by day"
      refreshing={isRefreshing}
      actions={
        hasData ? (
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
            {SERIES.map((s) => (
              <LegendItem key={s.key} color={s.color} label={s.label} />
            ))}
          </div>
        ) : null
      }
    >
      {isError ? (
        <WidgetError error={error} onRetry={onRetry} />
      ) : isPending ? (
        <div className="p-5">
          <Skeleton className="h-64" />
        </div>
      ) : !hasData ? (
        <WidgetUnavailable
          icon={BarChart3}
          title="No work hours in this range"
          description="Hours appear once employees work with the desktop agent running. Widen the range to see earlier days."
        />
      ) : (
        <figure className="h-64 px-2 pt-2 pb-4">
          <figcaption className="sr-only">Active, productive and neutral hours for each day</figcaption>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={points} margin={{ top: 12, right: 24, bottom: 0, left: 0 }} barGap={2} barCategoryGap="22%">
              <CartesianGrid vertical={false} stroke="var(--chart-grid)" />
              <XAxis
                dataKey="date"
                tickFormatter={(d: string) => dayLabel(d)}
                tickLine={false}
                axisLine={false}
                minTickGap={16}
                tickMargin={8}
                tick={{ fill: 'var(--muted-foreground)', fontSize: 11 }}
              />
              <YAxis
                tickFormatter={(v: number) => `${v}`}
                tickLine={false}
                axisLine={false}
                width={32}
                tick={{ fill: 'var(--muted-foreground)', fontSize: 11 }}
                label={{ value: 'Hours', angle: -90, position: 'insideLeft', fill: 'var(--muted-foreground)', fontSize: 11 }}
              />
              <Tooltip cursor={{ fill: 'var(--muted)', fillOpacity: 0.5 }} content={<DayTooltip />} />
              {SERIES.map((s) => (
                <Bar key={s.key} dataKey={s.key} fill={s.color} radius={[4, 4, 0, 0]} maxBarSize={18} isAnimationActive={!reduced} />
              ))}
            </BarChart>
          </ResponsiveContainer>
        </figure>
      )}
    </WidgetCard>
  )
}
