import { useId, useState } from 'react'
import { Gauge } from 'lucide-react'
import { Area, AreaChart, CartesianGrid, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'

import { Skeleton } from '@/components/ui/misc'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import {
  ChartTooltipBox,
  ViewToggle,
  WidgetCard,
  WidgetError,
  WidgetUnavailable,
  type ViewMode,
} from '@/features/dashboard/components/widget'
import type { Period, TrendPoint } from '@/features/dashboard/data/types'
import { usePrefersReducedMotion } from '@/hooks/use-now'
import { formatNumber } from '@/lib/format'

const RANGE_LABEL: Record<Period, string> = {
  daily: 'Daily · last 14 days',
  weekly: 'Weekly · last 12 weeks',
  monthly: 'Monthly · last 12 months',
}

function bucketLabel(date: string, period: Period, long = false): string {
  const d = new Date(date)
  if (period === 'monthly') return d.toLocaleDateString(undefined, { month: long ? 'long' : 'short', year: long ? 'numeric' : undefined })
  if (period === 'weekly') return `${long ? 'Week of ' : ''}${d.toLocaleDateString(undefined, { day: 'numeric', month: 'short' })}`
  return d.toLocaleDateString(undefined, long ? { weekday: 'long', day: 'numeric', month: 'short' } : { weekday: 'short', day: 'numeric' })
}

function TrendTooltip({
  active,
  payload,
  period,
}: {
  active?: boolean
  payload?: { payload?: TrendPoint }[]
  period: Period
}) {
  const point = payload?.[0]?.payload
  if (!active || !point) return null
  return (
    <ChartTooltipBox
      title={bucketLabel(point.date, period, true)}
      rows={[
        { label: 'Productive share', value: point.productivity === null ? 'Not enough data' : `${point.productivity.toFixed(0)}%`, color: 'var(--chart-1)' },
        { label: 'Work hours', value: `${formatNumber(point.workHours)} h` },
      ]}
    />
  )
}

interface ProductivityTrendCardProps {
  data: TrendPoint[] | undefined
  period: Period
  isPending: boolean
  isError: boolean
  error: unknown
  isRefreshing: boolean
  onRetry: () => void
  available: boolean
  sample: boolean
}

export function ProductivityTrendCard({
  data,
  period,
  isPending,
  isError,
  error,
  isRefreshing,
  onRetry,
  available,
  sample,
}: ProductivityTrendCardProps) {
  const [view, setView] = useState<ViewMode>('chart')
  const gradientId = useId()
  const reduced = usePrefersReducedMotion()
  const hasData = available && data && data.length > 0
  const known = hasData ? data.filter((p): p is TrendPoint & { productivity: number } => p.productivity !== null) : []
  const average = known.length ? known.reduce((sum, p) => sum + p.productivity, 0) / known.length : 0
  const last = known.at(-1)

  return (
    <WidgetCard
      title="Productive share trend"
      description={`Productive share of classified time · ${RANGE_LABEL[period]}`}
      sample={sample}
      refreshing={isRefreshing}
      actions={hasData ? <ViewToggle value={view} onChange={setView} /> : null}
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
          icon={Gauge}
          title="No productivity data yet"
          description="Calculated from classified application and website time. Add productivity rules to see it."
          phase={8}
        />
      ) : view === 'chart' ? (
        <div className="px-5 pt-3 pb-4">
          <div className="flex flex-wrap items-baseline gap-x-6 gap-y-1">
            <p className="text-[13px] text-muted-foreground">
              Latest <span className="ml-1 text-lg font-semibold text-foreground">{Math.round(last!.productivity)}%</span>
            </p>
            <p className="text-[13px] text-muted-foreground">
              Period average <span className="ml-1 text-lg font-semibold text-foreground">{Math.round(average)}%</span>
            </p>
          </div>
          <figure className="mt-3 h-64">
          <figcaption className="sr-only">{`Productivity trend, average ${Math.round(average)} percent`}</figcaption>
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={data} margin={{ top: 12, right: 24, bottom: 0, left: 0 }}>
                <defs>
                  <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="var(--chart-1)" stopOpacity={0.12} />
                    <stop offset="100%" stopColor="var(--chart-1)" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid vertical={false} stroke="var(--chart-grid)" />
                <XAxis
                  dataKey="date"
                  tickFormatter={(d: string) => bucketLabel(d, period)}
                  tickLine={false}
                  axisLine={false}
                  minTickGap={24}
                  tickMargin={8}
                  tick={{ fill: 'var(--muted-foreground)', fontSize: 11 }}
                />
                <YAxis
                  domain={[0, 100]}
                  ticks={[0, 25, 50, 75, 100]}
                  tickFormatter={(v: number) => `${v}%`}
                  tickLine={false}
                  axisLine={false}
                  width={48}
                  tick={{ fill: 'var(--muted-foreground)', fontSize: 11 }}
                />
                <ReferenceLine
                  y={average}
                  stroke="var(--muted-foreground)"
                  strokeOpacity={0.5}
                  label={{ value: `Avg ${Math.round(average)}%`, position: 'insideTopRight', fill: 'var(--muted-foreground)', fontSize: 11 }}
                />
                <Tooltip
                  cursor={{ stroke: 'var(--muted-foreground)', strokeOpacity: 0.4 }}
                  content={<TrendTooltip period={period} />}
                />
                <Area
                  type="monotone"
                  dataKey="productivity"
                  stroke="var(--chart-1)"
                  strokeWidth={2}
                  fill={`url(#${gradientId})`}
                  dot={false}
                  activeDot={{ r: 4, stroke: 'var(--card)', strokeWidth: 2 }}
                  isAnimationActive={!reduced}
                  animationDuration={600}
                />
              </AreaChart>
            </ResponsiveContainer>
          </figure>
        </div>
      ) : (
        <div className="max-h-[22rem] overflow-y-auto">
          <Table>
            <caption className="sr-only">Productivity by {period === 'daily' ? 'day' : period === 'weekly' ? 'week' : 'month'}</caption>
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                <TableHead className="pl-5">Period</TableHead>
                <TableHead className="text-right">Productivity</TableHead>
                <TableHead className="pr-5 text-right">Work hours</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {[...data].reverse().map((p) => (
                <TableRow key={p.date}>
                  <TableCell className="pl-5">{bucketLabel(p.date, period, true)}</TableCell>
                  <TableCell className="text-right tabular whitespace-nowrap">{p.productivity === null ? '—' : `${p.productivity.toFixed(0)}%`}</TableCell>
                  <TableCell className="pr-5 text-right tabular whitespace-nowrap">{formatNumber(p.workHours)} h</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </WidgetCard>
  )
}
