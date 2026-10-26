import { CalendarCheck } from 'lucide-react'

import { Skeleton } from '@/components/ui/misc'
import { WidgetCard, WidgetError } from '@/features/dashboard/components/widget'
import type { DayProductivity } from '@/types/api'

interface Props {
  days: DayProductivity[] | undefined
  month: { start: string; end: string }
  isPending: boolean
  isError: boolean
  error: unknown
  isRefreshing: boolean
  onRetry: () => void
}

type Status = 'holiday' | 'absent' | 'half' | 'threeQuarter' | 'full' | 'none'

const STYLE: Record<Status, { label: string; cell: string; text: string }> = {
  holiday: { label: 'Holiday', cell: 'bg-muted/60', text: 'text-muted-foreground' },
  absent: { label: 'Absent', cell: 'bg-cat-unproductive/10', text: 'text-cat-unproductive' },
  half: { label: 'Half day', cell: 'bg-warning-soft', text: 'text-warning' },
  threeQuarter: { label: '¾ day', cell: 'bg-info-soft', text: 'text-info' },
  full: { label: 'Full day', cell: 'bg-success-soft', text: 'text-success' },
  none: { label: '', cell: '', text: 'text-muted-foreground' },
}

/** A workday baseline of 8h of active time; tiers mirror common attendance buckets. */
function statusFor(day: DayProductivity | undefined): Status {
  if (!day) return 'none'
  if (day.holiday) return 'holiday'
  const hours = day.metrics.active_seconds / 3600
  if (hours <= 0) return 'absent'
  if (hours < 4) return 'half'
  if (hours < 6) return 'threeQuarter'
  return 'full'
}

const WEEKDAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']

export function AttendanceCalendarCard({ days, month, isPending, isError, error, isRefreshing, onRetry }: Props) {
  const [y, m] = month.start.split('-').map(Number)
  const firstOfMonth = new Date(y, m - 1, 1)
  const monthLabel = firstOfMonth.toLocaleDateString(undefined, { month: 'long', year: 'numeric' })
  const firstWeekday = firstOfMonth.getDay()
  const daysInMonth = new Date(y, m, 0).getDate()
  const byDay = new Map((days ?? []).map((d) => [d.day, d]))
  const cells: ({ date: number; iso: string } | null)[] = []
  for (let i = 0; i < firstWeekday; i++) cells.push(null)
  for (let d = 1; d <= daysInMonth; d++) {
    cells.push({ date: d, iso: `${y}-${String(m).padStart(2, '0')}-${String(d).padStart(2, '0')}` })
  }

  return (
    <WidgetCard
      title={
        <span className="inline-flex items-center gap-2">
          <CalendarCheck className="size-4 text-primary" aria-hidden /> Attendance
        </span>
      }
      description={`Day-by-day attendance · ${monthLabel}`}
      refreshing={isRefreshing}
    >
      {isError ? (
        <WidgetError error={error} onRetry={onRetry} />
      ) : isPending ? (
        <div className="p-5">
          <Skeleton className="h-64" />
        </div>
      ) : (
        <div className="px-5 pt-1 pb-4">
          <div className="grid grid-cols-7 gap-1.5 text-center">
            {WEEKDAYS.map((w) => (
              <div key={w} className="pb-1 text-[11px] font-medium text-muted-foreground">
                {w}
              </div>
            ))}
            {cells.map((cell, i) =>
              cell === null ? (
                <div key={`e${i}`} />
              ) : (
                (() => {
                  const status = statusFor(byDay.get(cell.iso))
                  const s = STYLE[status]
                  return (
                    <div
                      key={cell.iso}
                      className={`flex min-h-14 flex-col items-center rounded-lg border p-1.5 ${s.cell}`}
                      title={s.label}
                    >
                      <span className="text-[12px] font-medium">{cell.date}</span>
                      {s.label && <span className={`mt-0.5 text-[9px] leading-tight ${s.text}`}>{s.label}</span>}
                    </div>
                  )
                })()
              ),
            )}
          </div>
          <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1">
            {(['full', 'threeQuarter', 'half', 'absent', 'holiday'] as Status[]).map((k) => (
              <span key={k} className="inline-flex items-center gap-1.5 text-[11px] text-muted-foreground">
                <span className={`size-2.5 rounded-sm ${STYLE[k].cell} border`} aria-hidden />
                {STYLE[k].label}
              </span>
            ))}
          </div>
        </div>
      )}
    </WidgetCard>
  )
}
