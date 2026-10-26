import { useState } from 'react'
import { ArrowRight, UserRound } from 'lucide-react'
import { Link } from 'react-router'

import { FilterSelect, toOptions } from '@/components/common/filter-select'
import { PageHeader } from '@/components/common/page-header'
import { PersonAvatar } from '@/components/common/person'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { SegmentedControl } from '@/components/ui/segmented-control'
import { ActivityTimelineCard } from '@/features/dashboard/components/activity-timeline'
import { AttendanceCard } from '@/features/dashboard/components/org/attendance-card'
import { ConnectedNowCard } from '@/features/dashboard/components/org/connected-now-card'
import { MemberProductivityCard } from '@/features/dashboard/components/org/member-productivity-card'
import { OrgTrendCard } from '@/features/dashboard/components/org/org-trend-card'
import { WebsitesApplicationsCard } from '@/features/dashboard/components/org/websites-apps-card'
import { WorkHoursCard } from '@/features/dashboard/components/org/work-hours-card'
import { useOrgOverview } from '@/features/dashboard/data/use-org-overview'
import { SetupChecklist } from '@/features/dashboard/components/setup-checklist'
import { MyWorkCard } from '@/features/work/components/my-work-card'
import { RANGES, rangeFor, type RangeKey } from '@/features/productivity/meta'
import { greeting, ROLE_LABELS } from '@/lib/format'
import { useAuthStore, usePermissions } from '@/stores/auth-store'

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

function OrganizationDashboard() {
  const user = useAuthStore((s) => s.user)
  const company = useAuthStore((s) => s.company)
  const [view, setView] = useState<OrgView>('organization')
  const [rangeKey, setRangeKey] = useState<RangeKey>('7d')
  const [teamId, setTeamId] = useState<string | null>(null)

  const timeZone = company?.timezone ?? 'UTC'
  const range = rangeFor(rangeKey, timeZone)
  const o = useOrgOverview(range, teamId)

  const status = (q: { isPending: boolean; isError: boolean; error: unknown; isPlaceholderData: boolean; refetch: () => unknown }) => ({
    isPending: q.isPending,
    isError: q.isError,
    error: q.error,
    isRefreshing: q.isPlaceholderData,
    onRetry: () => void q.refetch(),
  })

  return (
    <div className="space-y-5">
      <PageHeader
        title={`${greeting()}, ${user?.full_name.split(' ')[0] ?? ''}`}
        description={`Workforce overview for ${company?.name ?? 'your workspace'}`}
      />

      {/* Views + scope: one row drives every widget below. */}
      <div className="flex flex-wrap items-center gap-3">
        <SegmentedControl<OrgView>
          label="View"
          value={view}
          onChange={setView}
          options={[
            { value: 'organization', label: 'Organization View' },
            { value: 'team', label: 'Team View' },
            { value: 'individual', label: 'Individual View' },
          ]}
        />
        <div className="sm:ml-auto flex flex-wrap items-center gap-3">
          <FilterSelect label="Team" value={teamId} onChange={setTeamId} options={toOptions(o.teams.data)} allLabel="All teams" />
          <SegmentedControl<RangeKey> label="Range" value={rangeKey} onChange={setRangeKey} options={RANGES} />
          <p className="hidden text-[12px] text-muted-foreground tabular sm:block">
            {range.start} → {range.end}
          </p>
        </div>
      </div>

      {view !== 'organization' ? (
        <Card className="flex flex-col items-start gap-2 p-6">
          <p className="font-semibold">{view === 'team' ? 'Team View' : 'Individual View'} is coming next</p>
          <p className="text-[13px] text-muted-foreground">
            We're building this as the next step. For now, use the Organization View, or open a person from{' '}
            <Link to="/people" className="font-medium text-primary hover:underline">
              People
            </Link>
            .
          </p>
          <Button size="sm" variant="outline" onClick={() => setView('organization')}>
            Back to Organization View
          </Button>
        </Card>
      ) : (
        <>
          <SetupChecklist />
          <MyWorkCard />

          <div className="grid gap-5 xl:grid-cols-2">
            <ConnectedNowCard {...status(o.presence)} data={o.presence.data} teamId={teamId} />
            <WorkHoursCard {...status(o.productivity)} totals={o.productivity.data?.totals} />
          </div>

          {/* Main charts (2/3) beside a narrow sidebar (1/3) of member ranking + the activity feed. */}
          <div className="grid gap-5 xl:grid-cols-3">
            <div className="space-y-5 xl:col-span-2">
              <OrgTrendCard {...status(o.productivity)} days={o.productivity.data?.days} />
              <WebsitesApplicationsCard
                {...status(o.websites)}
                websites={o.websites.data}
                applications={o.applications.data}
                isPending={o.websites.isPending || o.applications.isPending}
              />
              <AttendanceCard {...status(o.attendance)} data={o.attendance.data} />
            </div>
            <div className="space-y-5">
              <MemberProductivityCard {...status(o.productivity)} rows={o.productivity.data?.rows} />
              <ActivityTimelineCard {...status(o.activity)} data={o.activity.data} sample={false} />
            </div>
          </div>
        </>
      )}
    </div>
  )
}

export default function DashboardPage() {
  const { can } = usePermissions()
  return can('ACTIVITY_VIEW') ? <OrganizationDashboard /> : <PersonalHome />
}
