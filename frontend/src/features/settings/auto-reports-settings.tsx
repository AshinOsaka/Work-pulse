import { useState, type ReactNode } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, Hourglass, Mail, Send, Sparkles } from 'lucide-react'
import { toast } from 'sonner'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardAction, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from '@/components/ui/card'
import { Checkbox, Switch } from '@/components/ui/form-controls'
import { Input } from '@/components/ui/input'
import { SegmentedControl } from '@/components/ui/segmented-control'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { useAutoReportStatus, useSendTestReport, useUpdateCompany } from '@/features/settings/api'
import { AutoReportOverviewCard, ExtraRecipientsEditor } from '@/features/settings/auto-report-recipients'
import { EmployeeReportsCard } from '@/features/settings/employee-reports'
import { ContentChips } from '@/features/settings/report-content'
import { UnproductiveHistory } from '@/features/settings/unproductive-history'
import { errorMessage } from '@/lib/api-client'
import { cn } from '@/lib/utils'
import { useAuthStore, usePermissions } from '@/stores/auth-store'
import type { AutoReports } from '@/types/api'

const DEFAULTS: AutoReports = {
  enabled: false,
  midday_enabled: true,
  evening_enabled: true,
  midday_time: '13:30',
  evening_time: '18:30',
  send_to_managers: true,
  route_by: 'manager',
  extra_recipients: [],
  sections: ['summary', 'start_time', 'active_idle', 'categories', 'productive_share', 'customer_time', 'top_apps', 'focus', 'required_hours', 'average'],
  ai_summary: true,
  unproductive_alert_enabled: false,
  unproductive_total_enabled: true,
  unproductive_alert_minutes: 20,
  unproductive_continuous_enabled: false,
  unproductive_continuous_minutes: 20,
  employee_reports_enabled: false,
  employee_midday: true,
  employee_evening: true,
  employee_sections: ['start_time', 'active_idle', 'categories', 'productive_share', 'top_apps', 'required_hours'],
  employee_settings: [],
}


const ALERT_MINUTES = [10, 15, 20, 30, 45, 60, 90, 120]

type Frequency = 'twice' | 'evening' | 'midday'
const frequencyOf = (f: AutoReports): Frequency =>
  f.midday_enabled && f.evening_enabled ? 'twice' : f.midday_enabled ? 'midday' : 'evening'

/** "Route" choice, with "off" standing for not e-mailing the reporting line at all. */
type Route = AutoReports['route_by'] | 'off'

const same = (a: AutoReports, b: AutoReports) => JSON.stringify(a) === JSON.stringify(b)

/** One setting: a short label (and hint) on the left, its control on the right. */
function Row({ title, hint, children }: { title: string; hint?: string; children: ReactNode }) {
  return (
    <div className="grid gap-3 py-4 first:pt-1 last:pb-1 sm:grid-cols-[13rem_minmax(0,1fr)] sm:gap-6">
      <div>
        <p className="text-[13px] font-medium">{title}</p>
        {hint && <p className="mt-0.5 text-[12px] text-muted-foreground">{hint}</p>}
      </div>
      <div className="min-w-0">{children}</div>
    </div>
  )
}

function MinutesSelect({
  value,
  onChange,
  disabled,
  label,
}: {
  value: number
  onChange: (minutes: number) => void
  disabled: boolean
  label: string
}) {
  const options = ALERT_MINUTES.includes(value) ? ALERT_MINUTES : [...ALERT_MINUTES, value].sort((a, b) => a - b)
  return (
    <Select value={String(value)} onValueChange={(v) => onChange(Number(v))} disabled={disabled}>
      <SelectTrigger size="sm" className="w-28" aria-label={label}>
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {options.map((m) => (
          <SelectItem key={m} value={String(m)}>
            {m < 60 ? `${m} min` : `${m / 60} hour${m > 60 ? 's' : ''}`}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}

function TimeField({ label, value, onChange, disabled }: { label: string; value: string; onChange: (v: string) => void; disabled: boolean }) {
  return (
    <label className={cn('flex items-center gap-2 text-[12px] text-muted-foreground', disabled && 'opacity-60')}>
      {label}
      <Input
        type="time"
        value={value}
        onChange={(e) => e.target.value && onChange(e.target.value)}
        disabled={disabled}
        className="h-8 w-28 text-[13px] text-foreground tabular"
        aria-label={`${label} time`}
      />
    </label>
  )
}

/** Settings → Automatic reports: daily report e-mails, the unproductive-time alert, and who gets what. */
export function AutoReportsSettings() {
  const company = useAuthStore((s) => s.company)
  const { can } = usePermissions()
  const editable = can('POLICY_MANAGE')
  const update = useUpdateCompany()
  const status = useAutoReportStatus(editable)
  const sendTest = useSendTestReport()
  const queryClient = useQueryClient()
  const saved = { ...DEFAULTS, ...company?.auto_reports }
  const [form, setForm] = useState<AutoReports>(saved)
  if (!company) return null

  const set = (patch: Partial<AutoReports>) => setForm((f) => ({ ...f, ...patch }))
  const dirty = !same(form, saved)
  const timesOk = !(form.midday_enabled && form.evening_enabled) || form.midday_time < form.evening_time
  const alertsOk = !form.unproductive_alert_enabled || form.unproductive_total_enabled || form.unproductive_continuous_enabled
  const sectionsOk = form.sections.length > 0
  const employeesOk = !form.employee_reports_enabled || ((form.employee_midday || form.employee_evening) && form.employee_sections.length > 0)
  const valid = timesOk && alertsOk && sectionsOk && employeesOk
  const off = !editable || !form.enabled
  const alertOff = !editable || !form.unproductive_alert_enabled
  const route: Route = form.send_to_managers ? form.route_by : 'off'
  const hasSummary = form.sections.includes('summary')

  const save = () =>
    update.mutate(
      { auto_reports: form },
      {
        onSuccess: () => {
          toast.success('Saved')
          void queryClient.invalidateQueries({ queryKey: ['auto-reports'] })
        },
      },
    )
  const test = (slot: 'midday' | 'evening') =>
    sendTest.mutate(slot, {
      onSuccess: (r) => toast.success(`Test sent to ${r.sent_to} (${r.people} people)`),
      onError: (e) => toast.error(errorMessage(e)),
    })

  return (
    <div className="space-y-6 pb-4">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2.5">
            <span className="flex size-8 items-center justify-center rounded-lg bg-primary-soft text-primary">
              <Mail className="size-4" />
            </span>
            Report e-mails
          </CardTitle>
          <CardDescription>Daily activity reports for managers and HR.</CardDescription>
          <CardAction>
            <Switch checked={form.enabled} onCheckedChange={(enabled) => set({ enabled })} disabled={!editable} aria-label="Report e-mails" />
          </CardAction>
        </CardHeader>
        <CardContent>
          {status.data && !status.data.email_ready && (
            <p className="mb-3 flex items-center gap-2 rounded-md border border-warning/40 bg-warning-soft px-3 py-2 text-[13px] text-warning">
              <AlertTriangle className="size-4 shrink-0" /> E-mail isn&apos;t set up on this server.
            </p>
          )}
          <div className={cn('divide-y', !form.enabled && 'opacity-70')}>
            <Row title="Schedule" hint={`Working days · ${company.timezone.replaceAll('_', ' ')}`}>
              <div className="flex flex-wrap items-center gap-3">
                <div className={cn(off && 'pointer-events-none opacity-60')} aria-disabled={off}>
                  <SegmentedControl<Frequency>
                    size="sm"
                    label="Frequency"
                    value={frequencyOf(form)}
                    onChange={(v) => set({ midday_enabled: v !== 'evening', evening_enabled: v !== 'midday' })}
                    options={[
                      { value: 'twice', label: 'Twice daily' },
                      { value: 'evening', label: 'Evening' },
                      { value: 'midday', label: 'Mid-day' },
                    ]}
                  />
                </div>
                {form.midday_enabled && <TimeField label="Mid-day" value={form.midday_time} onChange={(midday_time) => set({ midday_time })} disabled={off} />}
                {form.evening_enabled && <TimeField label="Evening" value={form.evening_time} onChange={(evening_time) => set({ evening_time })} disabled={off} />}
              </div>
              {!timesOk && <p className="mt-2 text-[12px] text-destructive">Mid-day must be before evening.</p>}
            </Row>

            <Row title="Reporting line" hint="Each gets only their own people">
              <Select
                value={route}
                onValueChange={(v) =>
                  v === 'off' ? set({ send_to_managers: false }) : set({ send_to_managers: true, route_by: v as AutoReports['route_by'] })
                }
                disabled={off}
              >
                <SelectTrigger size="sm" className="w-48" aria-label="Reporting line">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="manager">Manager</SelectItem>
                  <SelectItem value="department_head">Department head</SelectItem>
                  <SelectItem value="team_lead">Team lead</SelectItem>
                  <SelectItem value="off">Don&apos;t send</SelectItem>
                </SelectContent>
              </Select>
            </Row>

            <Row title="Extra recipients" hint="HR, directors · by department or team">
              <ExtraRecipientsEditor value={form.extra_recipients} onChange={(extra_recipients) => set({ extra_recipients })} disabled={off} />
            </Row>

            <Row title="Content" hint="Tap to add or remove · name always shown">
              <ContentChips value={form.sections} onChange={(sections) => set({ sections })} disabled={off} />
              {!sectionsOk && <p className="mt-2 text-[12px] text-destructive">Choose at least one.</p>}
            </Row>

            <Row title="AI summary" hint="Numbers only, never names">
              <div className="flex flex-wrap items-center gap-3">
                <Switch
                  checked={form.ai_summary && hasSummary}
                  onCheckedChange={(ai_summary) => set({ ai_summary })}
                  disabled={off || !hasSummary}
                  aria-label="AI summary"
                />
                {status.data && (ai(status.data.ai_available))}
              </div>
            </Row>
          </div>
        </CardContent>
        {editable && (
          <CardFooter className="flex-wrap gap-2">
            <span className="mr-1 text-[12px] text-muted-foreground">Send a test to yourself</span>
            <Button type="button" size="sm" variant="outline" onClick={() => test('midday')} loading={sendTest.isPending && sendTest.variables === 'midday'}>
              <Send /> Mid-day
            </Button>
            <Button type="button" size="sm" variant="outline" onClick={() => test('evening')} loading={sendTest.isPending && sendTest.variables === 'evening'}>
              <Send /> Evening
            </Button>
          </CardFooter>
        )}
      </Card>

      <EmployeeReportsCard form={form} set={set} editable={editable} />

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2.5">
            <span className="flex size-8 items-center justify-center rounded-lg bg-warning-soft text-warning">
              <Hourglass className="size-4" />
            </span>
            Unproductive alert
          </CardTitle>
          <CardDescription>E-mail to the employee and their manager, plus an in-app alert.</CardDescription>
          <CardAction>
            <Switch
              checked={form.unproductive_alert_enabled}
              onCheckedChange={(unproductive_alert_enabled) => set({ unproductive_alert_enabled })}
              disabled={!editable}
              aria-label="Unproductive alert"
            />
          </CardAction>
        </CardHeader>
        <CardContent>
          <div className={cn('divide-y', !form.unproductive_alert_enabled && 'opacity-70')}>
            <Row title="Daily total" hint="Once a day">
              <div className="flex items-center gap-3">
                <Checkbox
                  checked={form.unproductive_total_enabled}
                  onCheckedChange={(v) => set({ unproductive_total_enabled: v === true })}
                  disabled={alertOff}
                  aria-label="Daily total alert"
                />
                <span className={cn('text-[13px]', alertOff && 'opacity-60')}>More than</span>
                <MinutesSelect
                  value={form.unproductive_alert_minutes}
                  onChange={(unproductive_alert_minutes) => set({ unproductive_alert_minutes })}
                  disabled={alertOff || !form.unproductive_total_enabled}
                  label="Daily total limit"
                />
              </div>
            </Row>
            <Row title="Without a break" hint="Once per stretch">
              <div className="flex items-center gap-3">
                <Checkbox
                  checked={form.unproductive_continuous_enabled}
                  onCheckedChange={(v) => set({ unproductive_continuous_enabled: v === true })}
                  disabled={alertOff}
                  aria-label="Continuous alert"
                />
                <span className={cn('text-[13px]', alertOff && 'opacity-60')}>Longer than</span>
                <MinutesSelect
                  value={form.unproductive_continuous_minutes}
                  onChange={(unproductive_continuous_minutes) => set({ unproductive_continuous_minutes })}
                  disabled={alertOff || !form.unproductive_continuous_enabled}
                  label="Continuous limit"
                />
              </div>
            </Row>
          </div>
          {!alertsOk && <p className="mt-2 text-[12px] text-destructive">Choose at least one alert.</p>}
          {editable && (
            <div className="mt-4">
              <UnproductiveHistory />
            </div>
          )}
        </CardContent>
      </Card>

      {editable && <AutoReportOverviewCard runs={status.data?.runs ?? []} />}

      {editable && dirty && (
        <div className="sticky bottom-4 z-20 flex items-center justify-between gap-3 rounded-xl border bg-card px-4 py-3 shadow-elevated">
          <span className="text-[13px] text-muted-foreground">Unsaved changes</span>
          <div className="flex gap-2">
            <Button type="button" size="sm" variant="ghost" onClick={() => setForm(saved)}>
              Discard
            </Button>
            <Button type="button" size="sm" onClick={save} disabled={!valid} loading={update.isPending}>
              Save changes
            </Button>
          </div>
        </div>
      )}
    </div>
  )
}

function ai(available: boolean) {
  return available ? (
    <Badge variant="success">
      <Sparkles /> AI ready
    </Badge>
  ) : (
    <Badge variant="outline">No AI key · summary from numbers</Badge>
  )
}
