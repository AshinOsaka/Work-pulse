import { useState } from 'react'
import { AppWindow, ChevronLeft, ChevronRight } from 'lucide-react'

import { EmptyState } from '@/components/common/empty-state'
import { Button } from '@/components/ui/button'
import { Card, CardAction, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/misc'
import { useEmployeeActivity } from '@/features/activity/api'
import { AppUsageTable } from '@/features/activity/components/app-usage-table'
import { DayTimeline } from '@/features/activity/components/day-timeline'
import { formatDay, formatSeconds, percent, shiftDay, todayIn } from '@/features/activity/format'
import { WidgetError } from '@/features/dashboard/components/widget'
import { useAuthStore } from '@/stores/auth-store'

function Stat({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div>
      <dt className="text-[12px] text-muted-foreground">{label}</dt>
      <dd className="mt-0.5 text-lg font-semibold tracking-tight tabular">
        {value}
        {hint && <span className="ml-1.5 text-[12px] font-normal text-muted-foreground">{hint}</span>}
      </dd>
    </div>
  )
}

/** One employee's application activity for a day, in the workspace timezone. */
export function EmployeeActivityPanel({ employeeId, firstName }: { employeeId: string; firstName: string }) {
  const timeZone = useAuthStore((s) => s.company?.timezone ?? 'UTC')
  const today = todayIn(timeZone)
  const [day, setDay] = useState(today)
  const query = useEmployeeActivity(employeeId, day)
  const data = query.data

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>{day === today ? 'Today' : day === shiftDay(today, -1) ? 'Yesterday' : formatDay(day)}</CardTitle>
          <CardDescription>
            {formatDay(day)} · {timeZone.replaceAll('_', ' ')}
          </CardDescription>
          <CardAction className="flex items-center gap-1">
            <Button variant="outline" size="icon-sm" aria-label="Previous day" onClick={() => setDay(shiftDay(day, -1))}>
              <ChevronLeft />
            </Button>
            <Button variant="outline" size="sm" disabled={day === today} onClick={() => setDay(today)}>
              Today
            </Button>
            <Button
              variant="outline"
              size="icon-sm"
              aria-label="Next day"
              disabled={day >= today}
              onClick={() => setDay(shiftDay(day, 1))}
            >
              <ChevronRight />
            </Button>
          </CardAction>
        </CardHeader>
        {query.isError ? (
          <WidgetError error={query.error} onRetry={() => void query.refetch()} />
        ) : !data ? (
          <div className="space-y-4 p-5">
            <Skeleton className="h-12" />
            <Skeleton className="h-10" />
          </div>
        ) : data.segments.length === 0 ? (
          <EmptyState
            size="sm"
            icon={AppWindow}
            title="No application activity"
            description={`Nothing was recorded for ${firstName} on this day. Activity is captured by the WorkPulse desktop agent only during work sessions.`}
          />
        ) : (
          <div className={query.isFetching ? 'opacity-70 transition-opacity' : undefined}>
            <dl className="grid grid-cols-2 gap-4 border-b px-5 pt-4 pb-4 sm:grid-cols-3">
              <Stat label="Tracked time" value={formatSeconds(data.tracked_seconds)} />
              <Stat
                label="Active time"
                value={formatSeconds(data.active_seconds)}
                hint={`${percent(data.active_seconds, data.tracked_seconds)}%`}
              />
              <Stat label="Applications" value={String(data.applications.length)} />
            </dl>
            <DayTimeline segments={data.segments} applications={data.applications} timeZone={data.timezone} />
            {data.truncated && (
              <p className="px-5 pb-4 text-[12px] text-muted-foreground">
                Showing the first {data.segments.length} segments of this day.
              </p>
            )}
          </div>
        )}
      </Card>
      {data && data.applications.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Applications</CardTitle>
            <CardDescription>Time in each application on {formatDay(day, 'short')}</CardDescription>
          </CardHeader>
          <div className="mt-3 border-t">
            <AppUsageTable
              applications={data.applications}
              totalSeconds={data.tracked_seconds}
              caption={`Application usage on ${formatDay(day)}`}
            />
          </div>
        </Card>
      )}
    </div>
  )
}
