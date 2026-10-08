import { useState, type ReactNode } from 'react'
import { Activity, AppWindow, CalendarCheck, Camera, CheckCircle2, Clock, Download, Eye, FileChartColumn, FileSpreadsheet, FileText, FolderKanban, Gauge, Globe, ListChecks, Lock, MonitorPlay, ShieldCheck, Trash2, TriangleAlert, type LucideIcon } from 'lucide-react'
import { toast } from 'sonner'

import { ConfirmDialog } from '@/components/common/confirm-dialog'
import { EmptyState } from '@/components/common/empty-state'
import { FilterSelect, toOptions } from '@/components/common/filter-select'
import { PageHeader } from '@/components/common/page-header'
import { Button } from '@/components/ui/button'
import { Card, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Progress, Skeleton, Spinner } from '@/components/ui/misc'
import { SegmentedControl } from '@/components/ui/segmented-control'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { formatDay, shiftDay, todayIn } from '@/features/activity/format'
import { RequirePermission } from '@/features/auth/guards'
import { WidgetError } from '@/features/dashboard/components/widget'
import { useDepartments, useEmployeeOptions, useTeams } from '@/features/people/api'
import { useWorkProfiles } from '@/features/productivity/api'
import { isActive, useDeleteReport, usePreviewReport, useReportJobs, useReportTypes, useRequestReport } from '@/features/reports/api'
import { formatBytes } from '@/features/screenshots/format'
import { useProjects } from '@/features/work/api'
import { AssigneePicker } from '@/features/work/components/assignee-picker'
import { useDocumentTitle } from '@/hooks/use-document-title'
import { errorMessage } from '@/lib/api-client'
import { formatRelative, ROLE_LABELS } from '@/lib/format'
import { cn } from '@/lib/utils'
import { useAuthStore, usePermissions } from '@/stores/auth-store'
import type { EmployeeRef, ReportFiltersInput, ReportFormat, ReportJob, ReportPeriod, ReportRequestInput, ReportType, Role } from '@/types/api'

const ICON: Record<ReportType, LucideIcon> = {
  attendance: CalendarCheck,
  work_hours: Clock,
  activity: Activity,
  applications: AppWindow,
  websites: Globe,
  screenshots: Camera,
  projects: FolderKanban,
  tasks: ListChecks,
  productivity: Gauge,
  live_sessions: MonitorPlay,
}

const FORMAT: Record<ReportFormat, { label: string; icon: LucideIcon; hint: string }> = {
  csv: { label: 'CSV', icon: FileText, hint: 'Plain data for any tool' },
  xlsx: { label: 'Excel', icon: FileSpreadsheet, hint: 'Filterable sheet + an "About" tab' },
  pdf: { label: 'PDF', icon: FileChartColumn, hint: 'For sharing and printing' },
}

const PERMISSION_LABEL: Record<string, string> = {
  ACTIVITY_VIEW: 'View activity',
  SCREENSHOT_VIEW: 'View screenshots',
  LIVE_STREAM_VIEW: 'View live screens',
}

const PREVIEW_MAX_DAYS = 31
const ROLES: Role[] = ['EMPLOYEE', 'TEAM_LEAD', 'MANAGER', 'COMPANY_ADMIN']

/** Turn the period choice into an inclusive date range. Weeks start on Monday. */
function rangeOf(period: ReportPeriod, day: string, month: string, custom: { start: string; end: string }): { start: string; end: string } {
  if (period === 'daily') return { start: day, end: day }
  if (period === 'weekly') {
    const weekday = (new Date(`${day}T00:00:00Z`).getUTCDay() + 6) % 7
    const start = shiftDay(day, -weekday)
    return { start, end: shiftDay(start, 6) }
  }
  if (period === 'monthly') {
    const [y, m] = month.split('-').map(Number)
    const last = new Date(Date.UTC(y, m, 0)).getUTCDate()
    return { start: `${month}-01`, end: `${month}-${String(last).padStart(2, '0')}` }
  }
  return custom
}

const days = (r: { start: string; end: string }) => Math.round((Date.parse(r.end) - Date.parse(r.start)) / 86_400_000) + 1

function Step({ n, title, children }: { n: number; title: string; children: ReactNode }) {
  return (
    <section className="space-y-3">
      <h3 className="flex items-center gap-2 text-[13px] font-semibold">
        <span className="flex size-5 items-center justify-center rounded-full bg-primary-soft text-[11px] text-primary-soft-foreground tabular">{n}</span>
        {title}
      </h3>
      {children}
    </section>
  )
}

/** A labelled filter field in the report form (the shared FilterSelect with a visible label). */
function LabelledFilter({ id, label, value, onChange, options, all }: { id: string; label: string; value: string | null; onChange: (v: string | null) => void; options: { id: string; name: string }[]; all: string }) {
  return (
    <div className="space-y-1.5">
      <Label htmlFor={id}>{label}</Label>
      <FilterSelect id={id} label={label} value={value} onChange={onChange} options={toOptions(options)} allLabel={all} className="sm:w-full" />
    </div>
  )
}

const STAGE: Record<ReportJob['status'], { label: string; tone: string }> = {
  queued: { label: 'Preparing report…', tone: 'text-muted-foreground' },
  preparing: { label: 'Preparing report…', tone: 'text-muted-foreground' },
  generating: { label: 'Generating…', tone: 'text-info' },
  ready: { label: 'Ready for download', tone: 'text-success' },
  failed: { label: 'Failed', tone: 'text-destructive' },
  expired: { label: 'Expired', tone: 'text-muted-foreground' },
}

function JobRow({ job, onDelete }: { job: ReportJob; onDelete: (job: ReportJob) => void }) {
  const stage = STAGE[job.status]
  const active = isActive(job)
  const Icon = ICON[job.report_type]
  return (
    <li className="space-y-2 px-5 py-3.5">
      <div className="flex items-start gap-3">
        <Icon className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden />
        <div className="min-w-0 flex-1">
          <p className="text-[13px] font-medium">
            {job.label} <span className="rounded bg-muted px-1.5 py-0.5 text-[10px] font-semibold tracking-wide text-muted-foreground uppercase">{FORMAT[job.format].label}</span>
          </p>
          <p className="text-[12px] text-muted-foreground">
            {job.start === job.end ? formatDay(job.start, 'short') : `${formatDay(job.start, 'short')} – ${formatDay(job.end, 'short')}`} · requested{' '}
            {formatRelative(job.created_at)}
          </p>
        </div>
        {job.status === 'ready' && job.download_url ? (
          <Button asChild size="sm" variant="outline">
            <a href={job.download_url} download={job.filename ?? undefined}>
              <Download /> Download
            </a>
          </Button>
        ) : null}
        {!active && (
          <Button size="icon-sm" variant="ghost" aria-label={`Delete ${job.label} report`} onClick={() => onDelete(job)}>
            <Trash2 />
          </Button>
        )}
      </div>
      <div className="pl-7">
        <p className={cn('flex items-center gap-1.5 text-[12px] font-medium', stage.tone)} aria-live="polite">
          {active ? (
            <Spinner className="size-3.5" />
          ) : job.status === 'ready' ? (
            <CheckCircle2 className="size-3.5" aria-hidden />
          ) : job.status === 'failed' ? (
            <TriangleAlert className="size-3.5" aria-hidden />
          ) : null}
          {stage.label}
          {job.status === 'ready' && (
            <span className="font-normal text-muted-foreground">
              · {job.row_count?.toLocaleString()} rows · {formatBytes(job.size_bytes ?? 0)}
              {job.expires_at && ` · deleted ${formatRelative(job.expires_at)}`}
            </span>
          )}
        </p>
        {active && <Progress value={job.progress} className="mt-1.5 h-1" aria-label="Export progress" />}
        {job.status === 'failed' && job.error && <p className="mt-1 text-[12px] text-muted-foreground">{job.error}</p>}
        {job.status === 'ready' && job.notes.length > 0 && (
          <details className="mt-1 text-[12px] text-muted-foreground">
            <summary className="cursor-pointer">Notes ({job.notes.length})</summary>
            <ul className="mt-1 list-disc space-y-0.5 pl-4">
              {job.notes.map((n) => (
                <li key={n}>{n}</li>
              ))}
            </ul>
          </details>
        )}
      </div>
    </li>
  )
}

function ReportHistory() {
  const jobs = useReportJobs()
  const remove = useDeleteReport()
  const [deleting, setDeleting] = useState<ReportJob | null>(null)
  return (
    <Card className="overflow-hidden">
      <CardHeader>
        <CardTitle>Your reports</CardTitle>
        <CardDescription>Only you can download them. Files are encrypted and deleted automatically; every download is logged.</CardDescription>
      </CardHeader>
      <div className="mt-3 border-t">
        {jobs.isError ? (
          <WidgetError error={jobs.error} onRetry={() => void jobs.refetch()} />
        ) : !jobs.data ? (
          <div className="p-5">
            <Skeleton className="h-24" />
          </div>
        ) : jobs.data.length === 0 ? (
          <EmptyState size="sm" icon={FileChartColumn} title="No reports yet" description="Generated reports appear here, with their progress." />
        ) : (
          <ul aria-label="Your reports" className="max-h-[640px] divide-y overflow-y-auto">
            {jobs.data.map((job) => (
              <JobRow key={job.id} job={job} onDelete={setDeleting} />
            ))}
          </ul>
        )}
      </div>
      <ConfirmDialog
        open={deleting !== null}
        onOpenChange={(open) => !open && setDeleting(null)}
        title="Delete this report?"
        description="The file is removed. You can generate it again at any time."
        confirmLabel="Delete report"
        destructive
        loading={remove.isPending}
        onConfirm={() => deleting && remove.mutate(deleting.id, { onSuccess: () => setDeleting(null), onError: (e) => toast.error(errorMessage(e)) })}
      />
    </Card>
  )
}

function ReportBuilder() {
  const timeZone = useAuthStore((s) => s.company?.timezone ?? 'UTC')
  const { can } = usePermissions()
  const canExport = can('REPORT_EXPORT')
  const today = todayIn(timeZone)
  const types = useReportTypes()
  const departments = useDepartments()
  const teams = useTeams()
  const profiles = useWorkProfiles()
  const projects = useProjects()
  const people = useEmployeeOptions()
  const preview = usePreviewReport()
  const request = useRequestReport()

  const [type, setType] = useState<ReportType>('attendance')
  const [period, setPeriod] = useState<ReportPeriod>('weekly')
  const [day, setDay] = useState(shiftDay(today, -1))
  const [month, setMonth] = useState(today.slice(0, 7))
  const [custom, setCustom] = useState({ start: shiftDay(today, -29), end: today })
  const [filters, setFilters] = useState<ReportFiltersInput>({})
  const [format, setFormat] = useState<ReportFormat>('xlsx')

  const info = types.data?.find((t) => t.key === type)
  const range = rangeOf(period, day, month, custom)
  const span = days(range)
  const validRange = span >= 1 && range.end >= range.start
  const relevant = new Set<string>(info?.filters ?? [])
  // Only the filters that apply to the chosen report are sent.
  const input: ReportRequestInput = {
    report_type: type,
    format,
    period,
    ...range,
    filters: Object.fromEntries(
      Object.entries(filters).filter(([k, v]) => relevant.has(filterKey(k)) && v !== null && v !== undefined && (!Array.isArray(v) || v.length)),
    ) as ReportFiltersInput,
  }
  const everyone: EmployeeRef[] = (people.data ?? []).map((p) => ({ id: p.id, full_name: p.full_name, email: '', job_title: p.job_title ?? null, status: 'active' }))
  const set = (patch: ReportFiltersInput) => setFilters((f) => ({ ...f, ...patch }))

  const generate = () =>
    request.mutate(input, {
      onSuccess: () => toast.success('Preparing report… it will appear under Your reports when ready.'),
      onError: (e) => toast.error(errorMessage(e)),
    })

  return (
    <Card>
      <CardHeader>
        <CardTitle>New report</CardTitle>
        <CardDescription>Reports only include people and projects you are allowed to see.</CardDescription>
      </CardHeader>
      <div className="space-y-6 px-5 pt-4 pb-5">
        <Step n={1} title="Report">
          {!types.data ? (
            <Skeleton className="h-40" />
          ) : (
            <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-5">
              {types.data.map((t) => {
                const Icon = ICON[t.key]
                return (
                  <button
                    key={t.key}
                    type="button"
                    aria-pressed={type === t.key}
                    disabled={!t.allowed}
                    title={t.allowed ? t.description : `Needs the ${PERMISSION_LABEL[t.requires ?? ''] ?? t.requires} permission`}
                    onClick={() => {
                      setType(t.key)
                      preview.reset()
                    }}
                    className={cn(
                      'flex flex-col gap-1 rounded-lg border p-3 text-left transition',
                      t.allowed ? 'hover:border-primary/50' : 'cursor-not-allowed opacity-50',
                      type === t.key && 'border-primary bg-primary-soft/40 ring-1 ring-primary',
                    )}
                  >
                    <span className="flex items-center gap-2 text-[13px] font-medium">
                      {t.allowed ? <Icon className="size-4 text-muted-foreground" aria-hidden /> : <Lock className="size-4 text-muted-foreground" aria-hidden />}
                      {t.label}
                    </span>
                    <span className="line-clamp-2 text-[11px] text-muted-foreground">{t.allowed ? t.description : `Needs ${PERMISSION_LABEL[t.requires ?? ''] ?? t.requires}`}</span>
                  </button>
                )
              })}
            </div>
          )}
        </Step>

        <Step n={2} title="Period">
          <div className="flex flex-wrap items-end gap-3">
            <SegmentedControl<ReportPeriod>
              label="Period"
              value={period}
              onChange={setPeriod}
              options={[
                { value: 'daily', label: 'Daily' },
                { value: 'weekly', label: 'Weekly' },
                { value: 'monthly', label: 'Monthly' },
                { value: 'custom', label: 'Custom range' },
              ]}
            />
            {(period === 'daily' || period === 'weekly') && (
              <div className="space-y-1.5">
                <Label htmlFor="report-day">{period === 'daily' ? 'Day' : 'Any day in the week'}</Label>
                <Input id="report-day" type="date" value={day} max={today} onChange={(e) => e.target.value && setDay(e.target.value)} className="h-8 w-40" />
              </div>
            )}
            {period === 'monthly' && (
              <div className="space-y-1.5">
                <Label htmlFor="report-month">Month</Label>
                <Input id="report-month" type="month" value={month} max={today.slice(0, 7)} onChange={(e) => e.target.value && setMonth(e.target.value)} className="h-8 w-40" />
              </div>
            )}
            {period === 'custom' && (
              <>
                <div className="space-y-1.5">
                  <Label htmlFor="report-start">From</Label>
                  <Input id="report-start" type="date" value={custom.start} max={custom.end} onChange={(e) => e.target.value && setCustom((c) => ({ ...c, start: e.target.value }))} className="h-8 w-40" />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="report-end">To</Label>
                  <Input id="report-end" type="date" value={custom.end} min={custom.start} onChange={(e) => e.target.value && setCustom((c) => ({ ...c, end: e.target.value }))} className="h-8 w-40" />
                </div>
              </>
            )}
            <p className="pb-1.5 text-[12px] text-muted-foreground tabular">
              {validRange ? `${formatDay(range.start, 'short')} – ${formatDay(range.end, 'short')} · ${span} day${span === 1 ? '' : 's'}` : 'Choose a valid range'}
            </p>
          </div>
        </Step>

        <Step n={3} title="Filters">
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
            {relevant.has('employee') && (
              <div className="space-y-1.5 sm:col-span-2 xl:col-span-3">
                <Label>People</Label>
                <AssigneePicker members={everyone} value={filters.employee_ids ?? []} onChange={(ids) => set({ employee_ids: ids })} label="People in the report" placeholder="Everyone (choose people…)" />
                <p className="text-[11px] text-muted-foreground">Leave empty for everyone you can see.</p>
              </div>
            )}
            {relevant.has('department') && (
              <LabelledFilter id="f-dept" label="Department" all="All departments" value={filters.department_id ?? null} onChange={(v) => set({ department_id: v })} options={departments.data ?? []} />
            )}
            {relevant.has('team') && <LabelledFilter id="f-team" label="Team" all="All teams" value={filters.team_id ?? null} onChange={(v) => set({ team_id: v })} options={teams.data ?? []} />}
            {relevant.has('role') && (
              <LabelledFilter
                id="f-role"
                label="Role"
                all="Any role"
                value={filters.role ?? null}
                onChange={(v) => set({ role: v as Role | null })}
                options={ROLES.map((r) => ({ id: r, name: ROLE_LABELS[r] }))}
              />
            )}
            {relevant.has('work_profile') && (profiles.data?.length ?? 0) > 0 && (
              <LabelledFilter
                id="f-profile"
                label="Job role (work profile)"
                all="Any job role"
                value={filters.work_profile_id ?? null}
                onChange={(v) => set({ work_profile_id: v })}
                options={profiles.data ?? []}
              />
            )}
            {relevant.has('project') && (
              <LabelledFilter id="f-project" label="Project" all="All projects" value={filters.project_id ?? null} onChange={(v) => set({ project_id: v })} options={projects.data ?? []} />
            )}
          </div>
        </Step>

        <Step n={4} title="Format">
          <div className="grid gap-2 sm:grid-cols-3">
            {(Object.keys(FORMAT) as ReportFormat[]).map((f) => {
              const meta = FORMAT[f]
              return (
                <button
                  key={f}
                  type="button"
                  aria-pressed={format === f}
                  aria-labelledby={`format-${f} format-${f}-hint`}
                  onClick={() => setFormat(f)}
                  className={cn('flex items-center gap-3 rounded-lg border p-3 text-left transition hover:border-primary/50', format === f && 'border-primary bg-primary-soft/40 ring-1 ring-primary')}
                >
                  <meta.icon className="size-5 text-muted-foreground" aria-hidden />
                  <span>
                    <span id={`format-${f}`} className="block text-[13px] font-medium">
                      {meta.label}
                    </span>{' '}
                    <span id={`format-${f}-hint`} className="block text-[11px] text-muted-foreground">
                      {meta.hint}
                    </span>
                  </span>
                </button>
              )
            })}
          </div>
        </Step>

        <div className="flex flex-wrap items-center gap-3 border-t pt-4">
          <Button
            variant="outline"
            onClick={() => preview.mutate(input, { onError: (e) => toast.error(errorMessage(e)) })}
            loading={preview.isPending}
            disabled={!info?.allowed || !validRange || span > PREVIEW_MAX_DAYS}
            title={span > PREVIEW_MAX_DAYS ? `Preview covers up to ${PREVIEW_MAX_DAYS} days` : undefined}
          >
            <Eye /> Preview
          </Button>
          <Button onClick={generate} loading={request.isPending} disabled={!info?.allowed || !validRange || !canExport}>
            <Download /> Generate {FORMAT[format].label}
          </Button>
          <p className="flex items-center gap-1.5 text-[12px] text-muted-foreground">
            <ShieldCheck className="size-3.5" aria-hidden />
            {canExport ? 'Generated in the background; you can leave this page.' : 'You can preview reports. Exporting files needs the Export reports permission.'}
          </p>
        </div>

        {preview.data && <PreviewTable data={preview.data} />}
      </div>
    </Card>
  )
}

function filterKey(field: string): string {
  return { employee_ids: 'employee', department_id: 'department', team_id: 'team', role: 'role', work_profile_id: 'work_profile', project_id: 'project' }[field] ?? field
}

function PreviewTable({ data }: { data: NonNullable<ReturnType<typeof usePreviewReport>['data']> }) {
  const numeric = new Set(['int', 'duration', 'percent'])
  return (
    <section className="space-y-2" aria-label="Preview">
      <p className="text-[13px] font-semibold">
        Preview · {data.title}{' '}
        <span className="font-normal text-muted-foreground">
          · showing {data.rows.length.toLocaleString()} of {data.total_rows.toLocaleString()} rows · {data.people} {data.people === 1 ? 'person' : 'people'} in scope
        </span>
      </p>
      {data.notes.length > 0 && (
        <ul className="list-disc space-y-0.5 pl-4 text-[12px] text-muted-foreground">
          {data.notes.map((n) => (
            <li key={n}>{n}</li>
          ))}
        </ul>
      )}
      <div className="relative max-h-[420px] overflow-auto rounded-lg border">
        <Table>
          <caption className="sr-only">Report preview</caption>
          <TableHeader className="sticky top-0 z-10">
            <TableRow className="hover:bg-transparent">
              {data.columns.map((c) => (
                <TableHead key={c.key} className={cn('whitespace-nowrap', numeric.has(c.kind) && 'text-right')}>
                  {c.label}
                </TableHead>
              ))}
            </TableRow>
          </TableHeader>
          <TableBody>
            {data.rows.map((row, i) => (
              <TableRow key={i}>
                {data.columns.map((c) => (
                  <TableCell key={c.key} className={cn('max-w-64 truncate whitespace-nowrap', numeric.has(c.kind) && 'text-right tabular')} title={row[c.key]}>
                    {row[c.key]}
                  </TableCell>
                ))}
              </TableRow>
            ))}
            {data.rows.length === 0 && (
              <TableRow>
                <TableCell colSpan={data.columns.length} className="py-8 text-center text-muted-foreground">
                  No rows for this selection.
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>
    </section>
  )
}

export default function ReportsPage() {
  useDocumentTitle('Reports')
  return (
    <div className="space-y-6">
      <PageHeader title="Reports" description="Attendance, time, activity, projects, productivity and access logs — as CSV, Excel or PDF." icon={FileChartColumn} />
      <RequirePermission permission="REPORT_VIEW">
        <div className="grid grid-cols-1 gap-6 2xl:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
          <ReportBuilder />
          <ReportHistory />
        </div>
      </RequirePermission>
    </div>
  )
}
