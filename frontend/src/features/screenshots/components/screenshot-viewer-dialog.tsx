import { useMemo, useState } from 'react'
import { Camera, Download } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogTitle } from '@/components/ui/dialog'
import { Skeleton } from '@/components/ui/misc'
import { useScreenshotDetail, useScreenshots, useScreenshotTimeline } from '@/features/screenshots/api'
import { cn } from '@/lib/utils'

/** "9AM", "12PM", "1PM" for the hour-range pills. */
function hour12(hour: number): string {
  const period = hour < 12 ? 'AM' : 'PM'
  const h = hour % 12 === 0 ? 12 : hour % 12
  return `${h}${period}`
}

function clockWithSeconds(value: string, timeZone: string): string {
  try {
    return new Intl.DateTimeFormat('en-GB', {
      timeZone,
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: true,
    }).format(new Date(value))
  } catch {
    return value
  }
}

/** "IST (UTC+05:30)" from an IANA zone, falling back to the zone name. */
function timezoneLabel(timeZone: string): string {
  try {
    const now = new Date()
    const short = new Intl.DateTimeFormat('en-US', { timeZone, timeZoneName: 'short' })
      .formatToParts(now)
      .find((p) => p.type === 'timeZoneName')?.value
    const offset = new Intl.DateTimeFormat('en-US', { timeZone, timeZoneName: 'longOffset' })
      .formatToParts(now)
      .find((p) => p.type === 'timeZoneName')?.value
    const utc = offset?.replace('GMT', 'UTC') ?? timeZone
    return short && short !== utc ? `${short} (${utc})` : utc
  } catch {
    return timeZone
  }
}

export function ScreenshotViewerDialog({
  open,
  onOpenChange,
  employeeId,
  employeeName,
  day,
  timeZone,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  employeeId: string
  employeeName: string
  day: string
  timeZone: string
}) {
  const base = { day, employee_id: employeeId }
  const timeline = useScreenshotTimeline(base, open)
  // Only the hour/capture the viewer explicitly picked; the default is derived below, never stored, so a
  // change of day or person falls back cleanly without effects.
  const [pickedHour, setPickedHour] = useState<number | null>(null)
  const [pickedId, setPickedId] = useState<string | null>(null)

  const hours = useMemo(
    () => (timeline.data?.buckets ?? []).filter((b) => b.count > 0).sort((a, b) => a.hour - b.hour),
    [timeline.data],
  )
  const hour =
    pickedHour !== null && hours.some((h) => h.hour === pickedHour) ? pickedHour : (hours[0]?.hour ?? null)

  const list = useScreenshots({ ...base, hour: hour ?? undefined }, open && hour !== null)
  const items = useMemo(() => list.data?.pages.flatMap((p) => p.items) ?? [], [list.data])

  const activeId = pickedId && items.some((i) => i.id === pickedId) ? pickedId : (items[0]?.id ?? null)
  const detail = useScreenshotDetail(open ? activeId : null)
  const activeItem = items.find((i) => i.id === activeId) ?? null

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        className="flex h-[88vh] max-h-[88vh] w-full max-w-6xl flex-col gap-0 overflow-hidden p-0 sm:max-w-6xl"
        aria-describedby={undefined}
      >
        <div className="border-b px-6 py-4 pr-12">
          <DialogTitle className="text-[15px]">
            {employeeName} <span className="font-normal text-muted-foreground">(Timezone - {timezoneLabel(timeZone)})</span>
          </DialogTitle>
        </div>

        {/* Hour-range selector */}
        <div className="flex items-center gap-2 overflow-x-auto border-b px-6 py-3">
          <span className="shrink-0 text-[13px] font-medium text-muted-foreground">Select Time Range:</span>
          {timeline.isLoading ? (
            <Skeleton className="h-8 w-64" />
          ) : hours.length === 0 ? (
            <span className="text-[13px] text-muted-foreground">No screenshots on this day.</span>
          ) : (
            hours.map((b) => (
              <button
                key={b.hour}
                type="button"
                aria-pressed={hour === b.hour}
                onClick={() => setPickedHour(b.hour)}
                className={cn(
                  'inline-flex shrink-0 items-center gap-2 rounded-full border px-3.5 py-1.5 text-[13px] font-medium transition',
                  hour === b.hour
                    ? 'border-primary bg-primary text-primary-foreground'
                    : 'bg-card text-foreground hover:border-primary/50',
                )}
              >
                {hour12(b.hour)} - {hour12((b.hour + 1) % 24)}
                <span
                  className={cn(
                    'inline-flex min-w-5 justify-center rounded-full px-1.5 text-[11px]',
                    hour === b.hour ? 'bg-primary-foreground/20' : 'bg-muted text-muted-foreground',
                  )}
                >
                  {b.count}
                </span>
              </button>
            ))
          )}
        </div>

        {/* Thumbnails + preview */}
        <div className="grid min-h-0 flex-1 grid-cols-[132px_1fr] overflow-hidden">
          <div className="min-h-0 overflow-y-auto border-r bg-subtle/40 p-2.5">
            {!list.data && hour !== null ? (
              <div className="space-y-2.5">
                {Array.from({ length: 4 }, (_, i) => (
                  <Skeleton key={i} className="h-20" />
                ))}
              </div>
            ) : (
              items.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => setPickedId(item.id)}
                  aria-pressed={activeId === item.id}
                  className={cn(
                    'mb-2.5 block w-full overflow-hidden rounded-lg border bg-card text-left transition hover:border-primary/50',
                    activeId === item.id && 'border-primary ring-1 ring-primary',
                  )}
                >
                  <img
                    src={item.thumbnail_url}
                    alt=""
                    loading="lazy"
                    decoding="async"
                    referrerPolicy="no-referrer"
                    draggable={false}
                    onError={() => void list.refetch()}
                    className="aspect-video w-full object-cover object-top"
                  />
                  <span className="block px-2 py-1 text-center text-[11px] tabular text-muted-foreground">
                    {clockWithSeconds(item.captured_at, timeZone)}
                  </span>
                </button>
              ))
            )}
          </div>

          <div className="relative min-h-0 overflow-auto bg-muted/40 p-4">
            {activeItem ? (
              detail.data ? (
                <img
                  src={detail.data.image_url}
                  alt={`Screenshot at ${clockWithSeconds(activeItem.captured_at, timeZone)}`}
                  referrerPolicy="no-referrer"
                  draggable={false}
                  onError={() => void detail.refetch()}
                  className="mx-auto max-h-full w-auto max-w-full rounded-lg border bg-card object-contain shadow-sm"
                />
              ) : (
                <img
                  src={activeItem.thumbnail_url}
                  alt=""
                  referrerPolicy="no-referrer"
                  draggable={false}
                  className="mx-auto max-h-full w-auto max-w-full rounded-lg border bg-card object-contain opacity-80"
                />
              )
            ) : (
              <div className="flex h-full flex-col items-center justify-center gap-2 text-muted-foreground">
                <Camera className="size-6" aria-hidden />
                <p className="text-[13px]">Select a time range to see screenshots.</p>
              </div>
            )}
            {activeItem && detail.data && (
              <div className="absolute right-6 bottom-6 flex items-center gap-2 rounded-lg border bg-card/90 px-3 py-1.5 text-[12px] shadow-sm backdrop-blur">
                <span className="tabular text-muted-foreground">
                  {clockWithSeconds(activeItem.captured_at, timeZone)}
                  {detail.data.application ? ` · ${detail.data.application}` : ''}
                </span>
                <Button asChild size="sm" variant="ghost" className="h-6 px-2">
                  <a href={detail.data.image_url} target="_blank" rel="noreferrer" download>
                    <Download /> Open
                  </a>
                </Button>
              </div>
            )}
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}
