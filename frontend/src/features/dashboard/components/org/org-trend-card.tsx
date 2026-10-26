import { TrendingUp } from 'lucide-react'
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'

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
  productive: number
  unproductive: number
  neutral: number
}

const SERIES = [
  { key: 'productive', label: 'Productive', color: 'var(--cat-productive)' },
  { key: 'unproductive', label: 'Unproductive', color: 'var(--cat-unproductive)' },
  { key: 'neutral', label: 'Neutral', color: 'var(--cat-neutral)' },
] as const

function TrendTooltip({ active, payload }: { active?: boolean; payload?: { payload?: Point }[] }) {
  const point = payload?.[0]?.payload
  if (!active || !point) return null
  return (
    <ChartTooltipBox
      title={dayLabel(point.date, true)}
      rows={SERIES.map((s) => ({ label: s.label, value: formatShort(point[s.key] * 3600), color: s.color }))}
    />
  )
}

export function OrgTrendCard({ days, isPending, isError, error, isRefreshing, onRetry }: Props) {
  const reduced = usePrefersReducedMotion()
  const points: Point[] = (days ?? []).map((d) => ({
    date: d.day,
    productive: d.metrics.productive_seconds / 3600,
    unproductive: d.metrics.unproductive_seconds / 3600,
    neutral: d.metrics.neutral_seconds / 3600,
  }))
  const hasData = points.some((p) => p.productive + p.unproductive + p.neutral > 0)

  return (
    <WidgetCard
      title={
        <span className="inline-flex items-center gap-2">
          <TrendingUp className="size-4 text-primary" aria-hidden /> Productivity Trend
        </span>
      }
      description="Productive vs unproductive time by date"
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
      className="xl:col-span-2"
    >
      {isError ? (
        <WidgetError error={error} onRetry={onRetry} />
      ) : isPending ? (
        <div className="p-5">
          <Skeleton className="h-64" />
        </div>
      ) : !hasData ? (
        <WidgetUnavailable
          icon={TrendingUp}
          title="No productivity data in this range"
          description="Comes from classified application and website time. Widen the range or add productivity rules to see it."
        />
      ) : (
        <figure className="h-64 px-2 pt-2 pb-4">
          <figcaption className="sr-only">Productive, unproductive and neutral hours by day</figcaption>
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={points} margin={{ top: 12, right: 24, bottom: 0, left: 0 }}>
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
              <Tooltip cursor={{ stroke: 'var(--muted-foreground)', strokeOpacity: 0.4 }} content={<TrendTooltip />} />
              {SERIES.map((s) => (
                <Line
                  key={s.key}
                  type="monotone"
                  dataKey={s.key}
                  stroke={s.color}
                  strokeWidth={2}
                  dot={false}
                  activeDot={{ r: 4, stroke: 'var(--card)', strokeWidth: 2 }}
                  isAnimationActive={!reduced}
                  animationDuration={600}
                />
              ))}
            </LineChart>
          </ResponsiveContainer>
        </figure>
      )}
    </WidgetCard>
  )
}
