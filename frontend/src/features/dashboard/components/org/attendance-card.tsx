import { CalendarCheck } from 'lucide-react'
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'

import { Skeleton } from '@/components/ui/misc'
import { ChartTooltipBox, LegendItem, WidgetCard, WidgetError, WidgetUnavailable } from '@/features/dashboard/components/widget'
import { dayLabel } from '@/features/dashboard/components/org/shared'
import { usePrefersReducedMotion } from '@/hooks/use-now'
import type { AttendanceSummary } from '@/types/api'

interface Props {
  data: AttendanceSummary | undefined
  isPending: boolean
  isError: boolean
  error: unknown
  isRefreshing: boolean
  onRetry: () => void
}

interface Point {
  date: string
  present: number
  away: number
  holiday: boolean
}

const PRESENT = 'var(--cat-productive)'
const AWAY = 'var(--cat-unproductive)'

function AttendanceTooltip({ active, payload }: { active?: boolean; payload?: { payload?: Point }[] }) {
  const point = payload?.[0]?.payload
  if (!active || !point) return null
  return (
    <ChartTooltipBox
      title={`${dayLabel(point.date, true)}${point.holiday ? ' · holiday' : ''}`}
      rows={[
        { label: 'Present', value: String(point.present), color: PRESENT },
        { label: 'Away', value: point.holiday ? '—' : String(point.away), color: AWAY },
      ]}
    />
  )
}

export function AttendanceCard({ data, isPending, isError, error, isRefreshing, onRetry }: Props) {
  const reduced = usePrefersReducedMotion()
  const points: Point[] = (data?.days ?? []).map((d) => ({ date: d.day, present: d.present, away: d.away, holiday: d.holiday }))
  const hasData = points.some((p) => p.present + p.away > 0)

  return (
    <WidgetCard
      title={
        <span className="inline-flex items-center gap-2">
          <CalendarCheck className="size-4 text-primary" aria-hidden /> Attendance
        </span>
      }
      description="Present and away members by date"
      refreshing={isRefreshing}
      actions={
        hasData ? (
          <div className="flex items-center gap-4">
            <LegendItem color={PRESENT} label="Present" />
            <LegendItem color={AWAY} label="Away" />
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
          icon={CalendarCheck}
          title="No attendance yet"
          description="Present counts members with a work session each working day, once the desktop agent is in use."
        />
      ) : (
        <figure className="h-64 px-2 pt-2 pb-4">
          <figcaption className="sr-only">Present and away members by day</figcaption>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={points} margin={{ top: 12, right: 16, bottom: 0, left: 0 }}>
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
                allowDecimals={false}
                tickLine={false}
                axisLine={false}
                width={28}
                tick={{ fill: 'var(--muted-foreground)', fontSize: 11 }}
                label={{ value: 'Members', angle: -90, position: 'insideLeft', fill: 'var(--muted-foreground)', fontSize: 11 }}
              />
              <Tooltip cursor={{ fill: 'var(--muted-foreground)', fillOpacity: 0.08 }} content={<AttendanceTooltip />} />
              <Bar dataKey="present" fill={PRESENT} radius={[3, 3, 0, 0]} maxBarSize={22} isAnimationActive={!reduced} />
              <Bar dataKey="away" fill={AWAY} radius={[3, 3, 0, 0]} maxBarSize={22} isAnimationActive={!reduced} />
            </BarChart>
          </ResponsiveContainer>
        </figure>
      )}
    </WidgetCard>
  )
}
