import { useState } from 'react'
import { Activity, AppWindow, ArrowRight, Clock, Globe, MousePointerClick } from 'lucide-react'
import { Link } from 'react-router'

import { EmptyState } from '@/components/common/empty-state'
import { FilterSelect, toOptions } from '@/components/common/filter-select'
import { PageHeader } from '@/components/common/page-header'
import { StatTile } from '@/components/common/stat-tile'
import { Button } from '@/components/ui/button'
import { Card, CardAction, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/misc'
import { SegmentedControl } from '@/components/ui/segmented-control'
import { useApplicationUsage, useWebsiteUsage } from '@/features/activity/api'
import { AppUsageTable } from '@/features/activity/components/app-usage-table'
import { WebsiteUsageTable } from '@/features/activity/components/website-usage-table'
import { formatDay, formatSeconds, percent, shiftDay, todayIn } from '@/features/activity/format'
import { RequirePermission } from '@/features/auth/guards'
import { WidgetError } from '@/features/dashboard/components/widget'
import { useTeams } from '@/features/people/api'
import { EmployeePicker } from '@/features/people/components/employee-picker'
import { useDocumentTitle } from '@/hooks/use-document-title'
import { useAuthStore } from '@/stores/auth-store'

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

function ActivityReport() {
  const timeZone = useAuthStore((s) => s.company?.timezone ?? 'UTC')
  const today = todayIn(timeZone)
  const [range, setRange] = useState<Range>('7d')
  const [teamId, setTeamId] = useState<string | null>(null)
  const [employeeId, setEmployeeId] = useState<string | null>(null)
  const [tab, setTab] = useState<'applications' | 'websites'>('applications')
  const teams = useTeams()
  const { start, end } = rangeDates(range, today)
  const params = { start, end, team_id: teamId ?? undefined, employee_id: employeeId ?? undefined }
  const query = useApplicationUsage(params)
  const websiteQuery = useWebsiteUsage(params)
  const report = query.data
  const websites = websiteQuery.data
  const period = start === end ? formatDay(start) : `${formatDay(start, 'short')} – ${formatDay(end, 'short')}`

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center gap-3">
        <SegmentedControl label="Period" value={range} onChange={setRange} options={RANGES} />
        <FilterSelect label="Team" value={teamId} onChange={setTeamId} options={toOptions(teams.data)} allLabel="All teams" />
        <div className="w-56">
          <EmployeePicker value={employeeId} onChange={setEmployeeId} placeholder="All people" />
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
              <CardTitle>{tab === 'applications' ? 'Application usage' : 'Website usage'}</CardTitle>
              <CardDescription>{tab === 'applications' ? period : `${period} · domains only`}</CardDescription>
              <CardAction>
                <div className="flex items-center gap-2">
                  <SegmentedControl<'applications' | 'websites'>
                    label="Usage type"
                    size="sm"
                    value={tab}
                    onChange={setTab}
                    options={[
                      { value: 'applications', label: 'Applications' },
                      { value: 'websites', label: 'Websites' },
                    ]}
                  />
                  {employeeId && (
                    <Button asChild variant="outline" size="sm">
                      <Link to={`/people/employees/${employeeId}?tab=activity`}>
                        Daily timeline <ArrowRight />
                      </Link>
                    </Button>
                  )}
                </div>
              </CardAction>
            </CardHeader>
            {tab === 'applications' ? (
              report.applications.length === 0 ? (
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
              )
            ) : !websites ? (
              <div className="p-5">
                <Skeleton className="h-40" />
              </div>
            ) : !websites.tracking_enabled ? (
              <EmptyState
                size="sm"
                icon={Globe}
                title="Website tracking is off"
                description="Turn on “Record websites (domain only)” in the activity policy to see website usage."
              />
            ) : websites.websites.length === 0 ? (
              <EmptyState
                size="sm"
                icon={Globe}
                title="No website activity in this period"
                description="The desktop agent records the domain of sites visited in the browser (never the full address) while website tracking is on."
              />
            ) : (
              <div className="mt-3 border-t">
                <WebsiteUsageTable
                  websites={websites.websites}
                  totalSeconds={websites.total_seconds}
                  showPeople={!employeeId}
                  caption={`Website usage, ${period}`}
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
        description="Application usage and active time, recorded by the desktop agent."
        icon={Activity}
      />
      <RequirePermission permission="ACTIVITY_VIEW">
        <ActivityReport />
      </RequirePermission>
    </div>
  )
}
