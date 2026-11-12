import { useMemo, useState } from 'react'
import { CalendarDays, ChevronLeft, ChevronRight, X } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Card, CardAction, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/misc'
import { formatClock, formatDay, formatSeconds } from '@/features/activity/format'
import { useAttendanceReport } from '@/features/attendance/api'
import { useEmployeeProductivity } from '@/features/productivity/api'
import { CATEGORY, CATEGORY_ORDER } from '@/features/productivity/meta'
import { useHiddenSections } from '@/config/sections'
import { WidgetError } from '@/features/dashboard/components/widget'
import { cn } from '@/lib/utils'
import type { AttendanceDayStatus, AttendanceReportDay } from '@/types/api'

/** One person's month of attendance: shared by the Attendance page and the employee profile. */

export function monthStart(day: string) {
  return `${day.slice(0, 7)}-01`
}

export function monthEnd(day: string) {
  const [y, m] = day.split('-').map(Number)
  return `${day.slice(0, 7)}-${String(utcDate(y, m, 0).getUTCDate()).padStart(2, '0')}`
}

/** A UTC calendar date (month is 0-based; overflowing days/months roll over). */
export function utcDate(year: number, month: number, day: number) {
  return new Date(Date.UTC(year, month, day))
}

export const DAY_STYLE: Record<AttendanceDayStatus, { label: string; cell: string; dot: string }> = {
  met: { label: 'Completed', cell: 'bg-success-soft border-success/30', dot: 'bg-success' },
  short: { label: 'Short', cell: 'bg-destructive-soft border-destructive/30', dot: 'bg-destructive' },
  absent: { label: 'Absent', cell: 'bg-destructive-soft border-destructive/30', dot: 'bg-destructive' },
  in_progress: { label: 'In progress', cell: 'bg-info-soft border-info/30', dot: 'bg-info' },
  no_target: { label: 'Worked', cell: 'bg-subtle', dot: 'bg-muted-foreground' },
  holiday: { label: 'Holiday', cell: 'bg-muted/60', dot: 'bg-muted-foreground/50' },
  upcoming: { label: '', cell: '', dot: '' },
}

/** Completed / Short by / Over by, against the expected hours of the range. */
export function Balance({ logged, expected, compact = false }: { logged: number; expected: number; compact?: boolean }) {
  if (expected <= 0) return <span className="text-[12px] text-muted-foreground">No requirement</span>
  const diff = logged - expected
  const done = diff >= 0
  return (
    <span
      className={cn(
        'inline-flex items-center rounded-full px-2 py-0.5 text-[12px] font-medium whitespace-nowrap tabular',
        done ? 'bg-success-soft text-success' : 'bg-destructive-soft text-destructive',
      )}
    >
      {done ? (diff >= 60 ? `Over by ${formatSeconds(diff)}` : 'Completed') : `${compact ? '−' : 'Short by '}${formatSeconds(-diff)}`}
    </span>
  )
}

const WEEKDAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

export function AttendanceCalendar({
  employeeId,
  name,
  initialDay,
  today,
  timeZone,
  onClose,
}: {
  employeeId: string
  name: string
  initialDay: string
  today: string
  timeZone: string
  onClose?: () => void
}) {
  const [month, setMonth] = useState(() => monthStart(initialDay))
  const [selected, setSelected] = useState<string | null>(null)
  const query = useAttendanceReport({ start: month, end: monthEnd(month), employee_id: employeeId })
  const row = query.data?.rows[0]
  const byDay = useMemo(() => new Map((row?.days ?? []).map((d) => [d.day, d])), [row])
  const [y, m] = month.split('-').map(Number)
  const label = utcDate(y, m - 1, 1).toLocaleDateString(undefined, { month: 'long', year: 'numeric', timeZone: 'UTC' })
  const lead = (new Date(`${month}T00:00:00Z`).getUTCDay() + 6) % 7
  const count = utcDate(y, m, 0).getUTCDate()
  const cells: (string | null)[] = [...Array<null>(lead).fill(null)]
  for (let d = 1; d <= count; d++) cells.push(`${month.slice(0, 7)}-${String(d).padStart(2, '0')}`)
  const detail = selected ? byDay.get(selected) : undefined
  const shift = (delta: number) => {
    const next = utcDate(y, m - 1 + delta, 1).toISOString().slice(0, 10)
    setMonth(next)
    setSelected(null)
  }

  return (
    <Card className="overflow-hidden">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <CalendarDays className="size-4 text-primary" aria-hidden /> {name}
        </CardTitle>
        <CardDescription>Sign-in, sign-out and active time per day</CardDescription>
        {onClose && (
          <CardAction>
            <Button variant="ghost" size="icon" className="size-8" onClick={onClose} aria-label="Close calendar">
              <X className="size-4" />
            </Button>
          </CardAction>
        )}
      </CardHeader>
      <div className="px-4 pt-3 pb-4">
        <div className="mb-3 flex items-center justify-between">
          <Button variant="outline" size="icon" className="size-8" onClick={() => shift(-1)} aria-label="Previous month">
            <ChevronLeft className="size-4" />
          </Button>
          <span className="text-[14px] font-semibold">{label}</span>
          <Button
            variant="outline"
            size="icon"
            className="size-8"
            onClick={() => shift(1)}
            disabled={month >= monthStart(today)}
            aria-label="Next month"
          >
            <ChevronRight className="size-4" />
          </Button>
        </div>
        {query.isError ? (
          <WidgetError error={query.error} onRetry={() => void query.refetch()} />
        ) : !row ? (
          <Skeleton className="h-80" />
        ) : (
          <div className={cn('space-y-3', query.isPlaceholderData && 'opacity-70 transition-opacity')}>
            <div className="grid grid-cols-7 gap-1">
              {WEEKDAYS.map((w) => (
                <div key={w} className="pb-1 text-center text-[10px] font-medium tracking-wide text-muted-foreground uppercase">
                  {w}
                </div>
              ))}
              {cells.map((iso, i) => {
                if (!iso) return <div key={`e${i}`} />
                const d = byDay.get(iso)
                const style = DAY_STYLE[d?.status ?? 'upcoming']
                const extra = (d?.sessions.length ?? 0) - 1
                return (
                  <button
                    key={iso}
                    type="button"
                    onClick={() => setSelected(selected === iso ? null : iso)}
                    disabled={!d || d.status === 'upcoming'}
                    className={cn(
                      'flex min-h-[4.25rem] flex-col items-stretch rounded-md border p-1 text-left transition',
                      style.cell,
                      selected === iso && 'ring-2 ring-primary',
                      d && d.status !== 'upcoming' ? 'hover:brightness-[0.97]' : 'cursor-default opacity-60',
                    )}
                    title={style.label || undefined}
                    aria-label={`${formatDay(iso)}${style.label ? `, ${style.label}` : ''}`}
                  >
                    <span className={cn('text-[11px] font-semibold', iso === today && 'text-primary')}>{Number(iso.slice(8))}</span>
                    {d?.first_in && (
                      <span className="mt-0.5 truncate text-[9.5px] leading-tight tabular">
                        In {formatClock(d.first_in, timeZone)}
                      </span>
                    )}
                    {d?.first_in && (
                      <span className="truncate text-[9.5px] leading-tight text-muted-foreground tabular">
                        {d.last_out ? `Out ${formatClock(d.last_out, timeZone)}` : 'Signed in'}
                      </span>
                    )}
                    {extra > 0 && <span className="text-[9px] leading-tight text-primary">+{extra} more</span>}
                    {d && d.status !== 'upcoming' && d.status !== 'holiday' && d.active_seconds > 0 && (
                      <span className="mt-auto text-[9.5px] font-medium tabular">{formatSeconds(d.active_seconds)}</span>
                    )}
                  </button>
                )
              })}
            </div>
            <div className="flex flex-wrap gap-x-3 gap-y-1">
              {(['met', 'short', 'absent', 'in_progress', 'holiday'] as AttendanceDayStatus[]).map((k) => (
                <span key={k} className="inline-flex items-center gap-1.5 text-[11px] text-muted-foreground">
                  <span className={cn('size-2 rounded-full', DAY_STYLE[k].dot)} aria-hidden /> {DAY_STYLE[k].label}
                </span>
              ))}
            </div>
            {detail ? (
              <DayDetail day={detail} timeZone={timeZone} employeeId={employeeId} />
            ) : (
              <p className="text-[12px] text-muted-foreground">Click a day to see every session.</p>
            )}
          </div>
        )}
      </div>
    </Card>
  )
}

function DayDetail({ day, timeZone, employeeId }: { day: AttendanceReportDay; timeZone: string; employeeId: string }) {
  return (
    <div className="space-y-2 rounded-lg border bg-subtle/50 p-3">
      <div className="flex items-center justify-between gap-2">
        <span className="text-[13px] font-semibold">{formatDay(day.day)}</span>
        {day.status === 'holiday' ? (
          <span className="text-[12px] text-muted-foreground">Holiday</span>
        ) : (
          <Balance logged={day.active_seconds} expected={day.expected_seconds} />
        )}
      </div>
      <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-[12px] sm:grid-cols-4">
        {[
          ['Active (logged)', day.active_seconds],
          ['Signed in', day.work_seconds],
          ['Idle', day.idle_seconds],
          ['Required', day.expected_seconds],
        ].map(([label, seconds]) => (
          <div key={label}>
            <dt className="text-muted-foreground">{label}</dt>
            <dd className="font-medium tabular">{formatSeconds(Number(seconds))}</dd>
          </div>
        ))}
      </dl>
      {day.work_seconds > 0 && <DayCategories employeeId={employeeId} day={day.day} />}
      {day.customer_seconds > 0 && (
        <p className="text-[12px] text-muted-foreground">
          Includes <span className="font-medium text-foreground tabular">{formatSeconds(day.customer_seconds)}</span> of
          customer system time.
        </p>
      )}
      {day.meeting_seconds > 0 && (
        <p className="text-[12px] text-muted-foreground">
          Includes <span className="font-medium text-foreground tabular">{formatSeconds(day.meeting_seconds)}</span> of
          approved meeting time.
        </p>
      )}
      {day.sessions.length === 0 ? (
        <p className="text-[12px] text-muted-foreground">No work session this day.</p>
      ) : (
        <ul className="space-y-1">
          {day.sessions.map((s) => (
            <li key={s.start} className="flex justify-between text-[12px] tabular">
              <span>
                {formatClock(s.start, timeZone)} – {s.open ? 'now' : formatClock(s.end, timeZone)}
              </span>
              <span className="text-muted-foreground">
                {formatSeconds((Date.parse(s.end) - Date.parse(s.start)) / 1000)}
                {s.open && ' · signed in'}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}


/**
 * The day's app and website time by productivity category, from the Productivity report (display only: attendance
 * is not affected). Category time is time in front, typing or idle, so it adds up to about "Signed in".
 */
function DayCategories({ employeeId, day }: { employeeId: string; day: string }) {
  const { isHidden } = useHiddenSections()
  const query = useEmployeeProductivity(employeeId, { start: day, end: day }, !isHidden('productivity'))
  const totals = query.data?.start === day ? query.data.totals : undefined
  if (!totals) return null
  const parts = CATEGORY_ORDER.map((c) => ({ c, seconds: Number(totals[CATEGORY[c].metric]) || 0 })).filter((p) => p.c !== 'unclassified' || p.seconds >= 60)
  if (parts.length === 0) return null
  return (
    <div className="space-y-1">
      <ul className="flex flex-wrap gap-x-3 gap-y-1 text-[12px]">
        {parts.map(({ c, seconds }) => (
          <li key={c} className="inline-flex items-center gap-1.5">
            <span className={cn('size-2 rounded-full', CATEGORY[c].swatch)} aria-hidden />
            <span className="text-muted-foreground">{CATEGORY[c].label}</span>
            <span className="font-medium tabular">{formatSeconds(seconds)}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}
