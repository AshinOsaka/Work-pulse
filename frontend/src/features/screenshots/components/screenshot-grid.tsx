import { useMemo } from 'react'

import { PersonAvatar } from '@/components/common/person'
import { formatClock } from '@/features/activity/format'
import { hourIn, hourLabel } from '@/features/screenshots/format'
import type { ScreenshotItem } from '@/types/api'

interface ScreenshotGridProps {
  items: ScreenshotItem[]
  timeZone: string
  /** Hide the person on each card (single-employee views). */
  showEmployee: boolean
  onOpen: (index: number) => void
  /** A signed URL expired while the page was open. */
  onExpired: () => void
}

/** Thumbnails grouped by local hour, newest first. */
export function ScreenshotGrid({ items, timeZone, showEmployee, onOpen, onExpired }: ScreenshotGridProps) {
  const groups = useMemo(() => {
    const byHour = new Map<number, { item: ScreenshotItem; index: number }[]>()
    items.forEach((item, index) => {
      const hour = hourIn(item.captured_at, timeZone)
      byHour.set(hour, [...(byHour.get(hour) ?? []), { item, index }])
    })
    return [...byHour.entries()]
  }, [items, timeZone])

  return (
    <div className="space-y-6">
      {groups.map(([hour, entries]) => (
        <section key={hour} aria-labelledby={`hour-${hour}`}>
          <h3 id={`hour-${hour}`} className="mb-2.5 flex items-baseline gap-2 text-[13px] font-semibold">
            {hourLabel(hour)}
            <span className="text-[12px] font-normal text-muted-foreground">
              {entries.length} {entries.length === 1 ? 'screenshot' : 'screenshots'}
            </span>
          </h3>
          <ul className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4 2xl:grid-cols-6">
            {entries.map(({ item, index }) => (
              <li key={item.id}>
                <button
                  type="button"
                  onClick={() => onOpen(index)}
                  className="group w-full overflow-hidden rounded-lg border bg-card text-left shadow-xs transition hover:border-primary/40 hover:shadow-card focus-visible:ring-[3px] focus-visible:ring-ring/40 focus-visible:outline-none"
                  aria-label={`Open screenshot of ${item.employee.full_name} at ${formatClock(item.captured_at, timeZone)}`}
                >
                  <div className="aspect-video overflow-hidden bg-muted">
                    <img
                      src={item.thumbnail_url}
                      alt=""
                      loading="lazy"
                      decoding="async"
                      referrerPolicy="no-referrer"
                      draggable={false}
                      onError={onExpired}
                      className="size-full object-cover object-top transition duration-300 group-hover:scale-[1.02]"
                    />
                  </div>
                  <div className="flex items-center gap-2 px-2.5 py-2">
                    {showEmployee && <PersonAvatar name={item.employee.full_name} seed={item.employee.id} className="size-5 text-[9px]" />}
                    <span className="min-w-0 flex-1 truncate text-[12px] font-medium">
                      {showEmployee ? item.employee.full_name : formatClock(item.captured_at, timeZone)}
                    </span>
                    {showEmployee && (
                      <span className="shrink-0 text-[11px] text-muted-foreground tabular">
                        {formatClock(item.captured_at, timeZone)}
                      </span>
                    )}
                  </div>
                </button>
              </li>
            ))}
          </ul>
        </section>
      ))}
    </div>
  )
}
