import { useMemo, useState } from 'react'
import { ArrowLeft, Building2, ChevronRight, Gauge, LayoutGrid, LineChart, ListFilter, MousePointerClick, Users } from 'lucide-react'
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { Link, Outlet, useParams, useSearchParams } from 'react-router'

import { FilterSelect, toOptions } from '@/components/common/filter-select'
import { LinkTabs } from '@/components/common/link-tabs'
import { PageHeader } from '@/components/common/page-header'
import { Person } from '@/components/common/person'
import { VirtualTableBody } from '@/components/common/virtual'
import { Button } from '@/components/ui/button'
import { Card, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/misc'
import { SegmentedControl } from '@/components/ui/segmented-control'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { formatDay, formatSeconds } from '@/features/activity/format'
import { RequirePermission } from '@/features/auth/guards'
import { ChartTooltipBox, WidgetError } from '@/features/dashboard/components/widget'
import { useDepartments, useEmployee, useEmployeeOptions, useTeams } from '@/features/people/api'
import { useProductivityGroups, useProductivityTrend, useTeamProductivity, type ScopeParams, type TrendPeriod } from '@/features/productivity/api'
import { CategoryBar } from '@/features/productivity/components/category-bar'
import { DataSheet, type DataTarget } from '@/features/productivity/components/data-sheet'
import { EmployeeProductivityView } from '@/features/productivity/components/employee-view'
import { ProductivityReport } from '@/features/productivity/components/report'
import { TrendPanels } from '@/features/productivity/components/trend-panels'
import { RANGES, rangeFor, type RangeKey } from '@/features/productivity/meta'
import { useDocumentTitle } from '@/hooks/use-document-title'
import { useAuthStore, usePermissions } from '@/stores/auth-store'
import type { ProductivityGroupRow } from '@/types/api'

const pct = (v: number | null) => (v === null ? '—' : `${v}%`)

export function ProductivityLayout() {
  const { can } = usePermissions()
  const viewer = can('ACTIVITY_VIEW')
  const tabs = [
    ...(viewer
      ? [
          { to: '/productivity', label: 'People', icon: LayoutGrid, end: true },
          { to: '/productivity/departments', label: 'Departments & teams', icon: Building2 },
          { to: '/productivity/trends', label: 'Trends', icon: LineChart },
        ]
      : []),
    ...(viewer || can('POLICY_MANAGE') ? [{ to: '/productivity/rules', label: 'Rules & work profiles', icon: ListFilter }] : []),
  ]
  return (
    <div className="space-y-6">
      <PageHeader
        title="Productivity"
        description="Several measured signals — time, applications, focus and tasks — each shown with how it is calculated."
        icon={Gauge}
      />
      <LinkTabs tabs={tabs} />
      <Outlet />
    </div>
  )
}

/** Department / team / everyone selector, kept in the URL so views can link to each other. */
function useScopeParams(): [ScopeParams, (next: ScopeParams) => void] {
  const [params, setParams] = useSearchParams()
  const scope: ScopeParams = {
    department_id: params.get('department') ?? undefined,
    team_id: params.get('team') ?? undefined,
    employee_id: params.get('person') ?? undefined,
  }
  const set = (next: ScopeParams) =>
    setParams(
      (current) => {
        const out = new URLSearchParams(current)
        for (const [key, value] of [
          ['department', next.department_id],
          ['team', next.team_id],
          ['person', next.employee_id],
        ] as const) {
          if (value) out.set(key, value)
          else out.delete(key)
        }
        return out
      },
      { replace: true },
    )
  return [scope, set]
}

function ScopeSelects({ scope, onChange, people = false }: { scope: ScopeParams; onChange: (s: ScopeParams) => void; people?: boolean }) {
  const departments = useDepartments()
  const teams = useTeams()
  const employees = useEmployeeOptions(people)
  const teamOptions = (teams.data ?? []).filter((t) => !scope.department_id || t.department?.id === scope.department_id)
  return (
    <>
      <FilterSelect
        label="Department"
        value={scope.department_id}
        onChange={(v) => onChange({ department_id: v ?? undefined })}
        options={toOptions(departments.data)}
        allLabel="All departments"
      />
      <FilterSelect
        label="Team"
        value={scope.team_id}
        onChange={(v) => onChange({ department_id: scope.department_id, team_id: v ?? undefined })}
        options={toOptions(teamOptions)}
        allLabel="All teams"
      />
      {people && (
        <FilterSelect
          label="Person"
          value={scope.employee_id}
          onChange={(v) => onChange({ ...scope, employee_id: v ?? undefined })}
          options={(employees.data ?? []).map((e) => ({ value: e.id, label: e.full_name }))}
          allLabel="Everyone in the selection"
          className="sm:w-52"
        />
      )}
    </>
  )
}

function scopeLabel(scope: ScopeParams, names: { departments?: { id: string; name: string }[]; teams?: { id: string; name: string }[] }) {
  const team = names.teams?.find((t) => t.id === scope.team_id)?.name
  const dept = names.departments?.find((d) => d.id === scope.department_id)?.name
  return team ?? dept ?? 'Everyone in your scope'
}

// --------------------------------------------------------------------------- people (team) view
export function ProductivityOverviewPage() {
  useDocumentTitle('Productivity')
  const timeZone = useAuthStore((s) => s.company?.timezone ?? 'UTC')
  const [range, setRange] = useState<RangeKey>('7d')
  const [scope, setScope] = useScopeParams()
  const departments = useDepartments()
  const teams = useTeams()
  const params = useMemo(
    () => ({ ...rangeFor(range, timeZone), team_id: scope.team_id, department_id: scope.department_id }),
    [range, timeZone, scope.team_id, scope.department_id],
  )
  const query = useTeamProductivity(params)
  const data = query.data
  const [target, setTarget] = useState<DataTarget | null>(null)
  const label = scopeLabel(scope, { departments: departments.data, teams: teams.data })

  return (
    <RequirePermission permission="ACTIVITY_VIEW">
      <div className="space-y-5">
        <div className="flex flex-wrap items-center gap-3">
          <SegmentedControl label="Period" value={range} onChange={setRange} options={RANGES} />
          <ScopeSelects scope={scope} onChange={setScope} />
          {data && (
            <p className="text-[12px] text-muted-foreground">
              {formatDay(data.start, 'short')} – {formatDay(data.end, 'short')} · totals for {data.rows.length}{' '}
              {data.rows.length === 1 ? 'person' : 'people'}
            </p>
          )}
        </div>

        {query.isError ? (
          <Card>
            <WidgetError error={query.error} onRetry={() => void query.refetch()} />
          </Card>
        ) : !data ? (
          <div className="space-y-4">
            <Skeleton className="h-24" />
            <Skeleton className="h-72" />
          </div>
        ) : (
          <div className={query.isFetching ? 'opacity-80 transition-opacity' : undefined}>
            <ProductivityReport data={data} onSelectDay={(day) => setTarget({ start: day, end: day, scope: { team_id: scope.team_id, department_id: scope.department_id }, label })}>
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <Users className="size-4 text-muted-foreground" aria-hidden /> People
                  </CardTitle>
                  <CardDescription>Not a ranking: sorted by name. Open a person for the figures behind their numbers.</CardDescription>
                </CardHeader>
                <div className="relative mt-3 overflow-x-auto border-t">
                  <Table aria-rowcount={data.rows.length + 1}>
                    <caption className="sr-only">Productivity figures per person</caption>
                    <TableHeader>
                      <TableRow className="hover:bg-transparent">
                        <TableHead className="pl-5">Person</TableHead>
                        <TableHead className="text-right">Work</TableHead>
                        <TableHead className="text-right">Active</TableHead>
                        <TableHead className="text-right">Ext. idle</TableHead>
                        <TableHead className="w-[22%] min-w-44">Time by category</TableHead>
                        <TableHead className="text-right">Activity</TableHead>
                        <TableHead className="text-right">Productive</TableHead>
                        <TableHead className="text-right">Focus</TableHead>
                        <TableHead className="text-right">Utilization</TableHead>
                        <TableHead className="pr-5" />
                      </TableRow>
                    </TableHeader>
                    <VirtualTableBody
                      count={data.rows.length}
                      estimateSize={57}
                      columns={10}
                      getKey={(i) => data.rows[i].employee.id}
                      renderRow={(i, rowProps) => {
                        const row = data.rows[i]
                        return (
                            <TableRow key={row.employee.id} {...rowProps}>
                              <TableCell className="max-w-56 pl-5">
                                <Person
                                  id={row.employee.id}
                                  name={row.employee.full_name}
                                  subtitle={[row.work_profile?.name, row.team?.name ?? row.employee.job_title].filter(Boolean).join(' · ') || undefined}
                                />
                              </TableCell>
                              <TableCell className="text-right tabular whitespace-nowrap">{formatSeconds(row.metrics.work_seconds)}</TableCell>
                              <TableCell className="text-right tabular whitespace-nowrap">{formatSeconds(row.metrics.active_seconds)}</TableCell>
                              <TableCell className="text-right tabular whitespace-nowrap">{formatSeconds(row.metrics.extended_idle_seconds)}</TableCell>
                              <TableCell>
                                <CategoryBar metrics={row.metrics} legend={false} />
                              </TableCell>
                              <TableCell className="text-right tabular whitespace-nowrap">{pct(row.activity_score)}</TableCell>
                              <TableCell className="text-right tabular whitespace-nowrap" title={row.productive_share === null ? 'Not enough classified activity' : undefined}>
                                {pct(row.productive_share)}
                              </TableCell>
                              <TableCell className="text-right tabular whitespace-nowrap">{pct(row.focus_score)}</TableCell>
                              <TableCell className="text-right tabular whitespace-nowrap">{pct(row.work_utilization)}</TableCell>
                              <TableCell className="pr-5 text-right">
                                <Link
                                  to={`/productivity/employees/${row.employee.id}`}
                                  className="inline-flex items-center gap-0.5 text-[12px] font-medium text-primary hover:underline"
                                  aria-label={`Details for ${row.employee.full_name}`}
                                >
                                  Details <ChevronRight className="size-3.5" />
                                </Link>
                              </TableCell>
                            </TableRow>
                        )
                      }}
                    />
                  </Table>
                </div>
              </Card>
            </ProductivityReport>
          </div>
        )}
        <DataSheet target={target} onClose={() => setTarget(null)} />
      </div>
    </RequirePermission>
  )
}

// --------------------------------------------------------------------------- departments & teams
function GroupTooltip({ active, payload }: { active?: boolean; payload?: { payload?: ProductivityGroupRow & { name: string } }[] }) {
  const row = payload?.[0]?.payload
  if (!active || !row) return null
  return (
    <ChartTooltipBox
      title={row.name}
      rows={[
        { label: 'Work time', value: formatSeconds(row.metrics.work_seconds) },
        { label: 'People with data', value: `${row.people_with_data} of ${row.people}` },
        { label: 'Click', value: 'see the data' },
      ]}
    />
  )
}

export function ProductivityGroupsPage() {
  useDocumentTitle('Productivity by department')
  const timeZone = useAuthStore((s) => s.company?.timezone ?? 'UTC')
  const [range, setRange] = useState<RangeKey>('7d')
  const [by, setBy] = useState<'department' | 'team'>('department')
  const dates = useMemo(() => rangeFor(range, timeZone), [range, timeZone])
  const query = useProductivityGroups(by, dates)
  const data = query.data
  const [target, setTarget] = useState<DataTarget | null>(null)
  const name = (row: ProductivityGroupRow) => row.group?.name ?? (by === 'department' ? 'No department' : 'No team')
  const open = (row: ProductivityGroupRow) => {
    // People without a department/team can't be selected as a group; their data is in the People view.
    if (!row.group) return
    setTarget({ ...dates, scope: by === 'department' ? { department_id: row.group.id } : { team_id: row.group.id }, label: row.group.name })
  }
  const chartRows = (data?.rows ?? []).map((r) => ({ ...r, name: name(r), hours: r.metrics.work_seconds / 3600 }))

  return (
    <RequirePermission permission="ACTIVITY_VIEW">
      <div className="space-y-5">
        <div className="flex flex-wrap items-center gap-3">
          <SegmentedControl label="Period" value={range} onChange={setRange} options={RANGES} />
          <SegmentedControl<'department' | 'team'>
            label="Group by"
            value={by}
            onChange={setBy}
            options={[
              { value: 'department', label: 'Departments' },
              { value: 'team', label: 'Teams' },
            ]}
          />
        </div>
        {query.isError ? (
          <Card>
            <WidgetError error={query.error} onRetry={() => void query.refetch()} />
          </Card>
        ) : !data ? (
          <Skeleton className="h-72" />
        ) : (
          <div className={query.isFetching ? 'space-y-5 opacity-80 transition-opacity' : 'space-y-5'}>
            <p className="rounded-lg border border-info/30 bg-info-soft/40 px-4 py-3 text-[13px]">{data.disclaimer}</p>
            <Card className="p-5">
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <h2 className="text-[13px] font-semibold">Work time by {by}</h2>
                <p className="flex items-center gap-1.5 text-[12px] text-muted-foreground">
                  <MousePointerClick className="size-3.5" aria-hidden /> Click a bar to see the data behind it
                </p>
              </div>
              <figure className="mt-3" style={{ height: Math.max(120, chartRows.length * 40 + 24) }}>
                <figcaption className="sr-only">Work hours per {by}, in alphabetical order. The table below lists every figure.</figcaption>
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart
                    data={chartRows}
                    layout="vertical"
                    margin={{ top: 0, right: 16, bottom: 0, left: 0 }}
                    barCategoryGap="30%"
                    onClick={(state) => {
                      const raw = (state as { activeTooltipIndex?: number | string } | null)?.activeTooltipIndex
                      const i = raw === undefined || raw === null ? NaN : Number(raw)
                      if (Number.isInteger(i) && data.rows[i]) open(data.rows[i])
                    }}
                    style={{ cursor: 'pointer' }}
                  >
                    <CartesianGrid horizontal={false} stroke="var(--chart-grid)" />
                    <XAxis type="number" tickFormatter={(v: number) => `${v}h`} tickLine={false} axisLine={false} allowDecimals={false} tick={{ fill: 'var(--muted-foreground)', fontSize: 11 }} />
                    <YAxis type="category" dataKey="name" width={140} tickLine={false} axisLine={false} tick={{ fill: 'var(--foreground)', fontSize: 12 }} />
                    <Tooltip cursor={{ fill: 'var(--muted)', opacity: 0.5 }} content={<GroupTooltip />} />
                    <Bar dataKey="hours" fill="var(--chart-1)" radius={[0, 4, 4, 0]} isAnimationActive={false} />
                  </BarChart>
                </ResponsiveContainer>
              </figure>
            </Card>
            <Card className="overflow-hidden py-0">
              <div className="relative overflow-x-auto">
                <Table>
                  <caption className="sr-only">Productivity figures per {by}</caption>
                  <TableHeader>
                    <TableRow className="hover:bg-transparent">
                      <TableHead className="pl-5">{by === 'department' ? 'Department' : 'Team'}</TableHead>
                      <TableHead className="text-right">People</TableHead>
                      <TableHead className="text-right">Work</TableHead>
                      <TableHead className="w-[20%] min-w-44">Time by category</TableHead>
                      <TableHead className="text-right">Activity</TableHead>
                      <TableHead className="text-right">Productive</TableHead>
                      <TableHead className="text-right">Focus</TableHead>
                      <TableHead className="text-right">Utilization</TableHead>
                      <TableHead className="text-right">Tasks done</TableHead>
                      <TableHead className="pr-5" />
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {data.rows.map((row) => (
                      <TableRow key={row.group?.id ?? 'none'}>
                        <TableCell className="pl-5 font-medium">
                          {row.group ? (
                            <Link to={`/productivity?${by === 'department' ? 'department' : 'team'}=${row.group.id}`} className="hover:underline">
                              {row.group.name}
                            </Link>
                          ) : (
                            <span className="text-muted-foreground">{name(row)}</span>
                          )}
                        </TableCell>
                        <TableCell className="text-right tabular whitespace-nowrap" title="People with recorded data / people in the group">
                          {row.people_with_data}/{row.people}
                        </TableCell>
                        <TableCell className="text-right tabular whitespace-nowrap">{formatSeconds(row.metrics.work_seconds)}</TableCell>
                        <TableCell>
                          <CategoryBar metrics={row.metrics} legend={false} />
                        </TableCell>
                        <TableCell className="text-right tabular whitespace-nowrap">{pct(row.scores.activity_score.value)}</TableCell>
                        <TableCell className="text-right tabular whitespace-nowrap">{pct(row.scores.productive_share.value)}</TableCell>
                        <TableCell className="text-right tabular whitespace-nowrap">{pct(row.scores.focus_score.value)}</TableCell>
                        <TableCell className="text-right tabular whitespace-nowrap">{pct(row.scores.work_utilization.value)}</TableCell>
                        <TableCell className="text-right tabular whitespace-nowrap">{pct(row.task_completion)}</TableCell>
                        <TableCell className="pr-5 text-right">
                          {row.group && (
                            <Button size="sm" variant="ghost" onClick={() => open(row)}>
                              View data
                            </Button>
                          )}
                        </TableCell>
                      </TableRow>
                    ))}
                    {data.rows.length === 0 && (
                      <TableRow>
                        <TableCell colSpan={10} className="py-10 text-center text-[13px] text-muted-foreground">
                          Nobody in your scope yet.
                        </TableCell>
                      </TableRow>
                    )}
                  </TableBody>
                </Table>
              </div>
            </Card>
            <p className="text-[12px] text-muted-foreground">
              Sorted by name. Groups differ in size and in the kind of work they do, so their figures describe them rather than rank them.
            </p>
          </div>
        )}
        <DataSheet target={target} onClose={() => setTarget(null)} />
      </div>
    </RequirePermission>
  )
}

// --------------------------------------------------------------------------- trends
export function ProductivityTrendsPage() {
  useDocumentTitle('Productivity trends')
  const [period, setPeriod] = useState<TrendPeriod>('daily')
  const [scope, setScope] = useScopeParams()
  const departments = useDepartments()
  const teams = useTeams()
  const people = useEmployeeOptions()
  const query = useProductivityTrend(period, scope)
  const [target, setTarget] = useState<DataTarget | null>(null)
  const label = scope.employee_id
    ? (people.data?.find((p) => p.id === scope.employee_id)?.full_name ?? 'Selected person')
    : scopeLabel(scope, { departments: departments.data, teams: teams.data })

  return (
    <RequirePermission permission="ACTIVITY_VIEW">
      <div className="space-y-5">
        <div className="flex flex-wrap items-center gap-3">
          <SegmentedControl<TrendPeriod>
            label="Period"
            value={period}
            onChange={setPeriod}
            options={[
              { value: 'daily', label: 'Last 14 days' },
              { value: 'weekly', label: '12 weeks' },
              { value: 'monthly', label: '12 months' },
            ]}
          />
          <ScopeSelects scope={scope} onChange={setScope} people />
          <p className="text-[12px] text-muted-foreground">{label}</p>
        </div>
        {query.isError ? (
          <Card>
            <WidgetError error={query.error} onRetry={() => void query.refetch()} />
          </Card>
        ) : !query.data ? (
          <Skeleton className="h-96" />
        ) : (
          <div className={query.isFetching ? 'opacity-80 transition-opacity' : undefined}>
            <TrendPanels
              trend={query.data}
              onSelect={(p) => setTarget({ start: p.start, end: p.end, scope: { team_id: scope.team_id, department_id: scope.department_id, employee_id: scope.employee_id }, label })}
            />
          </div>
        )}
        <DataSheet target={target} onClose={() => setTarget(null)} />
      </div>
    </RequirePermission>
  )
}

// --------------------------------------------------------------------------- one person
export function ProductivityEmployeePage() {
  const { employeeId = '' } = useParams()
  const employee = useEmployee(employeeId)
  useDocumentTitle(employee.data ? `Productivity · ${employee.data.full_name}` : 'Productivity')
  return (
    <div className="space-y-5">
      <Link to="/productivity" className="inline-flex items-center gap-1.5 text-[13px] text-muted-foreground hover:text-foreground">
        <ArrowLeft className="size-3.5" /> All people
      </Link>
      {employee.data && <Person id={employee.data.id} name={employee.data.full_name} subtitle={employee.data.job_title ?? undefined} />}
      <EmployeeProductivityView employeeId={employeeId} />
    </div>
  )
}
