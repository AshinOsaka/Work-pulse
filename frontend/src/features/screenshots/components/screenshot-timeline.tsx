import { useState } from 'react'

import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { formatClock } from '@/features/activity/format'
import { ViewToggle, type ViewMode } from '@/features/dashboard/components/widget'
import { hourLabel, minuteOfDay } from '@/features/screenshots/format'
import { cn } from '@/lib/utils'
import type { ScreenshotTimeline as Timeline } from '@/types/api'

interface ScreenshotTimelineProps {
  timeline: Timeline
  selectedHour: number | null
  onSelectHour: (hour: number | null) => void
  onOpenCapture?: (id: string) => void
}

/** Captures per hour of the day; selecting an hour filters the gallery. Single employee: individual capture ticks. */
export function ScreenshotTimeline({ timeline, selectedHour, onSelectHour, onOpenCapture }: ScreenshotTimelineProps) {
  const [view, setView] = useState<ViewMode>('chart')
  const max = Math.max(1, ...timeline.buckets.map((b) => b.count))
  const tz = timeline.timezone

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-[13px] text-muted-foreground">
          <span className="font-semibold text-foreground tabular">{timeline.total}</span>{' '}
          {timeline.total === 1 ? 'screenshot' : 'screenshots'}
          {selectedHour !== null && (
            <>
              {' '}
              · showing {hourLabel(selectedHour)}–{hourLabel((selectedHour + 1) % 24)}{' '}
              <button type="button" className="font-medium text-primary hover:underline" onClick={() => onSelectHour(null)}>
                Show all
              </button>
            </>
          )}
        </p>
        <ViewToggle value={view} onChange={setView} />
      </div>

      {view === 'chart' ? (
        <div>
          <fieldset className="m-0 flex h-20 min-w-0 items-end gap-[2px] border-0 p-0">
            <legend className="sr-only">Screenshots per hour; select an hour to filter</legend>
            {timeline.buckets.map((bucket) => {
              const selected = selectedHour === bucket.hour
              return (
                <button
                  key={bucket.hour}
                  type="button"
                  disabled={bucket.count === 0}
                  aria-pressed={selected}
                  aria-label={`${hourLabel(bucket.hour)}: ${bucket.count} screenshot${bucket.count === 1 ? '' : 's'}`}
                  title={`${hourLabel(bucket.hour)} · ${bucket.count}`}
                  onClick={() => onSelectHour(selected ? null : bucket.hour)}
                  className="group relative flex h-full flex-1 items-end rounded-sm outline-none focus-visible:ring-[3px] focus-visible:ring-ring/40 disabled:cursor-default"
                >
                  <span
                    className={cn(
                      'w-full rounded-t-[3px] transition-colors',
                      bucket.count === 0
                        ? 'h-[2px] bg-border'
                        : selected
                          ? 'bg-primary'
                          : selectedHour === null
                            ? 'bg-chart-1/80 group-hover:bg-chart-1'
                            : 'bg-chart-1/30 group-hover:bg-chart-1/60',
                    )}
                    style={bucket.count ? { height: `${Math.max(8, (bucket.count / max) * 100)}%` } : undefined}
                  />
                </button>
              )
            })}
          </fieldset>
          <div className="mt-1.5 grid grid-cols-8 text-[11px] text-muted-foreground tabular" aria-hidden>
            {[0, 3, 6, 9, 12, 15, 18, 21].map((h) => (
              <span key={h}>{hourLabel(h)}</span>
            ))}
          </div>
          {timeline.captures && timeline.captures.length > 0 && (
            <div className="relative mt-3 h-6 rounded-md bg-muted/60" aria-label="Individual captures">
              {timeline.captures.map((capture) => {
                const minutes = minuteOfDay(capture.captured_at, tz)
                return (
                  <button
                    key={capture.id}
                    type="button"
                    onClick={() => onOpenCapture?.(capture.id)}
                    title={formatClock(capture.captured_at, tz)}
                    aria-label={`Open screenshot from ${formatClock(capture.captured_at, tz)}`}
                    className="absolute inset-y-1 w-[3px] -translate-x-1/2 rounded-full bg-chart-1 transition hover:inset-y-0 hover:w-[5px] focus-visible:ring-[3px] focus-visible:ring-ring/40 focus-visible:outline-none"
                    style={{ left: `${(minutes / 1440) * 100}%` }}
                  />
                )
              })}
            </div>
          )}
        </div>
      ) : (
        <div className="max-h-64 overflow-y-auto rounded-md border">
          <Table>
            <caption className="sr-only">Screenshots per hour</caption>
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                <TableHead className="pl-4">Hour</TableHead>
                <TableHead className="pr-4 text-right">Screenshots</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {timeline.buckets
                .filter((b) => b.count > 0)
                .map((b) => (
                  <TableRow key={b.hour} className="cursor-pointer" onClick={() => onSelectHour(b.hour)}>
                    <TableCell className="pl-4 tabular whitespace-nowrap">
                      {hourLabel(b.hour)}–{hourLabel((b.hour + 1) % 24)}
                    </TableCell>
                    <TableCell className="pr-4 text-right tabular whitespace-nowrap">{b.count}</TableCell>
                  </TableRow>
                ))}
            </TableBody>
          </Table>
        </div>
      )}
    </div>
  )
}
