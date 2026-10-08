import { useMemo, useState } from 'react'

import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { formatClock, formatSeconds } from '@/features/activity/format'
import { LegendItem, ViewToggle, type ViewMode } from '@/features/dashboard/components/widget'
import type { ActivitySegment, AppUsage } from '@/types/api'

const HOUR = 3_600_000
/** The three most-used applications get a series colour; the rest share a neutral one. */
const SERIES = ['var(--chart-1)', 'var(--chart-2)', 'var(--chart-3)']
const OTHER = 'color-mix(in oklch, var(--muted-foreground) 45%, transparent)'

interface DayTimelineProps {
  segments: ActivitySegment[]
  applications: AppUsage[]
  timeZone: string
}

export function DayTimeline({ segments, applications, timeZone }: DayTimelineProps) {
  const [view, setView] = useState<ViewMode>('chart')
  const [hovered, setHovered] = useState<ActivitySegment | null>(null)

  const colors = useMemo(() => {
    const map = new Map<string, string>()
    applications.slice(0, SERIES.length).forEach((app, i) => map.set(app.app_id, SERIES[i]))
    return map
  }, [applications])
  const hasOther = applications.length > SERIES.length
  const showTitles = segments.some((s) => s.window_title)

  const { start, end, ticks } = useMemo(() => {
    const first = Math.min(...segments.map((s) => new Date(s.started_at).getTime()))
    const last = Math.max(...segments.map((s) => new Date(s.ended_at).getTime()))
    const from = Math.floor(first / HOUR) * HOUR
    const to = Math.max(Math.ceil(last / HOUR) * HOUR, from + 2 * HOUR)
    const hours = (to - from) / HOUR
    const step = hours > 12 ? 3 : hours > 6 ? 2 : 1
    const marks: number[] = []
    for (let t = from; t <= to; t += step * HOUR) marks.push(t)
    return { start: from, end: to, ticks: marks }
  }, [segments])
  const span = end - start
  const position = (value: string) => ((new Date(value).getTime() - start) / span) * 100
  const colorOf = (appId: string) => colors.get(appId) ?? OTHER

  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-3 px-5 pt-4">
        <div className="flex flex-wrap gap-x-4 gap-y-1">
          {applications.slice(0, SERIES.length).map((app) => (
            <LegendItem key={app.app_id} color={colorOf(app.app_id)} label={app.app_name} />
          ))}
          {hasOther && <LegendItem color={OTHER} label="Other applications" />}
        </div>
        <ViewToggle value={view} onChange={setView} />
      </div>

      {view === 'chart' ? (
        <figure className="px-5 pt-4 pb-5">
          <figcaption className="sr-only">
            {`Application timeline from ${formatClock(start, timeZone)} to ${formatClock(end, timeZone)}, ${segments.length} segments. Switch to the table view for details.`}
          </figcaption>
          <div className="relative h-10 rounded-md bg-muted/60" onMouseLeave={() => setHovered(null)}>
            {segments.map((segment) => {
              const left = position(segment.started_at)
              const width = position(segment.ended_at) - left
              return (
                <div
                  key={segment.started_at + segment.app_id}
                  className="absolute inset-y-0 rounded-[3px] transition-opacity hover:opacity-80"
                  style={{
                    left: `${left}%`,
                    // 2px gap between neighbouring segments; tiny segments stay visible.
                    width: `max(2px, calc(${width}% - 2px))`,
                    background: colorOf(segment.app_id),
                  }}
                  onMouseEnter={() => setHovered(segment)}
                  aria-hidden
                />
              )
            })}
          </div>
          <div className="relative mt-1.5 h-4 text-[11px] text-muted-foreground" aria-hidden>
            {ticks.map((tick) => (
              <span
                key={tick}
                className="absolute -translate-x-1/2 whitespace-nowrap tabular first:translate-x-0 last:-translate-x-full"
                style={{ left: `${((tick - start) / span) * 100}%` }}
              >
                {formatClock(tick, timeZone)}
              </span>
            ))}
          </div>
          <p className="mt-3 min-h-5 text-[12px] text-muted-foreground" aria-live="polite">
            {hovered ? (
              <>
                <span className="font-medium text-foreground">{hovered.app_name}</span>
                {hovered.window_title && <> · {hovered.window_title}</>} · {formatClock(hovered.started_at, timeZone)}–
                {formatClock(hovered.ended_at, timeZone)} · {formatSeconds(hovered.duration_seconds)} ·{' '}
                {hovered.activity_level}% active
              </>
            ) : (
              'Hover over the timeline for details.'
            )}
          </p>
        </figure>
      ) : (
        <div className="mt-3 max-h-[26rem] overflow-y-auto border-t">
          <Table>
            <caption className="sr-only">Application segments</caption>
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                <TableHead className="pl-5">Time</TableHead>
                <TableHead>Application</TableHead>
                {showTitles && <TableHead className="hidden md:table-cell">Window</TableHead>}
                <TableHead className="text-right">Duration</TableHead>
                <TableHead className="pr-5 text-right">Active</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {segments.map((segment) => (
                <TableRow key={segment.started_at + segment.app_id}>
                  <TableCell className="pl-5 whitespace-nowrap tabular text-muted-foreground">
                    {formatClock(segment.started_at, timeZone)}–{formatClock(segment.ended_at, timeZone)}
                  </TableCell>
                  <TableCell className="max-w-48">
                    <span className="flex min-w-0 items-center gap-2">
                      <span className="size-2 shrink-0 rounded-full" style={{ background: colorOf(segment.app_id) }} aria-hidden />
                      <span className="truncate">{segment.app_name}</span>
                    </span>
                  </TableCell>
                  {showTitles && (
                    <TableCell className="hidden max-w-72 truncate text-muted-foreground md:table-cell" title={segment.window_title ?? undefined}>
                      {segment.window_title ?? '—'}
                    </TableCell>
                  )}
                  <TableCell className="text-right tabular whitespace-nowrap">{formatSeconds(segment.duration_seconds)}</TableCell>
                  <TableCell className="pr-5 text-right tabular whitespace-nowrap text-muted-foreground">{segment.activity_level}%</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </div>
  )
}
