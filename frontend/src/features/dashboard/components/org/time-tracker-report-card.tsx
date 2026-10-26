import { ClipboardList } from 'lucide-react'

import { Skeleton } from '@/components/ui/misc'
import { WidgetCard, WidgetError, WidgetUnavailable } from '@/features/dashboard/components/widget'
import { formatClock } from '@/features/dashboard/components/org/shared'
import { formatTime } from '@/lib/format'
import type { DayProductivity } from '@/types/api'

interface Props {
  days: DayProductivity[] | undefined
  totalProductiveSeconds: number | undefined
  isPending: boolean
  isError: boolean
  error: unknown
  isRefreshing: boolean
  onRetry: () => void
}

function dayLabel(iso: string): string {
  return new Date(`${iso}T00:00:00`).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' })
}

export function TimeTrackerReportCard({ days, totalProductiveSeconds, isPending, isError, error, isRefreshing, onRetry }: Props) {
  const rows = [...(days ?? [])].reverse() // most recent first

  return (
    <WidgetCard
      title={
        <span className="inline-flex items-center gap-2">
          <ClipboardList className="size-4 text-primary" aria-hidden /> Time Tracker Report
        </span>
      }
      description="Daily activity span and productivity breakdown"
      refreshing={isRefreshing}
      actions={
        totalProductiveSeconds !== undefined ? (
          <span className="text-[12px] text-muted-foreground">
            Total productive <span className="font-semibold text-foreground tabular">{formatClock(totalProductiveSeconds)}</span>
          </span>
        ) : null
      }
    >
      {isError ? (
        <WidgetError error={error} onRetry={onRetry} />
      ) : isPending ? (
        <div className="space-y-2 p-5">
          {[0, 1, 2, 3, 4].map((i) => (
            <Skeleton key={i} className="h-9" />
          ))}
        </div>
      ) : !rows.length ? (
        <WidgetUnavailable icon={ClipboardList} title="No activity in this range" description="Daily productivity appears once the desktop agent has recorded work." />
      ) : (
        <div className="max-h-[28rem] overflow-auto">
          <table className="w-full border-collapse text-[12px] whitespace-nowrap">
            <thead className="sticky top-0 bg-popover">
              <tr className="border-b text-left text-[11px] font-medium tracking-wide text-muted-foreground uppercase">
                <th className="px-5 py-2.5 font-medium">Date</th>
                <th className="px-3 py-2.5 font-medium">Activity span</th>
                <th className="px-3 py-2.5 text-right font-medium">Active</th>
                <th className="px-3 py-2.5 text-right font-medium">Productive</th>
                <th className="px-3 py-2.5 text-right font-medium">Unproductive</th>
                <th className="px-3 py-2.5 text-right font-medium">Neutral</th>
                <th className="px-3 py-2.5 text-right font-medium">Idle</th>
                <th className="px-5 py-2.5 text-right font-medium">Away</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((d) => (
                <tr key={d.day} className="border-b last:border-0 hover:bg-muted/40">
                  <td className="px-5 py-2.5 font-medium">{dayLabel(d.day)}</td>
                  <td className="px-3 py-2.5 text-muted-foreground">
                    {d.active_from && d.active_to ? `${formatTime(d.active_from)} – ${formatTime(d.active_to)}` : d.holiday ? 'Holiday' : '—'}
                  </td>
                  <td className="px-3 py-2.5 text-right tabular">{formatClock(d.metrics.active_seconds)}</td>
                  <td className="px-3 py-2.5 text-right tabular text-cat-productive">{formatClock(d.metrics.productive_seconds)}</td>
                  <td className="px-3 py-2.5 text-right tabular text-cat-unproductive">{formatClock(d.metrics.unproductive_seconds)}</td>
                  <td className="px-3 py-2.5 text-right tabular text-cat-neutral">{formatClock(d.metrics.neutral_seconds)}</td>
                  <td className="px-3 py-2.5 text-right tabular text-muted-foreground">{formatClock(d.metrics.idle_seconds)}</td>
                  <td className="px-5 py-2.5 text-right tabular text-muted-foreground">{formatClock(d.metrics.away_seconds)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </WidgetCard>
  )
}
