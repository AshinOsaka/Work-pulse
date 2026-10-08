import { useMemo, useState, type FormEvent } from 'react'
import { Building2, KeyRound, Monitor, Moon, Palette, Settings, Sun, UserRound } from 'lucide-react'
import { Outlet } from 'react-router'
import { toast } from 'sonner'

import { FormAlert, FormField } from '@/components/common/form-field'
import { LinkTabs } from '@/components/common/link-tabs'
import { PageHeader } from '@/components/common/page-header'
import { PersonAvatar } from '@/components/common/person'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { RadioCard, RadioGroup } from '@/components/ui/radio-group'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { useUpdateProfile } from '@/features/auth/api'
import { ActivityPolicyCard } from '@/features/activity/components/activity-policy-card'
import { LivePolicyCard } from '@/features/live/components/live-policy-card'
import { ScreenshotPolicyCard } from '@/features/screenshots/components/screenshot-policy-card'
import { useUpdateCompany } from '@/features/settings/api'
import { ApiError, errorMessage } from '@/lib/api-client'
import { capitalize, formatDate, formatDateTime, ROLE_LABELS, timezones } from '@/lib/format'
import { cn } from '@/lib/utils'
import { useAuthStore, usePermissions } from '@/stores/auth-store'
import { useUiStore, type ThemePreference } from '@/stores/ui-store'

export default function SettingsLayout() {
  const { can } = usePermissions()
  const tabs = [
    { to: '/settings/profile', label: 'Profile', icon: UserRound },
    { to: '/settings/workspace', label: 'Workspace', icon: Building2 },
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
