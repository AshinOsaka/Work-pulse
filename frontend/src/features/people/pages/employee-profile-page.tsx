import { useState, type ReactNode } from 'react'
import {
  Activity,
  ArrowLeft,
  CalendarClock,
  Camera,
  ChevronDown,
  Clock,
  Gauge,
  KeyRound,
  Laptop,
  ListChecks,
  Mail,
  MapPin,
  Pencil,
  UserRound,
  UserX,
} from 'lucide-react'
import { Link, useParams, useSearchParams } from 'react-router'
import { toast } from 'sonner'

import { ConfirmDialog } from '@/components/common/confirm-dialog'
import { EmptyState } from '@/components/common/empty-state'
import { Person, PersonAvatar } from '@/components/common/person'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Skeleton } from '@/components/ui/misc'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { EmployeeActivityPanel } from '@/features/activity/components/employee-activity-panel'
import { useChangeEmployeeStatus, useEmployee, useInviteEmployee } from '@/features/people/api'
import { AccessBadge, EmployeeStatusBadge } from '@/features/people/components/badges'
import { DevicesPanel } from '@/features/people/components/devices-panel'
import { EmployeeFormDialog } from '@/features/people/components/employee-form-dialog'
import { PermissionsPanel } from '@/features/people/components/permissions-panel'
import { UpcomingPanel } from '@/features/people/components/upcoming-panel'
import { EMPLOYMENT_TYPES } from '@/features/people/meta'
import { EmployeeProductivityView } from '@/features/productivity/components/employee-view'
import { EmployeeScreenshotsPanel } from '@/features/screenshots/components/employee-screenshots-panel'
import { EmployeeTasksPanel } from '@/features/work/components/employee-tasks-panel'
import { useDocumentTitle } from '@/hooks/use-document-title'
import { ApiError, errorMessage } from '@/lib/api-client'
import { formatDate } from '@/lib/format'
import { usePermissions, useAuthStore } from '@/stores/auth-store'
import type { EmployeeDetail, EmployeeStatus } from '@/types/api'

function Detail({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="grid grid-cols-[130px_minmax(0,1fr)] gap-3 py-2.5 text-[13px]">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="min-w-0 break-words">{children ?? <span className="text-muted-foreground">—</span>}</dd>
    </div>
  )
}

function OverviewTab({ employee }: { employee: EmployeeDetail }) {
  return (
    <div className="grid grid-cols-[minmax(0,1fr)] gap-6 lg:grid-cols-[minmax(0,1fr)_340px]">
      <Card>
        <CardHeader>
          <CardTitle>Employment details</CardTitle>
        </CardHeader>
        <CardContent className="pt-2">
          <dl className="divide-y">
            <Detail label="Email">{employee.email}</Detail>
            <Detail label="Employee ID">{employee.employee_code}</Detail>
            <Detail label="Job title">{employee.job_title}</Detail>
            <Detail label="Employment">{EMPLOYMENT_TYPES[employee.employment_type]}</Detail>
            <Detail label="Department">{employee.department?.name}</Detail>
            <Detail label="Team">{employee.team?.name}</Detail>
            <Detail label="Location">{employee.location}</Detail>
            <Detail label="Timezone">{employee.timezone.replaceAll('_', ' ')}</Detail>
            <Detail label="Hire date">{employee.hired_on ? formatDate(employee.hired_on) : null}</Detail>
            {employee.terminated_at && <Detail label="Terminated">{formatDate(employee.terminated_at)}</Detail>}
          </dl>
        </CardContent>
      </Card>
      <div className="space-y-6">
        <Card>
          <CardHeader>
            <CardTitle>Reports to</CardTitle>
          </CardHeader>
          <CardContent className="pt-3">
            {employee.manager ? (
              <Person id={employee.manager.id} name={employee.manager.full_name} subtitle={employee.manager.job_title} />
            ) : (
              <p className="text-[13px] text-muted-foreground">No manager assigned.</p>
            )}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Direct reports</CardTitle>
            <CardDescription>
              {employee.direct_reports.length} {employee.direct_reports.length === 1 ? 'person' : 'people'}
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3 pt-3">
            {employee.direct_reports.length === 0 ? (
              <p className="text-[13px] text-muted-foreground">Nobody reports to {employee.full_name.split(' ')[0]}.</p>
            ) : (
              employee.direct_reports.map((r) => <Person key={r.id} id={r.id} name={r.full_name} subtitle={r.job_title} />)
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  )
}

const UPCOMING = {
  attendance: {
    icon: Clock,
    title: 'Attendance',
    phase: 10,
    description: 'Clock-ins, shifts, breaks and timesheets will appear here, generated automatically from agent activity.',
    bullets: ['Daily attendance timeline', 'Shift and overtime tracking', 'Timesheet approvals'],
  },
} as const

const TAB_ICONS = { overview: UserRound, activity: Activity, productivity: Gauge, tasks: ListChecks, screenshots: Camera, devices: Laptop, permissions: KeyRound, ...Object.fromEntries(Object.entries(UPCOMING).map(([k, v]) => [k, v.icon])) }

function ProfileActions({ employee }: { employee: EmployeeDetail }) {
  const { can } = usePermissions()
  const isSelf = useAuthStore((s) => s.user?.id === employee.account?.user_id)
  const changeStatus = useChangeEmployeeStatus(employee.id)
  const invite = useInviteEmployee(employee.id)
  const [editOpen, setEditOpen] = useState(false)
  const [confirmTerminate, setConfirmTerminate] = useState(false)

  if (!can('EMPLOYEE_MANAGE')) return null

  const setStatus = (status: EmployeeStatus, message: string) =>
    changeStatus.mutate(status, {
      onSuccess: () => {
        toast.success(message)
        setConfirmTerminate(false)
      },
      onError: (e) => toast.error(errorMessage(e)),
    })

  const canInvite = can('USER_MANAGE') && employee.status !== 'terminated' && (employee.access === 'none' || employee.access === 'invited')

  return (
    <div className="flex items-center gap-2">
      <Button variant="outline" size="sm" onClick={() => setEditOpen(true)}>
        <Pencil /> Edit
      </Button>
      {!isSelf && (
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="outline" size="sm">
              Actions <ChevronDown className="opacity-60" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-52">
            {canInvite && (
              <DropdownMenuItem
                onSelect={() =>
                  invite.mutate(employee.account?.role ?? 'EMPLOYEE', {
                    onSuccess: () => toast.success(`Invitation sent to ${employee.email}`),
                    onError: (e) => toast.error(errorMessage(e)),
                  })
                }
              >
                <Mail /> {employee.access === 'none' ? 'Invite to WorkPulse' : 'Resend invitation'}
              </DropdownMenuItem>
            )}
            {employee.status === 'active' && (
              <DropdownMenuItem onSelect={() => setStatus('on_leave', 'Marked as on leave')}>
                <CalendarClock /> Mark as on leave
              </DropdownMenuItem>
            )}
            {employee.status !== 'active' && (
              <DropdownMenuItem onSelect={() => setStatus('active', employee.status === 'terminated' ? 'Employee reactivated' : 'Marked as active')}>
                <UserRound /> {employee.status === 'terminated' ? 'Reactivate employee' : 'Mark as active'}
              </DropdownMenuItem>
            )}
            {employee.status !== 'terminated' && (
              <>
                <DropdownMenuSeparator />
                <DropdownMenuItem variant="destructive" onSelect={() => setConfirmTerminate(true)}>
                  <UserX /> Terminate employment
                </DropdownMenuItem>
              </>
            )}
          </DropdownMenuContent>
        </DropdownMenu>
      )}
      <EmployeeFormDialog open={editOpen} onOpenChange={setEditOpen} employee={employee} />
      <ConfirmDialog
        open={confirmTerminate}
        onOpenChange={setConfirmTerminate}
        title={`Terminate ${employee.full_name}?`}
        description={
          employee.account
            ? 'Their WorkPulse account will be deactivated and all active sessions signed out immediately. You can reactivate them later.'
            : 'They will be marked as terminated and hidden from the default directory view. You can reactivate them later.'
        }
        confirmLabel="Terminate"
        destructive
        loading={changeStatus.isPending}
        onConfirm={() => setStatus('terminated', `${employee.full_name} was terminated`)}
      />
    </div>
  )
}

function ProfileSkeleton() {
  return (
    <div className="space-y-6">
      <Skeleton className="h-4 w-32" />
      <Card className="p-6">
        <div className="flex items-center gap-4">
          <Skeleton className="size-16 rounded-full" />
          <div className="space-y-2">
            <Skeleton className="h-5 w-48" />
            <Skeleton className="h-3 w-64" />
          </div>
        </div>
      </Card>
      <Skeleton className="h-64" />
    </div>
  )
}

export default function EmployeeProfilePage() {
  const { id } = useParams()
  const { can } = usePermissions()
  const query = useEmployee(id)
  const employee = query.data
  const isSelf = useAuthStore((s) => Boolean(employee?.account) && s.user?.id === employee?.account?.user_id)
  const [searchParams, setSearchParams] = useSearchParams()
  useDocumentTitle(employee?.full_name ?? 'Employee')

  const backLink = can('EMPLOYEE_VIEW') && (
    <Link to="/people/employees" className="inline-flex items-center gap-1.5 text-[13px] text-muted-foreground transition hover:text-foreground">
      <ArrowLeft className="size-3.5" /> Employees
    </Link>
  )

  if (query.isPending) return <ProfileSkeleton />
  if (query.isError || !employee) {
    const notFound = query.error instanceof ApiError && query.error.status === 404
    return (
      <div className="space-y-6">
        {backLink}
        <Card>
          <EmptyState
            icon={UserX}
            title={notFound ? 'Employee not found' : "Couldn't load this employee"}
            description={notFound ? "This employee doesn't exist or isn't in your scope." : errorMessage(query.error)}
            action={
              notFound ? undefined : (
                <Button size="sm" variant="outline" onClick={() => void query.refetch()}>
                  Try again
                </Button>
              )
            }
          />
        </Card>
      </div>
    )
  }

  const tabs: { value: string; label: string; upcoming?: boolean }[] = [
    { value: 'overview', label: 'Overview' },
    { value: 'attendance', label: 'Attendance', upcoming: true },
    ...(isSelf || can('ACTIVITY_VIEW') ? [{ value: 'activity', label: 'Activity' }] : []),
    ...(isSelf || can('ACTIVITY_VIEW') ? [{ value: 'productivity', label: 'Productivity' }] : []),
    ...(isSelf || can('SCREENSHOT_VIEW') || can('POLICY_MANAGE') ? [{ value: 'screenshots', label: 'Screenshots' }] : []),
    { value: 'tasks', label: 'Tasks' },
    { value: 'devices', label: `Devices${employee.device_count ? ` · ${employee.device_count}` : ''}` },
    { value: 'permissions', label: 'Permissions' },
  ]

  return (
    <div className="space-y-6">
      {backLink}
      <Card className="overflow-hidden">
        <div className="h-16 bg-gradient-to-r from-primary-soft via-primary-soft/40 to-transparent" aria-hidden />
        <div className="-mt-8 flex flex-col gap-4 px-6 pb-6 sm:flex-row sm:items-end">
          <PersonAvatar name={employee.full_name} seed={employee.id} className="size-16 text-lg ring-4 ring-card" />
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2.5">
              <h1 className="text-xl font-semibold tracking-tight">{employee.full_name}</h1>
              <EmployeeStatusBadge status={employee.status} />
              <AccessBadge access={employee.access} />
            </div>
            <p className="mt-1 flex flex-wrap items-center gap-x-4 gap-y-1 text-[13px] text-muted-foreground">
              <span>{employee.job_title ?? 'No title'}</span>
              {employee.department && <span>{[employee.department.name, employee.team?.name].filter(Boolean).join(' · ')}</span>}
              <span className="inline-flex items-center gap-1">
                <Mail className="size-3.5" /> {employee.email}
              </span>
              {employee.location && (
                <span className="inline-flex items-center gap-1">
                  <MapPin className="size-3.5" /> {employee.location}
                </span>
              )}
            </p>
          </div>
          <ProfileActions employee={employee} />
        </div>
      </Card>

      <Tabs
        value={tabs.some((t) => t.value === searchParams.get('tab')) ? searchParams.get('tab')! : 'overview'}
        onValueChange={(tab) => setSearchParams(tab === 'overview' ? {} : { tab }, { replace: true })}
      >
        <TabsList>
          {tabs.map(({ value, label, upcoming }) => {
            const Icon = TAB_ICONS[value as keyof typeof TAB_ICONS]
            return (
              <TabsTrigger key={value} value={value} className={upcoming ? 'text-muted-foreground' : undefined}>
                <Icon /> {label}
                {upcoming && <span className="size-1.5 rounded-full bg-primary/40" aria-label="coming soon" />}
              </TabsTrigger>
            )
          })}
        </TabsList>
        <TabsContent value="overview">
          <OverviewTab employee={employee} />
        </TabsContent>
        {Object.entries(UPCOMING).map(([key, meta]) => (
          <TabsContent key={key} value={key}>
            <UpcomingPanel {...meta} bullets={'bullets' in meta ? [...meta.bullets] : undefined} />
          </TabsContent>
        ))}
        <TabsContent value="activity">
          <EmployeeActivityPanel employeeId={employee.id} firstName={employee.full_name.split(' ')[0]} />
        </TabsContent>
        <TabsContent value="tasks">
          <EmployeeTasksPanel employeeId={employee.id} firstName={employee.full_name.split(' ')[0]} />
        </TabsContent>
        <TabsContent value="productivity">
          <EmployeeProductivityView employeeId={employee.id} />
        </TabsContent>
        <TabsContent value="screenshots">
          <EmployeeScreenshotsPanel employeeId={employee.id} firstName={employee.full_name.split(' ')[0]} isSelf={isSelf} />
        </TabsContent>
        <TabsContent value="devices">
          <DevicesPanel employee={employee} canManage={can('EMPLOYEE_MANAGE')} />
        </TabsContent>
        <TabsContent value="permissions">
          <PermissionsPanel employee={employee} />
        </TabsContent>
      </Tabs>
    </div>
  )
}
