import { ArrowRight, Building2, MailCheck, Plus, UserCheck, Users, UserRoundX, Plane } from 'lucide-react'
import { Link } from 'react-router'
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'

import { EmptyState } from '@/components/common/empty-state'
import { Person } from '@/components/common/person'
import { StatTile } from '@/components/common/stat-tile'
import { Button } from '@/components/ui/button'
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/misc'
import { usePeopleSummary } from '@/features/people/api'
import { errorMessage } from '@/lib/api-client'
import { usePermissions } from '@/stores/auth-store'
import type { PeopleSummary } from '@/types/api'

function DepartmentTooltip({ active, payload }: { active?: boolean; payload?: { payload?: { name: string; count: number } }[] }) {
  const row = payload?.[0]?.payload
  if (!active || !row) return null
  return (
    <div className="rounded-lg border bg-popover px-3 py-2 text-[12px] shadow-elevated">
      <p className="font-medium">{row.name}</p>
      <p className="text-muted-foreground tabular">
        {row.count} {row.count === 1 ? 'employee' : 'employees'}
      </p>
    </div>
  )
}

/** Head-count per department: a single series, so no legend — the title names it. */
function DepartmentChart({ summary }: { summary: PeopleSummary }) {
  const rows = summary.departments.slice(0, 8)
  const height = Math.max(160, rows.length * 36 + 24)
  return (
    <Card>
      <CardHeader>
        <CardTitle>Head-count by department</CardTitle>
        <CardDescription>Active and on-leave employees</CardDescription>
        <CardAction>
          <Button variant="ghost" size="sm" asChild>
            <Link to="/people/departments">
              Departments <ArrowRight />
            </Link>
          </Button>
        </CardAction>
      </CardHeader>
      <CardContent className="pt-2">
        {rows.length === 0 ? (
          <EmptyState size="sm" icon={Building2} title="No employees yet" description="Department head-count appears once people are added." />
        ) : (
          <div style={{ height }}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={rows} layout="vertical" margin={{ top: 4, right: 24, bottom: 4, left: 8 }} barCategoryGap={8}>
                <CartesianGrid horizontal={false} stroke="var(--chart-grid)" />
                <XAxis type="number" allowDecimals={false} tickLine={false} axisLine={false} tick={{ fill: 'var(--muted-foreground)', fontSize: 12 }} />
                <YAxis
                  type="category"
                  dataKey="name"
                  width={130}
                  tickLine={false}
                  axisLine={false}
                  tick={{ fill: 'var(--foreground)', fontSize: 12 }}
                />
                <Tooltip content={<DepartmentTooltip />} cursor={{ fill: 'var(--accent)' }} />
                <Bar dataKey="count" fill="var(--chart-1)" radius={[0, 4, 4, 0]} maxBarSize={22} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}
      </CardContent>
    </Card>
  )
}

export default function PeopleOverviewPage() {
  const { can } = usePermissions()
  const summary = usePeopleSummary()

  if (summary.isPending) {
    return (
      <div className="space-y-6">
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {Array.from({ length: 4 }, (_, i) => (
            <Skeleton key={i} className="h-28 rounded-xl" />
          ))}
        </div>
        <Skeleton className="h-72 rounded-xl" />
      </div>
    )
  }
  if (summary.isError) {
    return (
      <Card>
        <EmptyState icon={Users} title="Couldn't load the overview" description={errorMessage(summary.error)} />
      </Card>
    )
  }

  const data = summary.data
  const current = data.by_status.active + data.by_status.on_leave

  return (
    <div className="space-y-6">
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatTile icon={Users} label="Current employees" value={current} hint="Active and on leave" />
        <StatTile icon={UserCheck} label="Active" value={data.by_status.active} hint="Currently working" />
        <StatTile icon={Plane} label="On leave" value={data.by_status.on_leave} hint="Temporarily away" />
        <StatTile icon={MailCheck} label="Pending invitations" value={data.pending_invitations} hint="Awaiting acceptance" />
      </div>

      <div className="grid grid-cols-[minmax(0,1fr)] gap-6 xl:grid-cols-[minmax(0,1fr)_360px]">
        <DepartmentChart summary={data} />
        <Card>
          <CardHeader>
            <CardTitle>Recently added</CardTitle>
            <CardDescription>Newest people in your directory</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3.5 pt-3">
            {data.recent.length === 0 ? (
              <p className="text-[13px] text-muted-foreground">No employees yet.</p>
            ) : (
              data.recent.map((e) => <Person key={e.id} id={e.id} name={e.full_name} subtitle={e.job_title ?? e.email} />)
            )}
            {data.by_status.terminated > 0 && (
              <p className="flex items-center gap-1.5 border-t pt-3 text-[12px] text-muted-foreground">
                <UserRoundX className="size-3.5" /> {data.by_status.terminated} former{' '}
                {data.by_status.terminated === 1 ? 'employee' : 'employees'} not shown in counts
              </p>
            )}
          </CardContent>
        </Card>
      </div>

      {can('EMPLOYEE_MANAGE') && data.total <= 1 && (
        <Card className="border-dashed bg-subtle/60">
          <EmptyState
            icon={Plus}
            title="Build out your organisation"
            description="Create departments and teams, then add employees and invite them to WorkPulse."
            action={
              <div className="flex gap-2">
                <Button size="sm" variant="outline" asChild>
                  <Link to="/people/departments">Create departments</Link>
                </Button>
                <Button size="sm" asChild>
                  <Link to="/people/employees">Add employees</Link>
                </Button>
              </div>
            }
          />
        </Card>
      )}
    </div>
  )
}
