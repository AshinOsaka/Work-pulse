import { useState } from 'react'
import { ArrowRight, UserRound } from 'lucide-react'
import { Link } from 'react-router'

import { FilterSelect, toOptions } from '@/components/common/filter-select'
import { PageHeader } from '@/components/common/page-header'
import { PersonAvatar } from '@/components/common/person'
import { StatusDot } from '@/components/common/status'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { SegmentedControl } from '@/components/ui/segmented-control'
import { ActivityTimelineCard } from '@/features/dashboard/components/activity-timeline'
import { KpiCards } from '@/features/dashboard/components/kpi-cards'
import { LiveEmployeesCard } from '@/features/dashboard/components/live-employees-card'
import { ProductivityTrendCard } from '@/features/dashboard/components/productivity-trend-card'
import { RecentAlertsCard } from '@/features/dashboard/components/recent-alerts-card'
import { SetupChecklist } from '@/features/dashboard/components/setup-checklist'
import { TeamActivityCard } from '@/features/dashboard/components/team-activity-card'
import type { DashboardFilters, Period } from '@/features/dashboard/data/types'
import { useDashboard } from '@/features/dashboard/data/use-dashboard'
import { MyWorkCard } from '@/features/work/components/my-work-card'
import { formatTime, greeting, ROLE_LABELS } from '@/lib/format'
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

interface QueryLike<T> {
  data: T
  isPending: boolean
  isError: boolean
  error: unknown
  isPlaceholderData: boolean
  refetch: () => unknown
}

function ManagerDashboard() {
  const user = useAuthStore((s) => s.user)
  const company = useAuthStore((s) => s.company)
  const [filters, setFilters] = useState<DashboardFilters>({ period: 'daily', teamId: null })
  const dashboard = useDashboard(filters)
  const { source } = dashboard

  const widget = <T,>(q: QueryLike<T>) => ({
    data: q.data,
    isPending: q.isPending,
    isError: q.isError,
    error: q.error,
    isRefreshing: q.isPlaceholderData,
    onRetry: () => void q.refetch(),
    sample: false,
  })

  return (
    <div className="space-y-5">
      <PageHeader
        title={`${greeting()}, ${user?.full_name.split(' ')[0] ?? ''}`}
        description={`Workforce overview for ${company?.name ?? 'your workspace'}`}
      />

      <SetupChecklist />
      <MyWorkCard />

      {/* One filter row scopes every widget below it. */}
      <div className="flex flex-wrap items-center gap-3">
        <SegmentedControl<Period>
          label="Period"
          value={filters.period}
          onChange={(period) => setFilters((f) => ({ ...f, period }))}
          options={[
            { value: 'daily', label: 'Daily' },
            { value: 'weekly', label: 'Weekly' },
            { value: 'monthly', label: 'Monthly' },
          ]}
        />
        <FilterSelect
          label="Team"
          value={filters.teamId}
          onChange={(v) => setFilters((f) => ({ ...f, teamId: v }))}
          options={toOptions(dashboard.teams.data)}
          allLabel="All teams"
        />
        <p className="flex items-center gap-2 text-[12px] text-muted-foreground sm:ml-auto">
          <StatusDot tone="neutral" />
          Workspace data
          {dashboard.updatedAt > 0 && ` · updated ${formatTime(dashboard.updatedAt)}`}
        </p>
      </div>

      <KpiCards data={dashboard.kpis.data} isPending={dashboard.kpis.isPending} period={filters.period} />

      <div className="grid gap-5 xl:grid-cols-3">
        <TeamActivityCard {...widget(dashboard.teamActivity)} available={source.availability.presence} />
        <ActivityTimelineCard {...widget(dashboard.activity)} />
        <ProductivityTrendCard
          {...widget(dashboard.trend)}
          period={filters.period}
          available={source.availability.productivity}
        />
        <LiveEmployeesCard {...widget(dashboard.employees)} available={source.availability.presence} />
        <RecentAlertsCard {...widget(dashboard.alerts)} available={source.availability.alerts} />
      </div>
    </div>
  )
}

export default function DashboardPage() {
  const { can } = usePermissions()
  return can('ACTIVITY_VIEW') ? <ManagerDashboard /> : <PersonalHome />
}
