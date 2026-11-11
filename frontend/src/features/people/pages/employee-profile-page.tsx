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
  Trash2,
  UserRound,
  UserX,
} from 'lucide-react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router'
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
import {
  useChangeEmployeeStatus,
  useDeleteEmployee,
  useEmployee,
  useInviteEmployee,
  useResetEmployeePassword,
} from '@/features/people/api'
import { AccessBadge, EmployeeStatusBadge } from '@/features/people/components/badges'
import { DevicesPanel } from '@/features/people/components/devices-panel'
import { EmployeeFormDialog } from '@/features/people/components/employee-form-dialog'
import { PermissionsPanel } from '@/features/people/components/permissions-panel'
import { useHiddenSections } from '@/config/sections'
import { EMPLOYMENT_TYPES } from '@/features/people/meta'
import { EmployeeTimeClaims } from '@/features/time-claims/employee-time-claims'
import { EmployeeProductivityView } from '@/features/productivity/components/employee-view'
import { AttendanceCalendar } from '@/features/attendance/attendance-calendar'
import { todayIn } from '@/features/activity/format'
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

const TAB_ICONS = { overview: UserRound, attendance: Clock, activity: Activity, productivity: Gauge, tasks: ListChecks, screenshots: Camera, devices: Laptop, permissions: KeyRound }

function ProfileActions({ employee }: { employee: EmployeeDetail }) {
  const { can } = usePermissions()
  const isSelf = useAuthStore((s) => s.user?.id === employee.account?.user_id)
  const changeStatus = useChangeEmployeeStatus(employee.id)
  const invite = useInviteEmployee(employee.id)
  const resetPassword = useResetEmployeePassword(employee.id)
  const deleteEmployee = useDeleteEmployee(employee.id)
  const navigate = useNavigate()
  const [editOpen, setEditOpen] = useState(false)
  const [confirmTerminate, setConfirmTerminate] = useState(false)
  const [confirmReset, setConfirmReset] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState(false)

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
  const canResetPassword = can('USER_MANAGE') && employee.access === 'active'

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
                  invite.mutate(employee.account?.role_key ?? 'EMPLOYEE', {
                    onSuccess: () => toast.success(`Invitation sent to ${employee.email}`),
                    onError: (e) => toast.error(errorMessage(e)),
                  })
                }
              >
                <Mail /> {employee.access === 'none' ? 'Invite to WorkPulse' : 'Resend invitation'}
              </DropdownMenuItem>
            )}
            {canResetPassword && (
              <DropdownMenuItem onSelect={() => setConfirmReset(true)}>
                <KeyRound /> Reset password
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
            <DropdownMenuSeparator />
            {employee.status !== 'terminated' && (
              <DropdownMenuItem variant="destructive" onSelect={() => setConfirmTerminate(true)}>
                <UserX /> Terminate employment
              </DropdownMenuItem>
            )}
            <DropdownMenuItem variant="destructive" onSelect={() => setConfirmDelete(true)}>
              <Trash2 /> Delete permanently
            </DropdownMenuItem>
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
      <ConfirmDialog
        open={confirmReset}
        onOpenChange={setConfirmReset}
        title={`Reset ${employee.full_name}'s password?`}
        description={`We'll email ${employee.email} a secure link to set a new password. You won't see their password, and their current one keeps working until they choose a new one.`}
        confirmLabel="Send reset link"
        loading={resetPassword.isPending}
        onConfirm={() =>
          resetPassword.mutate(undefined, {
            onSuccess: () => {
              toast.success(`Password reset link sent to ${employee.email}`)
              setConfirmReset(false)
            },
            onError: (e) => toast.error(errorMessage(e)),
          })
        }
      />
      <ConfirmDialog
        open={confirmDelete}
        onOpenChange={setConfirmDelete}
        title={`Permanently delete ${employee.full_name}?`}
        description="This erases the employee and ALL of their data — their account, devices, work sessions, activity, screenshots, reports and task assignments. This cannot be undone. To keep a record instead, terminate them."
        confirmLabel="Delete permanently"
        destructive
        loading={deleteEmployee.isPending}
        onConfirm={() =>
          deleteEmployee.mutate(undefined, {
            onSuccess: () => {
              toast.success(`${employee.full_name} was permanently deleted`)
              setConfirmDelete(false)
              navigate('/people')
            },
            onError: (e) => toast.error(errorMessage(e)),
          })
        }
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
  const { isHidden } = useHiddenSections()
  const timeZone = useAuthStore((s) => s.company?.timezone ?? 'UTC')
  const today = todayIn(timeZone)
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

  const tabs: { value: string; label: string }[] = [
    { value: 'overview', label: 'Overview' },
    ...((isSelf || can('ACTIVITY_VIEW')) && !isHidden('attendance') ? [{ value: 'attendance', label: 'Attendance' }] : []),
    ...((isSelf || can('ACTIVITY_VIEW')) && !isHidden('activity') ? [{ value: 'activity', label: 'Activity' }] : []),
    ...((isSelf || can('ACTIVITY_VIEW')) && !isHidden('productivity') ? [{ value: 'productivity', label: 'Productivity' }] : []),
    ...((isSelf || can('SCREENSHOT_VIEW') || can('POLICY_MANAGE')) && !isHidden('screenshots') ? [{ value: 'screenshots', label: 'Screenshots' }] : []),
    ...((isSelf || can('TIME_CLAIM_MANAGE')) && !isHidden('time-claims') ? [{ value: 'time-claims', label: 'Time claims' }] : []),
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
          {tabs.map(({ value, label }) => {
            const Icon = TAB_ICONS[value as keyof typeof TAB_ICONS]
            return (
              <TabsTrigger key={value} value={value}>
                <Icon /> {label}
              </TabsTrigger>
            )
          })}
        </TabsList>
        <TabsContent value="overview">
          <OverviewTab employee={employee} />
        </TabsContent>
        <TabsContent value="attendance">
          <AttendanceCalendar employeeId={employee.id} name={employee.full_name} initialDay={today} today={today} timeZone={timeZone} />
        </TabsContent>
        <TabsContent value="activity">
          <EmployeeActivityPanel employeeId={employee.id} firstName={employee.full_name.split(' ')[0]} />
        </TabsContent>
        <TabsContent value="time-claims">
          <EmployeeTimeClaims employeeId={employee.id} name={employee.full_name} />
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
