import { useState } from 'react'
import { Activity, AppWindow, ArrowRight, Clock, MousePointerClick, Settings2 } from 'lucide-react'
import { Link } from 'react-router'

import { EmptyState } from '@/components/common/empty-state'
import { FilterSelect, toOptions } from '@/components/common/filter-select'
import { PageHeader } from '@/components/common/page-header'
import { StatTile } from '@/components/common/stat-tile'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardAction, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/misc'
import { SegmentedControl } from '@/components/ui/segmented-control'
import { useActivityPolicy, useApplicationUsage } from '@/features/activity/api'
import { AppUsageTable } from '@/features/activity/components/app-usage-table'
import { formatDay, formatSeconds, percent, shiftDay, todayIn } from '@/features/activity/format'
import { RequirePermission } from '@/features/auth/guards'
import { WidgetError } from '@/features/dashboard/components/widget'
import { useTeams } from '@/features/people/api'
import { EmployeePicker } from '@/features/people/components/employee-picker'
import { useDocumentTitle } from '@/hooks/use-document-title'
import { useAuthStore, usePermissions } from '@/stores/auth-store'

type Range = 'today' | 'yesterday' | '7d' | '30d'

const RANGES: { value: Range; label: string }[] = [
  { value: 'today', label: 'Today' },
  { value: 'yesterday', label: 'Yesterday' },
  { value: '7d', label: '7 days' },
  { value: '30d', label: '30 days' },
]

function rangeDates(range: Range, today: string): { start: string; end: string } {
  switch (range) {
    case 'today':
      return { start: today, end: today }
    case 'yesterday':
      return { start: shiftDay(today, -1), end: shiftDay(today, -1) }
    case '7d':
      return { start: shiftDay(today, -6), end: today }
    case '30d':
      return { start: shiftDay(today, -29), end: today }
  }
}

function PolicySummary() {
  const policy = useActivityPolicy().data
  const { can } = usePermissions()
  if (!policy) return null
  return (
    <div className="flex flex-wrap items-center gap-2 text-[12px] text-muted-foreground">
      <span>Recording:</span>
      <Badge variant={policy.track_applications ? 'success' : 'secondary'}>
        Applications {policy.track_applications ? 'on' : 'off'}
      </Badge>
      <Badge variant={policy.capture_window_titles ? 'info' : 'secondary'}>
        Window titles {policy.capture_window_titles ? 'on' : 'off'}
      </Badge>
      {policy.excluded_apps.length > 0 && <Badge variant="outline">{policy.excluded_apps.length} excluded</Badge>}
      {can('POLICY_MANAGE') && (
        <Button asChild variant="link" size="sm" className="h-auto px-1 text-[12px]">
          <Link to="/settings/workspace">
            <Settings2 /> Policy
          </Link>
        </Button>
      )}
    </div>
  )
}

function ActivityReport() {
  const timeZone = useAuthStore((s) => s.company?.timezone ?? 'UTC')
  const today = todayIn(timeZone)
  const [range, setRange] = useState<Range>('7d')
  const [teamId, setTeamId] = useState<string | null>(null)
  const [employeeId, setEmployeeId] = useState<string | null>(null)
  const teams = useTeams()
  const { start, end } = rangeDates(range, today)
  const query = useApplicationUsage({ start, end, team_id: teamId ?? undefined, employee_id: employeeId ?? undefined })
  const report = query.data
  const period = start === end ? formatDay(start) : `${formatDay(start, 'short')} – ${formatDay(end, 'short')}`

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center gap-3">
        <SegmentedControl label="Period" value={range} onChange={setRange} options={RANGES} />
        <FilterSelect label="Team" value={teamId} onChange={setTeamId} options={toOptions(teams.data)} allLabel="All teams" />
        <div className="w-56">
          <EmployeePicker value={employeeId} onChange={setEmployeeId} placeholder="All people" />
        </div>
        <div className="ml-auto">
          <PolicySummary />
        </div>
      </div>

      {query.isError ? (
        <Card>
          <WidgetError error={query.error} onRetry={() => void query.refetch()} />
        </Card>
      ) : !report ? (
        <div className="grid gap-4 sm:grid-cols-3">
          <Skeleton className="h-28" />
          <Skeleton className="h-28" />
          <Skeleton className="h-28" />
        </div>
      ) : (
        <div className={query.isFetching ? 'space-y-6 opacity-70 transition-opacity' : 'space-y-6'}>
          <div className="grid gap-4 sm:grid-cols-3">
            <StatTile icon={Clock} label="Tracked time" value={formatSeconds(report.total_seconds)} hint={`In applications · ${period}`} />
            <StatTile
              icon={MousePointerClick}
              label="Active time"
              value={formatSeconds(report.active_seconds)}
              hint={`${percent(report.active_seconds, report.total_seconds)}% of tracked time had keyboard or mouse input`}
            />
            <StatTile icon={AppWindow} label="Applications" value={String(report.applications.length)} hint="Distinct applications used" />
          </div>
          <Card>
            <CardHeader>
              <CardTitle>Application usage</CardTitle>
              <CardDescription>
                {period} · {report.timezone.replaceAll('_', ' ')}
              </CardDescription>
              {employeeId && (
                <CardAction>
                  <Button asChild variant="outline" size="sm">
                    <Link to={`/people/employees/${employeeId}?tab=activity`}>
                      Daily timeline <ArrowRight />
                    </Link>
                  </Button>
                </CardAction>
              )}
            </CardHeader>
            {report.applications.length === 0 ? (
              <EmptyState
                size="sm"
                icon={Activity}
                title="No application activity in this period"
                description="Application usage is recorded by the WorkPulse desktop agent while people are in a work session."
              />
            ) : (
              <div className="mt-3 border-t">
                <AppUsageTable
                  applications={report.applications}
                  totalSeconds={report.total_seconds}
                  showPeople={!employeeId}
                  caption={`Application usage, ${period}`}
                />
              </div>
            )}
          </Card>
        </div>
      )}
    </div>
  )
}

export default function ActivityPage() {
  useDocumentTitle('Activity')
  return (
    <div className="space-y-6">
      <PageHeader
        title="Activity"
        description="Application usage and active time recorded by the desktop agent during work sessions."
        icon={Activity}
      />
      <RequirePermission permission="ACTIVITY_VIEW">
        <ActivityReport />
      </RequirePermission>
    </div>
  )
}
