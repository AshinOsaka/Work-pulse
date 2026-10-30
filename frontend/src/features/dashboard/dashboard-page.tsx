import { useState } from 'react'
import { ArrowRight, UserRound, UsersRound } from 'lucide-react'
import { Link } from 'react-router'

import { FilterSelect, toOptions } from '@/components/common/filter-select'
import { PageHeader } from '@/components/common/page-header'
import { PersonAvatar } from '@/components/common/person'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { SegmentedControl } from '@/components/ui/segmented-control'
import { ActivityTimelineCard } from '@/features/dashboard/components/activity-timeline'
import { DateRangeChip } from '@/features/dashboard/components/date-range-chip'
import { AttendanceCard } from '@/features/dashboard/components/org/attendance-card'
import { AttendanceCalendarCard } from '@/features/dashboard/components/org/attendance-calendar-card'
import { ConnectedNowCard } from '@/features/dashboard/components/org/connected-now-card'
import { MemberProductivityCard } from '@/features/dashboard/components/org/member-productivity-card'
import { OrgTrendCard } from '@/features/dashboard/components/org/org-trend-card'
import { TimeTrackerReportCard } from '@/features/dashboard/components/org/time-tracker-report-card'
import { TodayDataCard } from '@/features/dashboard/components/org/today-data-card'
import { WebsitesApplicationsCard } from '@/features/dashboard/components/org/websites-apps-card'
import { WorkHoursCard } from '@/features/dashboard/components/org/work-hours-card'
import { useOrgOverview } from '@/features/dashboard/data/use-org-overview'
import { useIndividualOverview } from '@/features/dashboard/data/use-individual-overview'
import { SetupChecklist } from '@/features/dashboard/components/setup-checklist'
import { EmployeePicker } from '@/features/people/components/employee-picker'
import { MyWorkCard } from '@/features/work/components/my-work-card'
import { RANGES, rangeFor, type RangeKey } from '@/features/productivity/meta'
import { todayIn } from '@/features/activity/format'
import { greeting, ROLE_LABELS } from '@/lib/format'
import { useAuthStore, usePermissions } from '@/stores/auth-store'

/** Maps a react-query result to the common widget status props. */
function widgetStatus(q: { isPending: boolean; isError: boolean; error: unknown; isPlaceholderData: boolean; refetch: () => unknown }) {
  return {
    isPending: q.isPending,
    isError: q.isError,
    error: q.error,
    isRefreshing: q.isPlaceholderData,
    onRetry: () => void q.refetch(),
  }
}

/** Members without monitoring permissions get a personal start page instead of team analytics. */
function PersonalHome() {
  const user = useAuthStore((s) => s.user)
  const company = useAuthStore((s) => s.company)
  if (!user) return null
  return (
    <div className="space-y-6">
      <PageHeader title={`${greeting()}, ${user.full_name.split(' ')[0]}`} description={company?.name} />
      <Card className="flex flex-col gap-4 p-6 sm:flex-row sm:items-center">
        <PersonAvatar name={user.full_name} seed={user.employee_id ?? user.id} className="size-12 text-base" />
        <div className="flex-1">
          <p className="font-semibold">{user.full_name}</p>
          <p className="text-[13px] text-muted-foreground">
            {ROLE_LABELS[user.role]} · {user.email}
          </p>
        </div>
        {user.employee_id && (
          <Button variant="outline" asChild>
            <Link to={`/people/employees/${user.employee_id}`}>
              <UserRound /> My profile <ArrowRight />
            </Link>
          </Button>
        )}
      </Card>
      <Card className="p-6 text-[13px] text-muted-foreground">
        Track your work sessions with the WorkPulse desktop agent.
      </Card>
    </div>
  )
}

type OrgView = 'organization' | 'team' | 'individual'

/** The workforce widget grid, shared by the Organization and Team views (the team filter scopes it). */
function WorkforceWidgets({ o, teamId }: { o: ReturnType<typeof useOrgOverview>; teamId: string | null }) {
  return (
    <>
      <div className="wp-stagger grid gap-5 xl:grid-cols-2">
        <ConnectedNowCard {...widgetStatus(o.presence)} data={o.presence.data} teamId={teamId} />
        <WorkHoursCard {...widgetStatus(o.productivity)} totals={o.productivity.data?.totals} days={o.productivity.data?.days} />
      </div>

      {/* Main charts (2/3) beside a narrow sidebar (1/3) of member ranking + the activity feed. */}
      <div className="grid gap-5 xl:grid-cols-3">
        <div className="wp-stagger space-y-5 xl:col-span-2">
          <OrgTrendCard {...widgetStatus(o.productivity)} days={o.productivity.data?.days} />
          <WebsitesApplicationsCard
            {...widgetStatus(o.websites)}
            websites={o.websites.data}
            applications={o.applications.data}
            isPending={o.websites.isPending || o.applications.isPending}
          />
          <AttendanceCard {...widgetStatus(o.attendance)} data={o.attendance.data} />
        </div>
        <div className="wp-stagger space-y-5">
          <MemberProductivityCard {...widgetStatus(o.productivity)} rows={o.productivity.data?.rows} />
          <ActivityTimelineCard {...widgetStatus(o.activity)} data={o.activity.data} sample={false} />
        </div>
      </div>
    </>
  )
}

function OrganizationDashboard() {
  const user = useAuthStore((s) => s.user)
  const company = useAuthStore((s) => s.company)
  const [view, setView] = useState<OrgView>('organization')
  const [rangeKey, setRangeKey] = useState<RangeKey>('7d')
  const [custom, setCustom] = useState<{ start: string; end: string } | null>(null)
  const [teamId, setTeamId] = useState<string | null>(null)
  const [employeeId, setEmployeeId] = useState<string | null>(null)

  const timeZone = company?.timezone ?? 'UTC'
  // A preset (Today / 7 / 14 / 30 days) or a custom range chosen from the calendar chip.
  const range = custom ?? rangeFor(rangeKey, timeZone)
  const o = useOrgOverview(range, teamId)

  return (
    <div className="space-y-5">
      <PageHeader title={`${greeting()}, ${user?.full_name.split(' ')[0] ?? ''}`} />

      {/* Views + scope: one unified toolbar drives every widget below. */}
      <div className="flex justify-center">
        <div className="flex flex-wrap items-center justify-center gap-2 rounded-2xl border bg-card px-2 py-2 shadow-xs">
          <SegmentedControl<OrgView>
            label="View"
            size="sm"
            value={view}
            onChange={setView}
            options={[
              { value: 'organization', label: 'Organization' },
              { value: 'team', label: 'Team' },
              { value: 'individual', label: 'Individual' },
            ]}
          />
          <span className="mx-0.5 hidden h-6 w-px bg-border sm:block" aria-hidden />
          {view === 'individual' ? (
            <div className="w-48">
              <EmployeePicker value={employeeId} onChange={setEmployeeId} placeholder="Select a member" />
            </div>
          ) : (
            <FilterSelect label="Team" value={teamId} onChange={setTeamId} options={toOptions(o.teams.data)} allLabel="All teams" />
          )}
          <SegmentedControl<RangeKey>
            label="Range"
            size="sm"
            value={rangeKey}
            onChange={(v) => {
              setRangeKey(v)
              setCustom(null)
            }}
            options={RANGES}
          />
          <DateRangeChip
            start={range.start}
            end={range.end}
            max={todayIn(timeZone)}
            isCustom={custom !== null}
            onChange={(start, end) => setCustom({ start, end })}
            onReset={() => setCustom(null)}
          />
        </div>
      </div>

      {view === 'individual' ? (
        <IndividualView employeeId={employeeId} range={range} timeZone={timeZone} />
      ) : view === 'team' ? (
        teamId ? (
          <WorkforceWidgets o={o} teamId={teamId} />
        ) : (
          <Card className="flex flex-col items-center gap-2 p-10 text-center">
            <UsersRound className="size-7 text-muted-foreground" aria-hidden />
            <p className="font-semibold">Select a team</p>
            <p className="max-w-sm text-[13px] text-muted-foreground">
              Choose a team above to see its live presence, work hours, productivity, websites and attendance.
            </p>
          </Card>
        )
      ) : (
        <>
          <SetupChecklist />
          <MyWorkCard />
          <WorkforceWidgets o={o} teamId={teamId} />
        </>
      )}
    </div>
  )
}

function IndividualView({ employeeId, range, timeZone }: { employeeId: string | null; range: { start: string; end: string }; timeZone: string }) {
  const ind = useIndividualOverview(employeeId, range, timeZone)

  if (!employeeId) {
    return (
      <Card className="flex flex-col items-center gap-2 p-10 text-center">
        <UserRound className="size-7 text-muted-foreground" aria-hidden />
        <p className="font-semibold">Select a member</p>
        <p className="max-w-sm text-[13px] text-muted-foreground">
          Choose a person above to see their work hours, productivity, websites, attendance and a day-by-day time tracker report.
        </p>
      </Card>
    )
  }

  return (
    <div className="space-y-5">
      <div className="wp-stagger grid gap-5 xl:grid-cols-2">
        <WorkHoursCard {...widgetStatus(ind.productivity)} totals={ind.productivity.data?.totals} days={ind.productivity.data?.days} />
        <TodayDataCard {...widgetStatus(ind.today)} data={ind.today.data} />
      </div>

      <div className="grid gap-5 xl:grid-cols-3">
        <OrgTrendCard {...widgetStatus(ind.productivity)} days={ind.productivity.data?.days} />
        <WebsitesApplicationsCard
          {...widgetStatus(ind.websites)}
          websites={ind.websites.data}
          applications={ind.applications.data}
          isPending={ind.websites.isPending || ind.applications.isPending}
        />
      </div>

      <div className="grid gap-5 xl:grid-cols-2">
        <AttendanceCalendarCard {...widgetStatus(ind.calendar)} days={ind.calendar.data?.days} month={ind.month} />
        <TimeTrackerReportCard
          {...widgetStatus(ind.productivity)}
          days={ind.productivity.data?.days}
          totalProductiveSeconds={ind.productivity.data?.totals.productive_seconds}
        />
      </div>
    </div>
  )
}

export default function DashboardPage() {
  const { can } = usePermissions()
  return can('ACTIVITY_VIEW') ? <OrganizationDashboard /> : <PersonalHome />
}
