import { useMemo, useState, type FormEvent } from 'react'
import { Building2, Copy, Download, KeyRound, Monitor, MonitorDown, Moon, Palette, Settings, ShieldCheck, ShieldEllipsis, Sun, UserRound } from 'lucide-react'
import { Link, Outlet } from 'react-router'
import { toast } from 'sonner'

import { FormAlert, FormField } from '@/components/common/form-field'
import { LinkTabs } from '@/components/common/link-tabs'
import { PageHeader } from '@/components/common/page-header'
import { PersonAvatar } from '@/components/common/person'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from '@/components/ui/card'
import { Checkbox } from '@/components/ui/form-controls'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { RadioCard, RadioGroup } from '@/components/ui/radio-group'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { useUpdateProfile } from '@/features/auth/api'
import { ActivityPolicyCard } from '@/features/activity/components/activity-policy-card'
import { LivePolicyCard } from '@/features/live/components/live-policy-card'
import { ScreenshotPolicyCard } from '@/features/screenshots/components/screenshot-policy-card'
import { useAgentRelease, useUpdateCompany } from '@/features/settings/api'
import { ApiError, errorMessage } from '@/lib/api-client'
import { capitalize, formatDate, formatDateTime, ROLE_LABELS, timezones } from '@/lib/format'
import { cn } from '@/lib/utils'
import { useAuthStore, usePermissions } from '@/stores/auth-store'
import { useUiStore, type ThemePreference } from '@/stores/ui-store'
import type { CustomerSystem } from '@/types/api'

export default function SettingsLayout() {
  const { can } = usePermissions()
  const tabs = [
    { to: '/settings/profile', label: 'Profile', icon: UserRound },
    { to: '/settings/workspace', label: 'Workspace', icon: Building2 },
    { to: '/settings/agent', label: 'Desktop agent', icon: MonitorDown },
    { to: '/settings/privacy', label: 'Monitoring & privacy', icon: ShieldEllipsis },
    { to: '/settings/appearance', label: 'Appearance', icon: Palette },
    ...(can('USER_MANAGE') ? [{ to: '/settings/roles', label: 'Roles & permissions', icon: KeyRound }] : []),
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
                <Badge variant="soft">{ROLE_LABELS[user.role]}</Badge>
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

/** Which weekdays are working days, plus one-off company holidays. Used for productivity and attendance. */
function WorkScheduleCard() {
  const company = useAuthStore((s) => s.company)
  const { can } = usePermissions()
  const update = useUpdateCompany()
  const editable = can('POLICY_MANAGE')
  const [workDays, setWorkDays] = useState<number[]>(company?.work_days ?? [1, 2, 3, 4, 5])
  const [holidays, setHolidays] = useState<string[]>(company?.holidays ?? [])
  const [newDate, setNewDate] = useState('')
  if (!company) return null

  const sameDays = [...workDays].sort().join(',') === [...(company.work_days ?? [])].sort().join(',')
  const sameHolidays = [...holidays].sort().join(',') === [...(company.holidays ?? [])].sort().join(',')
  const dirty = !sameDays || !sameHolidays
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
      { work_days: workDays, holidays },
      { onSuccess: () => toast.success('Work schedule updated') },
    )
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Working days &amp; holidays</CardTitle>
        <CardDescription>
          Which days count as working days for productivity and attendance. Non-working days (for example Sunday) and
          holidays are shown as holidays, not as absence — a 6-day week scores over Monday–Saturday.
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

function CustomerSystemsCard() {
  const company = useAuthStore((s) => s.company)
  const { can } = usePermissions()
  const update = useUpdateCompany()
  const editable = can('POLICY_MANAGE')
  const [systems, setSystems] = useState<CustomerSystem[]>(company?.customer_systems ?? [])
  const [label, setLabel] = useState('')
  const [kind, setKind] = useState<'app' | 'website'>('website')
  const [pattern, setPattern] = useState('')
  if (!company) return null

  const serialise = (list: CustomerSystem[]) => list.map((s) => `${s.kind}:${s.pattern}:${s.label}`).sort().join('|')
  const dirty = serialise(systems) !== serialise(company.customer_systems ?? [])
  const add = () => {
    const l = label.trim()
    const p = pattern.trim()
    if (!l || !p) return
    if (systems.some((s) => s.kind === kind && s.pattern.toLowerCase() === p.toLowerCase())) {
      toast.error('That system is already in the list.')
      return
    }
    setSystems((list) => [...list, { label: l, kind, pattern: p }])
    setLabel('')
    setPattern('')
  }
  const save = () => update.mutate({ customer_systems: systems }, { onSuccess: () => toast.success('Customer systems updated') })

  return (
    <Card>
      <CardHeader>
        <CardTitle>Customer-facing systems</CardTitle>
        <CardDescription>
          Register your CRM (for example OsakaConnect), ticketing, telephony or chat tools. Time spent in them is
          reported as <strong>customer time</strong>, so staff who serve customers are measured by that work, not only
          by keyboard activity. Add a website by its domain (subdomains included) or an app by its program name.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {editable && (
          <div className="grid gap-2 sm:grid-cols-[1fr_9rem_1fr_auto]">
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
            <Button type="button" size="sm" variant="outline" onClick={add} disabled={!label.trim() || !pattern.trim()}>
              Add
            </Button>
          </div>
        )}
        {systems.length === 0 ? (
          <p className="text-[13px] text-muted-foreground">No customer systems yet. Customer time is not reported until you add one.</p>
        ) : (
          <ul className="divide-y rounded-lg border">
            {systems.map((s) => (
              <li key={`${s.kind}:${s.pattern}`} className="flex items-center gap-3 px-3 py-2">
                <Badge variant="secondary" className="shrink-0 capitalize">{s.kind}</Badge>
                <span className="min-w-0 flex-1 truncate text-[13px]">
                  <span className="font-medium">{s.label}</span> <span className="text-muted-foreground">· {s.pattern}</span>
                </span>
                {editable && (
                  <button
                    type="button"
                    onClick={() => setSystems((list) => list.filter((x) => !(x.kind === s.kind && x.pattern === s.pattern)))}
                    className="text-muted-foreground hover:text-destructive"
                    aria-label={`Remove ${s.label}`}
                  >
                    ×
                  </button>
                )}
              </li>
            ))}
          </ul>
        )}
      </CardContent>
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
    <CustomerSystemsCard />
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
