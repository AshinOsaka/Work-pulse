import { useMemo, useState, type FormEvent } from 'react'
import { Building2, ChevronDown, Copy, Download, Headset, KeyRound, Monitor, MonitorDown, Moon, Palette, Pencil, Settings, ShieldCheck, ShieldEllipsis, SlidersHorizontal, Sun, UserRound } from 'lucide-react'
import { Link, Outlet } from 'react-router'
import { toast } from 'sonner'

import { ConfirmDialog } from '@/components/common/confirm-dialog'
import { FormAlert, FormField } from '@/components/common/form-field'
import { LinkTabs } from '@/components/common/link-tabs'
import { PageHeader } from '@/components/common/page-header'
import { PersonAvatar } from '@/components/common/person'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from '@/components/ui/card'
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Checkbox, Switch } from '@/components/ui/form-controls'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { RadioCard, RadioGroup } from '@/components/ui/radio-group'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { useUpdateProfile } from '@/features/auth/api'
import { useDepartments } from '@/features/people/api'
import { ActivityPolicyCard } from '@/features/activity/components/activity-policy-card'
import { LivePolicyCard } from '@/features/live/components/live-policy-card'
import { ScreenshotPolicyCard } from '@/features/screenshots/components/screenshot-policy-card'
import { useAgentRelease, useUpdateCompany } from '@/features/settings/api'
import { ApiError, errorMessage } from '@/lib/api-client'
import { capitalize, formatDate, formatDateTime, roleKeyLabel, timezones } from '@/lib/format'
import { cn } from '@/lib/utils'
import { useAuthStore, usePermissions } from '@/stores/auth-store'
import { useUiStore, type ThemePreference } from '@/stores/ui-store'
import type { CustomerSystem, ServiceType } from '@/types/api'

export default function SettingsLayout() {
  const { can } = usePermissions()
  const tabs = [
    { to: '/settings/profile', label: 'Profile', icon: UserRound },
    { to: '/settings/workspace', label: 'Workspace', icon: Building2 },
    { to: '/settings/agent', label: 'Desktop agent', icon: MonitorDown },
    { to: '/settings/privacy', label: 'Monitoring & privacy', icon: ShieldEllipsis },
    { to: '/settings/customer-systems', label: 'Customer systems', icon: Headset },
    ...(can('USER_MANAGE') ? [{ to: '/settings/roles', label: 'Roles & permissions', icon: KeyRound }] : []),
    ...(can('USER_MANAGE') ? [{ to: '/settings/access', label: 'Dashboard access', icon: SlidersHorizontal }] : []),
    { to: '/settings/appearance', label: 'Appearance', icon: Palette },
  ]
  return (
    <div className="space-y-6">
      <PageHeader title="Settings" description="Manage your profile, workspace and preferences." icon={Settings} />
      <LinkTabs tabs={tabs} />
      <Outlet />
    </div>
  )
}

export function DesktopAgentSettings() {
  const release = useAgentRelease()
  const { can } = usePermissions()
  const copy = (text: string) =>
    void navigator.clipboard
      .writeText(text)
      .then(() => toast.success('Copied'))
      .catch(() => toast.error('Copy failed'))

  const steps = [
    'Download and run the installer (per-user, no administrator rights needed).',
    'Open “WorkPulse Agent” — a small icon appears in the Windows system tray.',
    'Sign in with your WorkPulse email and password, or choose “Use an enrolment code instead” and paste the code your administrator gave you.',
    'Click “Start work” to begin a session. That’s it.',
  ]

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Monitor className="size-4 text-muted-foreground" aria-hidden /> WorkPulse desktop agent
            {release.data && <Badge variant="secondary">v{release.data.version}</Badge>}
          </CardTitle>
          <CardDescription>
            Install it on each employee’s Windows computer to record work sessions and activity. After setup it starts
            with Windows and reconnects on its own.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {release.data?.download_url ? (
            <Button asChild>
              <a href={release.data.download_url} download>
                <Download /> Download for Windows
              </a>
            </Button>
          ) : (
            <div className="rounded-lg border bg-subtle p-4 text-[13px] text-muted-foreground">
              No installer has been published for this workspace yet.
              {can('POLICY_MANAGE') && (
                <>
                  {' '}
                  An administrator can build a signed installer (see <code>docs/agent-packaging.md</code>) and set{' '}
                  <code>AGENT_DOWNLOAD_URL</code> on the server.
                </>
              )}
            </div>
          )}
          <div className="space-y-1.5">
            <Label htmlFor="agent-api">Server address (enter this in the agent only if it asks)</Label>
            <div className="flex gap-2">
              <Input id="agent-api" readOnly value={release.data?.api_base ?? ''} className="font-mono text-[12px]" />
              <Button
                type="button"
                variant="outline"
                size="icon"
                aria-label="Copy server address"
                disabled={!release.data}
                onClick={() => release.data && copy(release.data.api_base)}
              >
                <Copy />
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>How to set it up</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <ol className="space-y-3">
            {steps.map((text, i) => (
              <li key={i} className="flex gap-3 text-[13px]">
                <span className="flex size-6 shrink-0 items-center justify-center rounded-full bg-primary-soft text-[12px] font-semibold text-primary-soft-foreground">
                  {i + 1}
                </span>
                <span className="pt-0.5">{text}</span>
              </li>
            ))}
          </ol>
          <p className="text-[12px] text-muted-foreground">
            After the first setup, the agent starts automatically each time you sign in to Windows and reconnects on its
            own — you don’t need to open it again.
          </p>
        </CardContent>
      </Card>

      {can('POLICY_MANAGE') && (
        <Card>
          <CardHeader>
            <CardTitle>For administrators</CardTitle>
            <CardDescription>
              Issue a one-time enrolment code for a specific employee’s device (no password needed), or revoke a device.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-2">
            <Button asChild variant="outline">
              <Link to="/people/employees">
                <ShieldCheck /> Manage employees &amp; devices
              </Link>
            </Button>
            <p className="text-[12px] text-muted-foreground">
              People → open an employee → Devices → Register device. Codes are single-use and expire after 72 hours.
            </p>
          </CardContent>
        </Card>
      )}
    </div>
  )
}

export function ProfileSettings() {
  const user = useAuthStore((s) => s.user)
  const update = useUpdateProfile()
  const [name, setName] = useState(user?.full_name ?? '')
  if (!user) return null

  const fieldErrors = update.error instanceof ApiError ? update.error.fieldErrors : {}
  const dirty = name.trim() !== user.full_name

  const onSubmit = (event: FormEvent) => {
    event.preventDefault()
    update.mutate(
      { full_name: name.trim() },
      { onSuccess: () => toast.success('Profile updated'), onError: (e) => toast.error(errorMessage(e)) },
    )
  }

  return (
    <Card>
      <form onSubmit={onSubmit}>
        <CardHeader>
          <CardTitle>Profile</CardTitle>
          <CardDescription>How you appear to others in your workspace.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-5">
          <div className="flex items-center gap-4">
            <PersonAvatar name={name || user.full_name} seed={user.id} className="size-14 text-base" />
            <div>
              <p className="font-medium">{user.full_name}</p>
              <div className="mt-1 flex items-center gap-2">
                <Badge variant="soft">{roleKeyLabel(user.role_key)}</Badge>
                <span className="text-[12px] text-muted-foreground">Member since {formatDate(user.created_at)}</span>
              </div>
            </div>
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <FormField label="Full name" value={name} onChange={(e) => setName(e.target.value)} error={fieldErrors.full_name} />
            <div className="space-y-1.5">
              <Label htmlFor="email">Email</Label>
              <Input id="email" value={user.email} disabled />
              <p className="text-[12px] text-muted-foreground">{user.email_verified ? 'Verified' : 'Not verified yet'}</p>
            </div>
          </div>
          <p className="text-[12px] text-muted-foreground">Last sign-in: {formatDateTime(user.last_login_at)}</p>
        </CardContent>
        <CardFooter className="justify-end">
          <Button type="button" variant="ghost" size="sm" disabled={!dirty} onClick={() => setName(user.full_name)}>
            Cancel
          </Button>
          <Button type="submit" size="sm" disabled={!dirty || name.trim().length < 2} loading={update.isPending}>
            Save changes
          </Button>
        </CardFooter>
      </form>
    </Card>
  )
}

const SIZES = ['1-10', '11-50', '51-200', '201-1000', '1000+']
const NONE = '__none__'

const WEEKDAYS: { iso: number; label: string }[] = [
  { iso: 1, label: 'Mon' },
  { iso: 2, label: 'Tue' },
  { iso: 3, label: 'Wed' },
  { iso: 4, label: 'Thu' },
  { iso: 5, label: 'Fri' },
  { iso: 6, label: 'Sat' },
  { iso: 7, label: 'Sun' },
]

const sevenDays = (values: number[] | undefined) => [...(values ?? []), 0, 0, 0, 0, 0, 0, 0].slice(0, 7)

/** Which weekdays are working days, plus one-off company holidays. Used for productivity and attendance. */
function WorkScheduleCard() {
  const company = useAuthStore((s) => s.company)
  const { can } = usePermissions()
  const update = useUpdateCompany()
  const editable = can('POLICY_MANAGE')
  const [workDays, setWorkDays] = useState<number[]>(company?.work_days ?? [1, 2, 3, 4, 5])
  const [holidays, setHolidays] = useState<string[]>(company?.holidays ?? [])
  // Required minutes per weekday, Monday first (0 = no requirement). Attendance compares active time with it.
  const [required, setRequired] = useState<number[]>(() => sevenDays(company?.required_minutes))
  const [newDate, setNewDate] = useState('')
  // Logged meeting time per person per day that counts without a manager's approval.
  const [autoMinutes, setAutoMinutes] = useState<number>(company?.time_claim_auto_minutes ?? 120)
  // Start-of-day check: tell managers when a computer hasn't reported soon after the workday starts.
  const [startCheck, setStartCheck] = useState(() => ({
    enabled: company?.start_check_enabled ?? false,
    time: company?.start_check_time ?? '09:00',
    grace: company?.start_check_grace_minutes ?? 30,
  }))
  if (!company) return null

  const sameDays = [...workDays].sort().join(',') === [...(company.work_days ?? [])].sort().join(',')
  const sameHolidays = [...holidays].sort().join(',') === [...(company.holidays ?? [])].sort().join(',')
  const sameRequired = required.join(',') === sevenDays(company.required_minutes).join(',')
  const sameAuto = autoMinutes === (company.time_claim_auto_minutes ?? 120)
  const sameStart =
    startCheck.enabled === company.start_check_enabled &&
    startCheck.time === company.start_check_time &&
    startCheck.grace === company.start_check_grace_minutes
  const dirty = !sameDays || !sameHolidays || !sameRequired || !sameAuto || !sameStart
  const setRequiredPart = (iso: number, part: 'h' | 'm', raw: string) =>
    setRequired((list) => {
      const next = [...list]
      const current = next[iso - 1]
      const value = Math.max(0, Math.floor(Number(raw) || 0))
      const hours = part === 'h' ? Math.min(24, value) : Math.floor(current / 60)
      const minutes = part === 'm' ? Math.min(59, value) : current % 60
      next[iso - 1] = Math.min(1440, hours * 60 + minutes)
      return next
    })
  const toggle = (iso: number) =>
    setWorkDays((days) => (days.includes(iso) ? days.filter((d) => d !== iso) : [...days, iso].sort((a, b) => a - b)))
  const addHoliday = () => {
    if (newDate && !holidays.includes(newDate)) setHolidays((h) => [...h, newDate].sort())
    setNewDate('')
  }
  const save = () => {
    if (workDays.length === 0) {
      toast.error('Select at least one working day.')
      return
    }
    update.mutate(
      {
        work_days: workDays,
        holidays,
        required_minutes: required,
        time_claim_auto_minutes: autoMinutes,
        start_check_enabled: startCheck.enabled,
        start_check_time: startCheck.time,
        start_check_grace_minutes: startCheck.grace,
      },
      { onSuccess: () => toast.success('Work schedule updated') },
    )
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Working days &amp; holidays</CardTitle>
        <CardDescription>
          Which days count as working days for productivity and attendance. Non-working days (for example Sunday) and
          holidays are shown as holidays, not as absence — a 6-day week scores over Monday–Saturday. Required hours are
          used only by the Attendance report, which compares them with each person&apos;s active time.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-5">
        <div className="space-y-2">
          <Label>Working days</Label>
          <div className="flex flex-wrap gap-2">
            {WEEKDAYS.map((d) => (
              <label
                key={d.iso}
                className={cn(
                  'flex cursor-pointer items-center gap-2 rounded-md border px-3 py-1.5 text-[13px] transition',
                  workDays.includes(d.iso) ? 'border-primary/50 bg-primary-soft/40 font-medium' : 'text-muted-foreground',
                  !editable && 'cursor-not-allowed opacity-60',
                )}
              >
                <Checkbox checked={workDays.includes(d.iso)} onCheckedChange={() => toggle(d.iso)} disabled={!editable} aria-label={d.label} />
                {d.label}
              </label>
            ))}
          </div>
        </div>
        <div className="space-y-2">
          <Label>Required hours per day</Label>
          <p className="text-[12px] text-muted-foreground">
            Active time a person should reach on each working day (breaks excluded — for example 9:30–6:00 with a
            40-minute break is 7h 50m). Leave 0 for no requirement.
          </p>
          <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {WEEKDAYS.filter((d) => workDays.includes(d.iso)).map((d) => (
              <div key={d.iso} className="flex items-center gap-2 rounded-md border px-3 py-1.5">
                <span className="w-10 text-[13px] font-medium">{d.label}</span>
                <Input
                  type="number"
                  min={0}
                  max={24}
                  value={Math.floor(required[d.iso - 1] / 60)}
                  onChange={(e) => setRequiredPart(d.iso, 'h', e.target.value)}
                  disabled={!editable}
                  className="h-8 w-16 text-[13px] tabular"
                  aria-label={`${d.label} required hours`}
                />
                <span className="text-[12px] text-muted-foreground">h</span>
                <Input
                  type="number"
                  min={0}
                  max={59}
                  step={5}
                  value={required[d.iso - 1] % 60}
                  onChange={(e) => setRequiredPart(d.iso, 'm', e.target.value)}
                  disabled={!editable}
                  className="h-8 w-16 text-[13px] tabular"
                  aria-label={`${d.label} required minutes`}
                />
                <span className="text-[12px] text-muted-foreground">m</span>
              </div>
            ))}
          </div>
        </div>
        <div className="space-y-2">
          <Label htmlFor="claim-limit-hours">Meeting time without approval</Label>
          <p className="text-[12px] text-muted-foreground">
            Time a person can log per day for meetings, client visits and calls away from the computer that counts
            straight away (their manager is told and can still reject it). More than this waits for approval. Set 0 to
            approve every claim. It is added to attendance only, never to productivity.
          </p>
          <div className="flex w-fit items-center gap-2 rounded-md border px-3 py-1.5">
            <Input
              id="claim-limit-hours"
              type="number"
              min={0}
              max={12}
              value={Math.floor(autoMinutes / 60)}
              onChange={(e) => setAutoMinutes(Math.min(720, Math.max(0, Math.floor(Number(e.target.value) || 0)) * 60 + (autoMinutes % 60)))}
              disabled={!editable}
              className="h-8 w-16 text-[13px] tabular"
              aria-label="Hours without approval"
            />
            <span className="text-[12px] text-muted-foreground">h</span>
            <Input
              type="number"
              min={0}
              max={59}
              step={5}
              value={autoMinutes % 60}
              onChange={(e) => setAutoMinutes(Math.min(720, Math.floor(autoMinutes / 60) * 60 + Math.min(59, Math.max(0, Math.floor(Number(e.target.value) || 0)))))}
              disabled={!editable}
              className="h-8 w-16 text-[13px] tabular"
              aria-label="Minutes without approval"
            />
            <span className="text-[12px] text-muted-foreground">m per day</span>
          </div>
        </div>
        <div className="space-y-2">
          <Label htmlFor="start-check">Start-of-day check</Label>
          <p className="text-[12px] text-muted-foreground">
            On working days, alert managers when an employee&apos;s computer hasn&apos;t reported by this time — it may be off,
            offline, or WorkPulse may have been removed. People on leave are skipped.
          </p>
          <div className="flex flex-wrap items-center gap-3 rounded-md border px-3 py-2">
            <label className={cn('flex items-center gap-2 text-[13px] font-medium', !editable && 'opacity-60')}>
              <Switch
                id="start-check"
                checked={startCheck.enabled}
                onCheckedChange={(enabled) => setStartCheck((c) => ({ ...c, enabled }))}
                disabled={!editable}
              />
              {startCheck.enabled ? 'On' : 'Off'}
            </label>
            <span className="text-[12px] text-muted-foreground">Workday starts at</span>
            <Input
              type="time"
              value={startCheck.time}
              onChange={(e) => e.target.value && setStartCheck((c) => ({ ...c, time: e.target.value }))}
              disabled={!editable || !startCheck.enabled}
              className="h-8 w-28 text-[13px] tabular"
              aria-label="Workday start time"
            />
            <span className="text-[12px] text-muted-foreground">alert after</span>
            <Select
              value={String(startCheck.grace)}
              onValueChange={(v) => setStartCheck((c) => ({ ...c, grace: Number(v) }))}
              disabled={!editable || !startCheck.enabled}
            >
              <SelectTrigger size="sm" className="w-28" aria-label="Alert after">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {[15, 30, 60, 90].map((m) => (
                  <SelectItem key={m} value={String(m)}>
                    {m < 60 ? `${m} min` : m === 60 ? '1 hour' : '1.5 hours'}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <span className="text-[12px] text-muted-foreground">({company.timezone.replaceAll('_', ' ')})</span>
          </div>
        </div>
        <div className="space-y-2">
          <Label htmlFor="holiday-date">Holidays</Label>
          {editable && (
            <div className="flex gap-2">
              <Input id="holiday-date" type="date" value={newDate} onChange={(e) => setNewDate(e.target.value)} className="w-44" />
              <Button type="button" size="sm" variant="outline" onClick={addHoliday} disabled={!newDate}>
                Add holiday
              </Button>
            </div>
          )}
          {holidays.length === 0 ? (
            <p className="text-[13px] text-muted-foreground">No holidays added. Weekly days off above still apply.</p>
          ) : (
            <ul className="flex flex-wrap gap-2">
              {holidays.map((date) => (
                <li key={date} className="inline-flex items-center gap-1.5 rounded-full border bg-subtle px-2.5 py-1 text-[12px] tabular">
                  {formatDate(date)}
                  {editable && (
                    <button
                      type="button"
                      onClick={() => setHolidays((h) => h.filter((x) => x !== date))}
                      className="text-muted-foreground hover:text-destructive"
                      aria-label={`Remove holiday ${date}`}
                    >
                      ×
                    </button>
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>
      </CardContent>
      {editable && (
        <CardFooter className="justify-end">
          <Button type="button" size="sm" disabled={!dirty} loading={update.isPending} onClick={save}>
            Save schedule
          </Button>
        </CardFooter>
      )}
    </Card>
  )
}

const ALL_DEPTS = '__all__'
const ALL_SERVICES = '__all__'
const NO_SERVICE = '__none__'
const SERVICE_TYPES: { value: ServiceType; label: string }[] = [
  { value: 'visa', label: 'Visa' },
  { value: 'ticketing', label: 'Ticketing' },
  { value: 'insurance', label: 'Insurance' },
  { value: 'forex', label: 'Forex' },
]
const serviceLabel = (value: ServiceType | null | undefined) => SERVICE_TYPES.find((t) => t.value === value)?.label

/** Pick any number of departments; none selected means "All departments". */
function DepartmentPicker({
  value,
  onChange,
  departments,
  compact = false,
}: {
  value: string[]
  onChange: (ids: string[]) => void
  departments: { id: string; name: string }[]
  compact?: boolean
}) {
  const names = value.map((id) => departments.find((d) => d.id === id)?.name ?? 'Unknown department')
  const label = value.length === 0 ? 'All departments' : compact || value.length === 1 ? names.join(', ') : `${value.length} departments`
  const toggle = (id: string, on: boolean) => onChange(on ? [...value, id] : value.filter((v) => v !== id))
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          type="button"
          variant="outline"
          className={cn(
            'justify-between gap-2 font-normal',
            compact ? 'h-7 max-w-64 shrink-0 px-2.5 text-[12px]' : 'h-9 w-full text-[13px]',
            value.length === 0 && 'text-muted-foreground',
          )}
          title={value.length === 0 ? 'All departments' : names.join(', ')}
          aria-label="Departments"
        >
          <span className="truncate">{label}</span>
          <ChevronDown className="size-3.5 shrink-0 opacity-60" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="max-h-72 w-72 overflow-y-auto">
        <DropdownMenuCheckboxItem
          checked={value.length === 0}
          onCheckedChange={() => onChange([])}
          onSelect={(e) => e.preventDefault()}
        >
          All departments
        </DropdownMenuCheckboxItem>
        <DropdownMenuSeparator />
        {departments.length === 0 ? (
          <p className="px-2 py-1.5 text-[12px] text-muted-foreground">No departments yet — add them under People.</p>
        ) : (
          departments.map((d) => (
            <DropdownMenuCheckboxItem
              key={d.id}
              checked={value.includes(d.id)}
              onCheckedChange={(on) => toggle(d.id, on === true)}
              onSelect={(e) => e.preventDefault()}
            >
              {d.name}
            </DropdownMenuCheckboxItem>
          ))
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

function CustomerSystemsCard() {
  const company = useAuthStore((s) => s.company)
  const { can } = usePermissions()
  const update = useUpdateCompany()
  const editable = can('POLICY_MANAGE')
  const departments = useDepartments(can('EMPLOYEE_VIEW'))
  const deptName = useMemo(() => {
    const map = new Map<string, string>()
    for (const d of departments.data ?? []) map.set(d.id, d.name)
    return map
  }, [departments.data])
  const [systems, setSystems] = useState<CustomerSystem[]>(company?.customer_systems ?? [])
  const [label, setLabel] = useState('')
  const [kind, setKind] = useState<'app' | 'website'>('website')
  const [pattern, setPattern] = useState('')
  // Departments for the next system to add; empty = All departments. Kept after adding, for quick repeats.
  const [departmentIds, setDepartmentIds] = useState<string[]>([])
  // Service type for the next system; '' = not chosen yet (required for websites, optional for apps).
  const [serviceType, setServiceType] = useState<ServiceType | ''>('')
  const [filter, setFilter] = useState<string>(ALL_DEPTS)
  const [serviceFilter, setServiceFilter] = useState<string>(ALL_SERVICES)
  const [editing, setEditing] = useState<{
    key: string
    label: string
    kind: 'app' | 'website'
    pattern: string
    service_type: ServiceType | null
  } | null>(null)
  const [removing, setRemoving] = useState<CustomerSystem | null>(null)
  if (!company) return null

  const deptList = departments.data ?? []
  const serialise = (list: CustomerSystem[]) =>
    list
      .map(
        (s) =>
          `${s.kind}:${s.pattern}:${s.label}:${s.service_type ?? ''}:${[...(s.department_ids ?? [])].sort().join(',')}`,
      )
      .sort()
      .join('|')
  const dirty = serialise(systems) !== serialise(company.customer_systems ?? [])
  const add = () => {
    const l = label.trim()
    const p = pattern.trim()
    if (!l || !p) return
    if (kind === 'website' && !serviceType) {
      toast.error('Choose the service type: Visa, Ticketing, Insurance or Forex.')
      return
    }
    if (systems.some((s) => s.kind === kind && s.pattern.toLowerCase() === p.toLowerCase())) {
      toast.error('That system is already in the list.')
      return
    }
    setSystems((list) => [
      ...list,
      { label: l, kind, pattern: p, department_ids: departmentIds, service_type: serviceType || null },
    ])
    setLabel('')
    setPattern('')
    // Asked afresh for every website.
    setServiceType('')
  }
  const saveEdit = () => {
    if (!editing) return
    const l = editing.label.trim()
    const p = editing.pattern.trim()
    if (!l || !p) {
      toast.error('Enter a name and a domain or program name.')
      return
    }
    const clash = systems.some(
      (x) => `${x.kind}:${x.pattern}` !== editing.key && x.kind === editing.kind && x.pattern.toLowerCase() === p.toLowerCase(),
    )
    if (clash) {
      toast.error('That system is already in the list.')
      return
    }
    setSystems((list) =>
      list.map((x) =>
        `${x.kind}:${x.pattern}` === editing.key
          ? { ...x, label: l, kind: editing.kind, pattern: p, service_type: editing.service_type }
          : x,
      ),
    )
    setEditing(null)
  }
  const onEditKey = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      e.preventDefault()
      saveEdit()
    } else if (e.key === 'Escape') {
      e.preventDefault()
      setEditing(null)
    }
  }
  const setSystemDepartments = (target: CustomerSystem, ids: string[]) =>
    setSystems((list) =>
      list.map((x) => (x.kind === target.kind && x.pattern === target.pattern ? { ...x, department_ids: ids } : x)),
    )
  const save = () => update.mutate({ customer_systems: systems }, { onSuccess: () => toast.success('Customer systems updated') })

  // Filtering by a department shows its systems plus those that apply to all departments.
  const visible = systems.filter((s) => {
    const ids = s.department_ids ?? []
    const inDept = filter === ALL_DEPTS || ids.length === 0 || ids.includes(filter)
    const inService =
      serviceFilter === ALL_SERVICES || (s.service_type ?? NO_SERVICE) === serviceFilter
    return inDept && inService
  })
  const filtered = filter !== ALL_DEPTS || serviceFilter !== ALL_SERVICES

  return (
    <Card>
      <CardHeader>
        <CardTitle>Customer-facing systems</CardTitle>
        <CardDescription>
          Register your CRM (for example OsakaConnect), ticketing, telephony or chat tools. Time spent in them is
          reported as <strong>customer time</strong>, so staff who serve customers are measured by that work, not only
          by keyboard activity. Add a website by its domain (subdomains included) or an app by its program name, choose
          its service (Visa, Ticketing, Insurance or Forex), and tag it with one or more departments (or All
          departments) to group and filter them.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {editable && (
          <div className="grid gap-2 sm:grid-cols-[1fr_7.5rem_1fr_8.5rem_10rem_auto]">
            <Input value={label} onChange={(e) => setLabel(e.target.value)} placeholder="Name (e.g. OsakaConnect)" maxLength={60} aria-label="System name" />
            <Select value={kind} onValueChange={(v) => setKind(v as 'app' | 'website')}>
              <SelectTrigger aria-label="Type">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="website">Website</SelectItem>
                <SelectItem value="app">Application</SelectItem>
              </SelectContent>
            </Select>
            <Input
              value={pattern}
              onChange={(e) => setPattern(e.target.value)}
              placeholder={kind === 'website' ? 'crm.example.com' : 'osakaconnect.exe'}
              maxLength={120}
              aria-label="Domain or program name"
              onKeyDown={(e) => e.key === 'Enter' && (e.preventDefault(), add())}
            />
            <Select
              value={serviceType === '' && kind === 'app' ? NO_SERVICE : serviceType}
              onValueChange={(v) => setServiceType(v === NO_SERVICE ? '' : (v as ServiceType))}
            >
              <SelectTrigger
                aria-label="Service type"
                aria-required={kind === 'website'}
                className={cn(serviceType === '' && 'text-muted-foreground')}
              >
                <SelectValue placeholder="Service type" />
              </SelectTrigger>
              <SelectContent>
                {SERVICE_TYPES.map((t) => (
                  <SelectItem key={t.value} value={t.value}>{t.label}</SelectItem>
                ))}
                {kind === 'app' && <SelectItem value={NO_SERVICE}>No service</SelectItem>}
              </SelectContent>
            </Select>
            <DepartmentPicker value={departmentIds} onChange={setDepartmentIds} departments={deptList} />
            <Button
              type="button"
              size="sm"
              variant="outline"
              onClick={add}
              disabled={!label.trim() || !pattern.trim() || (kind === 'website' && !serviceType)}
              title={kind === 'website' && !serviceType ? 'Choose the service type first' : undefined}
            >
              Add
            </Button>
          </div>
        )}
        {systems.length > 0 && (
          <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
            <div className="flex items-center gap-2">
              <span className="text-[12px] text-muted-foreground">Service</span>
              <Select value={serviceFilter} onValueChange={setServiceFilter}>
                <SelectTrigger className="h-8 w-40" aria-label="Filter by service type">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={ALL_SERVICES}>All services</SelectItem>
                  {SERVICE_TYPES.map((t) => (
                    <SelectItem key={t.value} value={t.value}>{t.label}</SelectItem>
                  ))}
                  <SelectItem value={NO_SERVICE}>Not set</SelectItem>
                </SelectContent>
              </Select>
            </div>
            {deptList.length > 0 && (
              <div className="flex items-center gap-2">
                <span className="text-[12px] text-muted-foreground">Department</span>
                <Select value={filter} onValueChange={setFilter}>
                  <SelectTrigger className="h-8 w-60" aria-label="Filter by department">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value={ALL_DEPTS}>All departments</SelectItem>
                    {deptList.map((d) => (
                      <SelectItem key={d.id} value={d.id}>{d.name}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            )}
          </div>
        )}
        {systems.length === 0 ? (
          <p className="text-[13px] text-muted-foreground">No customer systems yet. Customer time is not reported until you add one.</p>
        ) : visible.length === 0 ? (
          <p className="text-[13px] text-muted-foreground">
            {filtered ? 'No systems match these filters.' : 'No systems in this department.'}
          </p>
        ) : (
          <ul className="divide-y rounded-lg border">
            {visible.map((s) => {
              const key = `${s.kind}:${s.pattern}`
              if (editing && editing.key === key) {
                return (
                  <li key={key} className="flex flex-wrap items-center gap-2 bg-subtle/60 px-3 py-2 sm:flex-nowrap">
                    <Select value={editing.kind} onValueChange={(v) => setEditing({ ...editing, kind: v as 'app' | 'website' })}>
                      <SelectTrigger className="h-8 w-32 shrink-0" aria-label="Type">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="website">Website</SelectItem>
                        <SelectItem value="app">Application</SelectItem>
                      </SelectContent>
                    </Select>
                    <Select
                      value={editing.service_type ?? NO_SERVICE}
                      onValueChange={(v) =>
                        setEditing({ ...editing, service_type: v === NO_SERVICE ? null : (v as ServiceType) })
                      }
                    >
                      <SelectTrigger className="h-8 w-32 shrink-0" aria-label="Service type">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {SERVICE_TYPES.map((t) => (
                          <SelectItem key={t.value} value={t.value}>{t.label}</SelectItem>
                        ))}
                        <SelectItem value={NO_SERVICE}>No service</SelectItem>
                      </SelectContent>
                    </Select>
                    <Input
                      value={editing.label}
                      onChange={(e) => setEditing({ ...editing, label: e.target.value })}
                      onKeyDown={onEditKey}
                      maxLength={60}
                      className="h-8 min-w-0 flex-1 text-[13px]"
                      aria-label="System name"
                    />
                    <Input
                      value={editing.pattern}
                      onChange={(e) => setEditing({ ...editing, pattern: e.target.value })}
                      onKeyDown={onEditKey}
                      maxLength={120}
                      placeholder={editing.kind === 'website' ? 'crm.example.com' : 'osakaconnect.exe'}
                      className="h-8 min-w-0 flex-1 text-[13px]"
                      aria-label="Domain or program name"
                    />
                    <Button type="button" size="sm" className="h-8" onClick={saveEdit}>
                      Done
                    </Button>
                    <Button type="button" size="sm" variant="ghost" className="h-8" onClick={() => setEditing(null)}>
                      Cancel
                    </Button>
                  </li>
                )
              }
              return (
              <li key={key} className="group flex items-center gap-3 px-3 py-2">
                <Badge variant="secondary" className="shrink-0 capitalize">{s.kind}</Badge>
                {serviceLabel(s.service_type) && (
                  <Badge variant="outline" className="shrink-0">{serviceLabel(s.service_type)}</Badge>
                )}
                {editable ? (
                  <button
                    type="button"
                    onClick={() =>
                      setEditing({ key, label: s.label, kind: s.kind, pattern: s.pattern, service_type: s.service_type ?? null })
                    }
                    className="flex min-w-0 flex-1 items-center gap-1.5 rounded text-left text-[13px]"
                    title="Click to edit"
                  >
                    <span className="truncate">
                      <span className="font-medium group-hover:text-primary">{s.label}</span>{' '}
                      <span className="text-muted-foreground">· {s.pattern}</span>
                    </span>
                    <Pencil className="size-3.5 shrink-0 text-muted-foreground opacity-0 transition group-hover:opacity-100" aria-hidden />
                  </button>
                ) : (
                  <span className="min-w-0 flex-1 truncate text-[13px]">
                    <span className="font-medium">{s.label}</span> <span className="text-muted-foreground">· {s.pattern}</span>
                  </span>
                )}
                {editable ? (
                  <DepartmentPicker
                    compact
                    value={s.department_ids ?? []}
                    onChange={(ids) => setSystemDepartments(s, ids)}
                    departments={deptList}
                  />
                ) : (s.department_ids ?? []).length === 0 ? (
                  <Badge variant="secondary" className="shrink-0">All departments</Badge>
                ) : (
                  <span className="flex shrink-0 flex-wrap justify-end gap-1">
                    {(s.department_ids ?? []).map((id) => (
                      <Badge key={id} variant="outline">{deptName.get(id) ?? 'Unknown department'}</Badge>
                    ))}
                  </span>
                )}
                {editable && (
                  <button
                    type="button"
                    onClick={() => setRemoving(s)}
                    className="text-muted-foreground hover:text-destructive"
                    aria-label={`Remove ${s.label}`}
                  >
                    ×
                  </button>
                )}
              </li>
              )
            })}
          </ul>
        )}
      </CardContent>
      <ConfirmDialog
        open={Boolean(removing)}
        onOpenChange={(open) => !open && setRemoving(null)}
        title={`Remove ${removing?.label ?? 'this system'}?`}
        description={
          removing ? (
            <>
              Time spent in <strong>{removing.pattern}</strong> will no longer count as customer time. Click{' '}
              <strong>Save customer systems</strong> to apply the change.
            </>
          ) : null
        }
        confirmLabel="Remove"
        destructive
        onConfirm={() => {
          if (removing) {
            setSystems((list) => list.filter((x) => !(x.kind === removing.kind && x.pattern === removing.pattern)))
            if (editing?.key === `${removing.kind}:${removing.pattern}`) setEditing(null)
          }
          setRemoving(null)
        }}
      />
      {editable && (
        <CardFooter className="justify-end">
          <Button type="button" size="sm" disabled={!dirty} loading={update.isPending} onClick={save}>
            Save customer systems
          </Button>
        </CardFooter>
      )}
    </Card>
  )
}

export function WorkspaceSettings() {
  const company = useAuthStore((s) => s.company)
  const { can } = usePermissions()
  const update = useUpdateCompany()
  const zones = useMemo(() => timezones(), [])
  const [form, setForm] = useState({
    name: company?.name ?? '',
    timezone: company?.timezone ?? 'UTC',
    industry: company?.industry ?? '',
    size: company?.size ?? null,
  })
  if (!company) return null
  const editable = can('POLICY_MANAGE')
  const errors = update.error instanceof ApiError ? update.error.fieldErrors : {}
  const dirty =
    form.name.trim() !== company.name ||
    form.timezone !== company.timezone ||
    (form.industry.trim() || null) !== company.industry ||
    form.size !== company.size

  const onSubmit = (event: FormEvent) => {
    event.preventDefault()
    update.mutate(
      { name: form.name.trim(), timezone: form.timezone, industry: form.industry.trim() || null, size: form.size },
      { onSuccess: () => toast.success('Workspace updated') },
    )
  }

  return (
    <div className="space-y-6">
    <Card>
      <form onSubmit={onSubmit} noValidate>
        <CardHeader>
          <CardTitle>Workspace profile</CardTitle>
          <CardDescription>
            {editable ? 'Details shown across your workspace and in invitations.' : 'Only administrators can change these details.'}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {update.error && !Object.keys(errors).length && <FormAlert>{errorMessage(update.error)}</FormAlert>}
          <div className="grid gap-4 sm:grid-cols-2">
            <FormField
              label="Workspace name"
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              error={errors.name}
              disabled={!editable}
            />
            <div className="space-y-1.5">
              <Label htmlFor="workspace-id">Workspace ID</Label>
              <Input id="workspace-id" value={company.slug} disabled />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="workspace-timezone">Default timezone</Label>
              <Select value={form.timezone} onValueChange={(v) => setForm({ ...form, timezone: v })} disabled={!editable}>
                <SelectTrigger id="workspace-timezone">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent className="max-h-72">
                  {(zones.includes(form.timezone) ? zones : [form.timezone, ...zones]).map((zone) => (
                    <SelectItem key={zone} value={zone}>
                      {zone.replaceAll('_', ' ')}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="workspace-size">Company size</Label>
              <Select value={form.size ?? NONE} onValueChange={(v) => setForm({ ...form, size: v === NONE ? null : v })} disabled={!editable}>
                <SelectTrigger id="workspace-size">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={NONE}>Not specified</SelectItem>
                  {SIZES.map((size) => (
                    <SelectItem key={size} value={size}>
                      {size} employees
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <FormField
              label="Industry"
              value={form.industry}
              onChange={(e) => setForm({ ...form, industry: e.target.value })}
              error={errors.industry}
              disabled={!editable}
              placeholder="e.g. Software"
            />
          </div>
          <dl className="grid gap-3 rounded-lg border bg-subtle px-4 py-3 text-[13px] sm:grid-cols-3">
            <div>
              <dt className="text-muted-foreground">Plan</dt>
              <dd className="font-medium">{capitalize(company.plan)}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Status</dt>
              <dd className="font-medium">{capitalize(company.status)}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Created</dt>
              <dd className="font-medium">{formatDate(company.created_at)}</dd>
            </div>
          </dl>
        </CardContent>
        {editable && (
          <CardFooter className="justify-end">
            <Button type="submit" size="sm" disabled={!dirty || form.name.trim().length < 2} loading={update.isPending}>
              Save changes
            </Button>
          </CardFooter>
        )}
      </form>
    </Card>
    <WorkScheduleCard />
    <ActivityPolicyCard />
    <ScreenshotPolicyCard />
    <LivePolicyCard />
    </div>
  )
}

const THEMES: { value: ThemePreference; label: string; icon: typeof Sun; preview: string }[] = [
  { value: 'light', label: 'Light', icon: Sun, preview: 'bg-[oklch(0.985_0.003_286)]' },
  { value: 'dark', label: 'Dark', icon: Moon, preview: 'bg-[oklch(0.17_0.013_285)]' },
  {
    value: 'system',
    label: 'System',
    icon: Monitor,
    preview: 'bg-gradient-to-r from-[oklch(0.985_0.003_286)] from-50% to-[oklch(0.17_0.013_285)] to-50%',
  },
]

/** Customer-facing systems in their own Settings tab (moved out of Workspace; same card, same saving). */
export function CustomerSystemsSettings() {
  return (
    <div className="space-y-6">
      <CustomerSystemsCard />
    </div>
  )
}

export function AppearanceSettings() {
  const theme = useUiStore((s) => s.theme)
  const setTheme = useUiStore((s) => s.setTheme)
  return (
    <Card>
      <CardHeader>
        <CardTitle>Appearance</CardTitle>
        <CardDescription>Choose how WorkPulse looks on this device.</CardDescription>
      </CardHeader>
      <CardContent>
        <RadioGroup
          aria-label="Theme"
          className="gap-3 sm:grid-cols-3"
          value={theme}
          onValueChange={(value) => setTheme(value as ThemePreference)}
        >
          {THEMES.map(({ value, label, icon: Icon, preview }) => (
            <RadioCard key={value} value={value} className="rounded-xl p-2 text-left">
              <div className={cn('h-20 rounded-lg border', preview)} />
              <div className="flex items-center gap-2 px-1 pt-2.5 pb-1 text-[13px] font-medium text-foreground">
                <Icon className="size-4 text-muted-foreground" /> {label}
              </div>
            </RadioCard>
          ))}
        </RadioGroup>
      </CardContent>
    </Card>
  )
}
