import { type ReactNode, useMemo, useState } from 'react'
import { CalendarCheck, CalendarDays, Download, Settings2, Users } from 'lucide-react'
import { Link } from 'react-router'

import { EmptyState } from '@/components/common/empty-state'
import { FilterSelect, toOptions } from '@/components/common/filter-select'
import { PageHeader } from '@/components/common/page-header'
import { StatTile } from '@/components/common/stat-tile'
import { Button } from '@/components/ui/button'
import { Card, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/misc'
import { SegmentedControl } from '@/components/ui/segmented-control'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { formatClock, formatDay, formatSeconds, shiftDay, todayIn } from '@/features/activity/format'
import { useAttendanceReport } from '@/features/attendance/api'
import { AttendanceCalendar, Balance, DAY_STYLE, monthStart } from '@/features/attendance/attendance-calendar'
import { WidgetError } from '@/features/dashboard/components/widget'
import { useDepartments, useTeams } from '@/features/people/api'
import { EmployeePicker } from '@/features/people/components/employee-picker'
import { cn } from '@/lib/utils'
import { useAuthStore, usePermissions } from '@/stores/auth-store'
import type { AttendanceReportRow } from '@/types/api'

type View = 'organization' | 'individual'
type Preset = 'today' | 'week' | 'month' | 'last_month' | 'custom'

const PRESETS: { value: Preset; label: string }[] = [
  { value: 'today', label: 'Today' },
  { value: 'week', label: 'This week' },
  { value: 'month', label: 'This month' },
  { value: 'last_month', label: 'Last month' },
  { value: 'custom', label: 'Custom' },
]

/** Longest range the API accepts (92 days); custom ranges are clamped to it. */
const MAX_DAYS = 92

function presetRange(preset: Exclude<Preset, 'custom'>, today: string) {
  switch (preset) {
    case 'today':
      return { start: today, end: today }
    case 'week': {
      const weekday = (new Date(`${today}T00:00:00Z`).getUTCDay() + 6) % 7 // Monday = 0
      return { start: shiftDay(today, -weekday), end: today }
    }
    case 'month':
      return { start: monthStart(today), end: today }
    case 'last_month': {
      const last = shiftDay(monthStart(today), -1)
      return { start: monthStart(last), end: last }
    }
  }
}

function daysBetween(start: string, end: string) {
  return Math.round((Date.parse(`${end}T00:00:00Z`) - Date.parse(`${start}T00:00:00Z`)) / 86_400_000)
}

/** "7:50" style clock of a duration, for tables and CSV. */
function hm(seconds: number) {
  const minutes = Math.round(seconds / 60)
  return `${Math.floor(minutes / 60)}:${String(minutes % 60).padStart(2, '0')}`
}

function exportCsv(rows: AttendanceReportRow[], start: string, end: string, deptName: Map<string, string>, timeZone: string) {
  const cell = (v: string | number) => `"${String(v).replace(/"/g, '""')}"`
  let lines: string[]
  if (rows.length === 1) {
    // One person: a line per day with sign-in and sign-out.
    const r = rows[0]
    lines = [
      ['Name', 'Date', 'Status', 'In', 'Out', 'Active (logged)', 'Customer time (in logged)', 'Signed in', 'Idle', 'Expected'].map(cell).join(','),
      ...r.days
        .filter((d) => d.status !== 'upcoming')
        .map((d) =>
          [
            r.employee.full_name,
            d.day,
            DAY_STYLE[d.status].label,
            d.first_in ? formatClock(d.first_in, timeZone) : '',
            d.last_out ? formatClock(d.last_out, timeZone) : d.first_in ? 'Signed in' : '',
            hm(d.active_seconds),
            hm(d.customer_seconds),
            hm(d.work_seconds),
            hm(d.idle_seconds),
            hm(d.expected_seconds),
          ]
            .map(cell)
            .join(','),
        ),
    ]
  } else {
    lines = [
      ['Name', 'Email', 'Department', 'Logged (active)', 'Expected', 'Difference', 'Days completed', 'Working days', 'Holidays', 'Untracked days']
        .map(cell)
        .join(','),
      ...rows.map((r) =>
        [
          r.employee.full_name,
          r.employee.email ?? '',
          r.department_id ? (deptName.get(r.department_id) ?? '') : '',
          hm(r.logged_seconds),
          hm(r.expected_seconds),
          `${r.logged_seconds >= r.expected_seconds ? '+' : '-'}${hm(Math.abs(r.logged_seconds - r.expected_seconds))}`,
          r.days_met,
          r.working_days,
          r.holidays,
          r.untracked_days,
        ]
          .map(cell)
          .join(','),
      ),
    ]
  }
  const blob = new Blob([lines.join('\n')], { type: 'text/csv' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = rows.length === 1 ? `attendance-${rows[0].employee.full_name.replace(/\s+/g, '-')}-${start}_${end}.csv` : `attendance-${start}_${end}.csv`
  a.click()
  URL.revokeObjectURL(url)
}

// ----------------------------------------------------------------------------- page
function ToolbarField({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-1.5">
      <span className="text-[11px] font-medium tracking-wide text-muted-foreground uppercase">{label}</span>
      {children}
    </div>
  )
}

export default function AttendancePage() {
  const timeZone = useAuthStore((s) => s.company?.timezone ?? 'UTC')
  const company = useAuthStore((s) => s.company)
  const ownEmployeeId = useAuthStore((s) => s.user?.employee_id ?? null)
  const { can } = usePermissions()
  const watchesOthers = can('ACTIVITY_VIEW')
  const today = todayIn(timeZone)

  const [view, setView] = useState<View>(watchesOthers ? 'organization' : 'individual')
  const [preset, setPreset] = useState<Preset>('month')
  const [custom, setCustom] = useState(() => presetRange('month', today))
  const [teamId, setTeamId] = useState<string | null>(null)
  const [departmentId, setDepartmentId] = useState<string | null>(null)
  const [person, setPerson] = useState<string | null>(null)
  const [open, setOpen] = useState<string | null>(null)
  const teams = useTeams(can('EMPLOYEE_VIEW'))
  const departments = useDepartments(can('EMPLOYEE_VIEW'))
  const deptName = useMemo(() => new Map((departments.data ?? []).map((d) => [d.id, d.name])), [departments.data])

  const range = preset === 'custom' ? custom : presetRange(preset, today)
  const individualId = watchesOthers ? person : ownEmployeeId
  const params =
    view === 'individual'
      ? { start: range.start, end: range.end, employee_id: individualId ?? undefined }
      : // The organisation table shows only each person's totals, so the per-day detail isn't fetched.
        { start: range.start, end: range.end, team_id: teamId ?? undefined, department_id: departmentId ?? undefined, details: false }
  const query = useAttendanceReport(params, view === 'organization' || Boolean(individualId))
  const rows = useMemo(() => (view === 'individual' && !individualId ? [] : (query.data?.rows ?? [])), [query.data, view, individualId])
  const noRequirement = (company?.required_minutes ?? []).every((m) => !m)

  const totals = useMemo(() => {
    let met = 0
    let working = 0
    let untracked = 0
    let short = 0
    for (const r of rows) {
      met += r.days_met
      working += r.working_days
      untracked += r.untracked_days
      short += r.days_short
    }
    return { met, working, untracked, short }
  }, [rows])

  const setCustomPart = (part: 'start' | 'end', value: string) => {
    if (!value) return
    setCustom((c) => {
      const next = { ...c, [part]: value }
      if (next.end > today) next.end = today
      if (next.start > next.end) next[part === 'start' ? 'end' : 'start'] = value
      if (daysBetween(next.start, next.end) >= MAX_DAYS) {
        if (part === 'start') next.end = shiftDay(next.start, MAX_DAYS - 1)
        else next.start = shiftDay(next.end, -(MAX_DAYS - 1))
      }
      return next
    })
  }

  // Both views open the calendar only on request (row or calendar button), and it can be closed again.
  const openRow = rows.find((r) => r.employee.id === open)
  const period = range.start === range.end ? formatDay(range.start) : `${formatDay(range.start, 'short')} – ${formatDay(range.end, 'short')}`

  return (
    <div className="space-y-6">
      <PageHeader
        title="Attendance"
        description="Sign-in and sign-out per day, and active time against the required hours."
        icon={CalendarCheck}
      />

      {noRequirement && (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-warning/40 bg-warning-soft px-4 py-3 text-[13px]">
          <span>
            No required hours are set yet, so nobody can be marked short or complete. Set them per weekday under Settings →
            Workspace → Working days &amp; holidays.
          </span>
          {can('POLICY_MANAGE') && (
            <Button asChild size="sm" variant="outline">
              <Link to="/settings/workspace">
                <Settings2 /> Set required hours
              </Link>
            </Button>
          )}
        </div>
      )}

      {watchesOthers && (
        <SegmentedControl<View>
          label="View"
          value={view}
          onChange={(v) => {
            setView(v)
            setOpen(null)
          }}
          options={[
            { value: 'organization', label: 'Organization view' },
            { value: 'individual', label: 'Individual view' },
          ]}
        />
      )}

      {/* Filter toolbar: one row on wide screens, labelled fields that wrap cleanly on narrow ones. */}
      <Card className="p-4">
        <div className="flex flex-wrap items-end gap-x-4 gap-y-3">
          <ToolbarField label="Period">
            <SegmentedControl<Preset> label="Period" value={preset} onChange={setPreset} options={PRESETS} />
          </ToolbarField>
          <ToolbarField label="Dates">
            {preset === 'custom' ? (
              <div className="flex h-9 items-center rounded-md border border-input bg-card shadow-xs focus-within:border-ring focus-within:ring-[3px] focus-within:ring-ring/25">
                <CalendarDays className="ml-3 size-4 shrink-0 text-muted-foreground" aria-hidden />
                <input
                  type="date"
                  value={custom.start}
                  max={today}
                  onChange={(e) => setCustomPart('start', e.target.value)}
                  className="h-full w-[8.5rem] bg-transparent px-2 text-[13px] tabular outline-none"
                  aria-label="From"
                />
                <span className="text-[13px] text-muted-foreground">–</span>
                <input
                  type="date"
                  value={custom.end}
                  max={today}
                  onChange={(e) => setCustomPart('end', e.target.value)}
                  className="h-full w-[8.5rem] bg-transparent px-2 text-[13px] tabular outline-none"
                  aria-label="To"
                />
              </div>
            ) : (
              <div className="flex h-9 items-center gap-2 rounded-md border border-dashed px-3 text-[13px] text-muted-foreground tabular">
                <CalendarDays className="size-4 shrink-0" aria-hidden />
                {period}
              </div>
            )}
          </ToolbarField>
          {view === 'organization'
            ? can('EMPLOYEE_VIEW') && (
                <>
                  <ToolbarField label="Department">
                    <FilterSelect
                      label="Department"
                      value={departmentId}
                      onChange={setDepartmentId}
                      options={toOptions(departments.data)}
                      allLabel="All departments"
                      className="w-48"
                    />
                  </ToolbarField>
                  <ToolbarField label="Team">
                    <FilterSelect
                      label="Team"
                      value={teamId}
                      onChange={setTeamId}
                      options={toOptions(teams.data)}
                      allLabel="All teams"
                      className="w-44"
                    />
                  </ToolbarField>
                </>
              )
            : watchesOthers && (
                <ToolbarField label="Member">
                  <div className="w-64">
                    <EmployeePicker
                      value={person}
                      onChange={(id) => {
                        setPerson(id)
                        setOpen(null)
                      }}
                      placeholder="Select a member"
                    />
                  </div>
                </ToolbarField>
              )}
          <Button
            variant="outline"
            className="ml-auto"
            onClick={() => exportCsv(rows, range.start, range.end, deptName, timeZone)}
            disabled={!rows.length}
          >
            <Download /> Export CSV
          </Button>
        </div>
      </Card>

      {view === 'individual' && !individualId ? (
        <Card>
          <EmptyState
            icon={Users}
            title={watchesOthers ? 'Select a member' : 'No employee record'}
            description={
              watchesOthers
                ? 'Choose a person above to see their attendance and calendar.'
                : 'Your account is not linked to an employee record, so there is no attendance to show.'
            }
          />
        </Card>
      ) : query.isError ? (
        <Card>
          <WidgetError error={query.error} onRetry={() => void query.refetch()} />
        </Card>
      ) : !query.data ? (
        <div className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-4">
            {[0, 1, 2, 3].map((i) => (
              <Skeleton key={i} className="h-24" />
            ))}
          </div>
          <Skeleton className="h-80" />
        </div>
      ) : (
        <div className={cn('space-y-6', query.isPlaceholderData && 'opacity-80 transition-opacity')}>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <StatTile icon={Users} label={view === 'individual' ? 'Working days' : 'People'} value={String(view === 'individual' ? totals.working : rows.length)} hint={period} />
            <StatTile marker="bg-success" label="Days completed" value={String(totals.met)} hint={`of ${totals.working} working days`} />
            <StatTile marker="bg-destructive" label="Short days" value={String(totals.short)} hint="Worked, but under the required hours" />
            <StatTile marker="bg-muted-foreground" label="Untracked days" value={String(totals.untracked)} hint="Working days with no work session" />
          </div>

          <div className={cn('grid gap-6', openRow && 'xl:grid-cols-[minmax(0,1fr)_minmax(0,27rem)]')}>
            <Card className="min-w-0 overflow-hidden">
              <CardHeader>
                <CardTitle>{view === 'individual' ? 'Attendance' : 'Attendance by person'}</CardTitle>
                <CardDescription>
                  {period} · Logged = active time (keyboard or mouse input) plus idle time with a customer system in
                  front, compared with the required hours of each working day up to today.
                </CardDescription>
              </CardHeader>
              {rows.length === 0 ? (
                <EmptyState size="sm" icon={Users} title="No active employees" description="Nobody matches these filters." />
              ) : (
                <div className="mt-3 border-t [&_[data-slot=table-container]]:max-h-[36rem] [&_[data-slot=table-container]]:overflow-y-auto [&_[data-slot=table-container]]:[scrollbar-width:thin]">
                  <Table>
                    <caption className="sr-only">Attendance by person, {period}</caption>
                    <TableHeader className="sticky top-0 z-10 shadow-[inset_0_-1px_0_var(--color-border)]">
                      <TableRow className="hover:bg-transparent">
                        <TableHead className="pl-5">Name</TableHead>
                        <TableHead className="text-right">Logged</TableHead>
                        <TableHead className="text-right">Expected</TableHead>
                        <TableHead>Status</TableHead>
                        <TableHead className="hidden text-right lg:table-cell">Completed</TableHead>
                        <TableHead className="hidden text-right md:table-cell">Holidays</TableHead>
                        <TableHead className="hidden text-right md:table-cell">Untracked</TableHead>
                        <TableHead className="pr-5 text-right">Calendar</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {rows.map((r) => {
                        const active = openRow?.employee.id === r.employee.id
                        return (
                          <TableRow
                            key={r.employee.id}
                            className={cn('cursor-pointer', active && 'bg-primary-soft/40 hover:bg-primary-soft/50')}
                            onClick={() => setOpen(active ? null : r.employee.id)}
                          >
                            <TableCell className="w-full max-w-0 pl-5">
                              <span className="block truncate font-medium">{r.employee.full_name}</span>
                              <span className="block truncate text-[12px] text-muted-foreground">
                                {[r.employee.job_title, r.department_id ? deptName.get(r.department_id) : null].filter(Boolean).join(' · ') ||
                                  r.employee.email}
                              </span>
                            </TableCell>
                            <TableCell className="text-right font-medium whitespace-nowrap tabular">{formatSeconds(r.logged_seconds)}</TableCell>
                            <TableCell className="text-right whitespace-nowrap text-muted-foreground tabular">
                              {r.expected_seconds ? formatSeconds(r.expected_seconds) : '—'}
                            </TableCell>
                            <TableCell>
                              <Balance logged={r.logged_seconds} expected={r.expected_seconds} compact />
                            </TableCell>
                            <TableCell className="hidden text-right whitespace-nowrap tabular lg:table-cell">
                              {r.days_met}/{r.working_days}
                            </TableCell>
                            <TableCell className="hidden text-right tabular md:table-cell">{r.holidays}</TableCell>
                            <TableCell className={cn('hidden text-right tabular md:table-cell', r.untracked_days > 0 && 'font-medium text-destructive')}>
                              {r.untracked_days}
                            </TableCell>
                            <TableCell className="pr-5 text-right">
                              <Button
                                variant={active ? 'default' : 'outline'}
                                size="icon"
                                className="size-8"
                                onClick={(e) => {
                                  e.stopPropagation()
                                  setOpen(active ? null : r.employee.id)
                                }}
                                aria-label={`Calendar for ${r.employee.full_name}`}
                                aria-pressed={active}
                              >
                                <CalendarDays className="size-4" />
                              </Button>
                            </TableCell>
                          </TableRow>
                        )
                      })}
                    </TableBody>
                  </Table>
                </div>
              )}
            </Card>
            {openRow && (
              <AttendanceCalendar
                key={openRow.employee.id}
                employeeId={openRow.employee.id}
                name={openRow.employee.full_name}
                initialDay={range.end}
                today={today}
                timeZone={timeZone}
                onClose={() => setOpen(null)}
              />
            )}
          </div>
        </div>
      )}
    </div>
  )
}
