import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { Camera, ChevronLeft, ChevronRight } from 'lucide-react'

import { EmptyState } from '@/components/common/empty-state'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/misc'
import { formatDay, shiftDay, todayIn } from '@/features/activity/format'
import { WidgetError } from '@/features/dashboard/components/widget'
import { useScreenshots, useScreenshotTimeline } from '@/features/screenshots/api'
import { ScreenshotGrid } from '@/features/screenshots/components/screenshot-grid'
import { ScreenshotTimeline } from '@/features/screenshots/components/screenshot-timeline'
import { ScreenshotViewer } from '@/features/screenshots/components/screenshot-viewer'
import { hourIn } from '@/features/screenshots/format'
import { useAuthStore } from '@/stores/auth-store'

interface ScreenshotGalleryProps {
  employeeId?: string
  teamId?: string
  /** Extra filters rendered in the same row as the date controls. */
  filters?: ReactNode
  emptyDescription: string
}

export function ScreenshotGallery({ employeeId, teamId, filters, emptyDescription }: ScreenshotGalleryProps) {
  const timeZone = useAuthStore((s) => s.company?.timezone ?? 'UTC')
  const today = todayIn(timeZone)
  const [day, setDay] = useState(today)
  // The hour filter belongs to one day/person/team selection and resets when that changes.
  const selection = `${day}|${employeeId ?? ''}|${teamId ?? ''}`
  const [hourState, setHourState] = useState<{ selection: string; hour: number | null }>({ selection, hour: null })
  const hour = hourState.selection === selection ? hourState.hour : null
  const setHour = useCallback((value: number | null) => setHourState({ selection, hour: value }), [selection])
  const [open, setOpen] = useState<number | null>(null)
  const pendingOpen = useRef<string | null>(null)

  const base = { day, employee_id: employeeId, team_id: teamId }
  const timeline = useScreenshotTimeline(base)
  const list = useScreenshots({ ...base, hour: hour ?? undefined })
  const items = useMemo(() => list.data?.pages.flatMap((p) => p.items) ?? [], [list.data])
  const tz = list.data?.pages[0]?.timezone ?? timeZone

  // Opening a capture from the timeline: narrow the grid to its hour, then page until it is loaded.
  const { hasNextPage, isFetchingNextPage, fetchNextPage } = list
  useEffect(() => {
    const id = pendingOpen.current
    if (!id || !list.data) return
    const index = items.findIndex((i) => i.id === id)
    if (index >= 0) {
      pendingOpen.current = null
      setOpen(index)
    } else if (hasNextPage && !isFetchingNextPage) {
      void fetchNextPage()
    } else if (!hasNextPage) {
      pendingOpen.current = null
    }
  }, [items, list.data, hasNextPage, isFetchingNextPage, fetchNextPage])
  const openCapture = (id: string) => {
    const index = items.findIndex((i) => i.id === id)
    if (index >= 0) return setOpen(index)
    const capture = timeline.data?.captures?.find((c) => c.id === id)
    if (!capture) return
    pendingOpen.current = id
    setHour(hourIn(capture.captured_at, tz))
  }

  const refetchList = list.refetch
  const expired = useRef(false)
  const onExpired = useCallback(() => {
    if (expired.current) return
    expired.current = true
    void refetchList().finally(() => (expired.current = false))
  }, [refetchList])

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-1">
          <Button variant="outline" size="icon-sm" aria-label="Previous day" onClick={() => setDay(shiftDay(day, -1))}>
            <ChevronLeft />
          </Button>
          <label className="sr-only" htmlFor="screenshot-day">
            Day
          </label>
          <input
            id="screenshot-day"
            type="date"
            value={day}
            max={today}
            onChange={(e) => e.target.value && setDay(e.target.value)}
            className="h-8 rounded-md border border-input bg-card px-2.5 text-[13px] shadow-xs outline-none focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/25"
          />
          <Button
            variant="outline"
            size="icon-sm"
            aria-label="Next day"
            disabled={day >= today}
            onClick={() => setDay(shiftDay(day, 1))}
          >
            <ChevronRight />
          </Button>
          <Button variant="ghost" size="sm" disabled={day === today} onClick={() => setDay(today)}>
            Today
          </Button>
        </div>
        {filters}
      </div>

      <Card className="p-5">
        <p className="mb-3 text-[13px] font-semibold">
          {formatDay(day)} <span className="font-normal text-muted-foreground">· {tz.replaceAll('_', ' ')}</span>
        </p>
        {timeline.data ? (
          <ScreenshotTimeline
            timeline={timeline.data}
            selectedHour={hour}
            onSelectHour={setHour}
            onOpenCapture={timeline.data.captures ? openCapture : undefined}
          />
        ) : (
          <Skeleton className="h-24" />
        )}
      </Card>

      {list.isError ? (
        <Card>
          <WidgetError error={list.error} onRetry={() => void list.refetch()} />
        </Card>
      ) : !list.data ? (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
          {Array.from({ length: 8 }, (_, i) => (
            <Skeleton key={i} className="aspect-video" />
          ))}
        </div>
      ) : items.length === 0 ? (
        <Card>
          <EmptyState icon={Camera} title="No screenshots" description={emptyDescription} />
        </Card>
      ) : (
        <div className={list.isFetching && !list.isFetchingNextPage ? 'opacity-80 transition-opacity' : undefined}>
          <ScreenshotGrid
            items={items}
            timeZone={tz}
            showEmployee={!employeeId}
            onOpen={setOpen}
            onExpired={onExpired}
          />
          {list.hasNextPage && (
            <div className="mt-6 flex justify-center">
              <Button variant="outline" loading={list.isFetchingNextPage} onClick={() => void list.fetchNextPage()}>
                Load older screenshots
              </Button>
            </div>
          )}
        </div>
      )}

      <ScreenshotViewer items={items} index={open} timeZone={tz} onIndexChange={setOpen} />
    </div>
  )
}
