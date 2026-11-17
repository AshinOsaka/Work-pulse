import { useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, Mail, Send, Sparkles } from 'lucide-react'
import { toast } from 'sonner'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from '@/components/ui/card'
import { Checkbox, Switch } from '@/components/ui/form-controls'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { SegmentedControl } from '@/components/ui/segmented-control'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { useAutoReportStatus, useSendTestReport, useUpdateCompany } from '@/features/settings/api'
import { AutoReportOverviewCard, ExtraRecipientsEditor } from '@/features/settings/auto-report-recipients'
import { errorMessage } from '@/lib/api-client'
import { formatDate } from '@/lib/format'
import { cn } from '@/lib/utils'
import { useAuthStore, usePermissions } from '@/stores/auth-store'
import type { AutoReports, ReportSection } from '@/types/api'

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
}

const SECTION_OPTIONS: { value: ReportSection; label: string; hint?: string }[] = [
  { value: 'summary', label: 'Written summary', hint: 'AI or automatic' },
  { value: 'start_time', label: 'Start time' },
  { value: 'active_idle', label: 'Active & idle time' },
  { value: 'categories', label: 'Productive / Neutral / Unproductive time' },
  { value: 'productive_share', label: 'Productive %' },
  { value: 'customer_time', label: 'Customer time', hint: 'CRM and other customer systems' },
  { value: 'top_apps', label: 'Top apps & websites' },
  { value: 'focus', label: 'Focus sessions' },
  { value: 'required_hours', label: 'Required hours met', hint: 'evening report' },
  { value: 'average', label: 'Compared with own 7-day average', hint: 'evening report' },
]

type Frequency = 'twice' | 'evening' | 'midday'
const frequencyOf = (f: AutoReports): Frequency =>
  f.midday_enabled && f.evening_enabled ? 'twice' : f.midday_enabled ? 'midday' : 'evening'

/** Minutes picker for the unproductive limits (keeps an unusual saved value selectable). */
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
const ALERT_MINUTES = [10, 15, 20, 30, 45, 60, 90, 120]

const same = (a: AutoReports, b: AutoReports) => JSON.stringify(a) === JSON.stringify(b)

/** Settings → Automatic reports: twice-daily digests to managers, and the unproductive-time alert. */
export function AutoReportsSettings() {
  const company = useAuthStore((s) => s.company)
  const { can } = usePermissions()
  const editable = can('POLICY_MANAGE')
  const update = useUpdateCompany()
  const status = useAutoReportStatus(editable)
  const sendTest = useSendTestReport()
  const saved = { ...DEFAULTS, ...company?.auto_reports }
  const [form, setForm] = useState<AutoReports>(saved)
  const queryClient = useQueryClient()
  if (!company) return null

  const set = (patch: Partial<AutoReports>) => setForm((f) => ({ ...f, ...patch }))
  const dirty = !same(form, saved)
  const timesOk = !(form.midday_enabled && form.evening_enabled) || form.midday_time < form.evening_time
  const alertsOk =
    !form.unproductive_alert_enabled || form.unproductive_total_enabled || form.unproductive_continuous_enabled
  const frequency = frequencyOf(form)
  const sectionsOk = form.sections.length > 0
  const toggleSection = (value: ReportSection, on: boolean) =>
    set({
      sections: SECTION_OPTIONS.map((o) => o.value).filter((v) =>
        v === value ? on : form.sections.includes(v),
      ),
    })
  const setFrequency = (value: Frequency) =>
    set({ midday_enabled: value !== 'evening', evening_enabled: value !== 'midday' })
  const save = () =>
    update.mutate(
      { auto_reports: form },
      {
        onSuccess: () => {
          toast.success('Automatic reports saved')
          void queryClient.invalidateQueries({ queryKey: ['auto-reports'] })
        },
      },
    )
  const test = (slot: 'midday' | 'evening') =>
    sendTest.mutate(slot, {
      onSuccess: (r) => toast.success(`Test report with ${r.people} people sent to ${r.sent_to}`),
      onError: (e) => toast.error(errorMessage(e)),
    })
  const ai = status.data?.ai_available
  const off = !editable || !form.enabled
  const alertOff = !editable || !form.unproductive_alert_enabled

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Mail className="size-4 text-muted-foreground" /> Automatic report e-mails
          </CardTitle>
          <CardDescription>
            Once or twice each working day: attendance, active and idle time, Productive / Neutral / Unproductive time,
            top apps and websites, and required hours. Each manager gets one e-mail for their team.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-5">
          {status.data && !status.data.email_ready && (
            <p className="flex items-center gap-2 rounded-md border border-warning/40 bg-warning-soft px-3 py-2 text-[13px] text-warning">
              <AlertTriangle className="size-4 shrink-0" /> E-mail isn&apos;t set up on this server, so reports can&apos;t be sent.
            </p>
          )}
          <label className={cn('flex w-fit items-center gap-2 text-[13px] font-medium', !editable && 'opacity-60')}>
            <Switch checked={form.enabled} onCheckedChange={(enabled) => set({ enabled })} disabled={!editable} />
            {form.enabled ? 'On' : 'Off'}
          </label>

          <div className="space-y-2">
            <Label>How often</Label>
            <div className={cn('w-fit', off && 'pointer-events-none opacity-60')} aria-disabled={off}>
            <SegmentedControl<Frequency>
              size="sm"
              label="How often"
              value={frequency}
              onChange={setFrequency}
              options={[
                { value: 'twice', label: 'Twice a day' },
                { value: 'evening', label: 'Once a day (evening)' },
                { value: 'midday', label: 'Once a day (mid-day)' },
              ]}
            />
            </div>
          </div>

          <div className="space-y-2">
            <Label>Send times</Label>
            <p className="text-[12px] text-muted-foreground">
              Working days only, in the workspace time zone ({company.timezone.replaceAll('_', ' ')}).
            </p>
            <div className="grid gap-2 sm:grid-cols-2">
              {form.midday_enabled && (
              <div className="rounded-md border px-3 py-2">
                <div className="flex items-center justify-between gap-2">
                  <span className="text-[13px] font-medium">Mid-day report</span>
                  <Input
                    type="time"
                    value={form.midday_time}
                    onChange={(e) => e.target.value && set({ midday_time: e.target.value })}
                    disabled={off}
                    className="h-8 w-28 text-[13px] tabular"
                    aria-label="Mid-day report time"
                  />
                </div>
                <p className="mt-1 text-[12px] text-muted-foreground">
                  {form.evening_enabled ? 'Covers the morning, until this time.' : 'Covers the day until this time.'}
                </p>
              </div>
              )}
              {form.evening_enabled && (
              <div className="rounded-md border px-3 py-2">
                <div className="flex items-center justify-between gap-2">
                  <span className="text-[13px] font-medium">Evening report</span>
                  <Input
                    type="time"
                    value={form.evening_time}
                    onChange={(e) => e.target.value && set({ evening_time: e.target.value })}
                    disabled={off}
                    className="h-8 w-28 text-[13px] tabular"
                    aria-label="Evening report time"
                  />
                </div>
                <p className="mt-1 text-[12px] text-muted-foreground">
                  {form.midday_enabled ? 'Covers the afternoon, plus the whole day.' : 'Covers the whole day.'}
                </p>
              </div>
              )}
            </div>
            {!timesOk && <p className="text-[12px] text-destructive">The mid-day time must be before the evening time.</p>}
          </div>

          <div className="space-y-2">
            <Label>Who receives them</Label>
            <div className="flex flex-wrap items-center gap-2">
              <label htmlFor="auto-reports-managers" className={cn('flex items-center gap-2 text-[13px]', off && 'opacity-60')}>
                <Checkbox
                  id="auto-reports-managers"
                  checked={form.send_to_managers}
                  onCheckedChange={(v) => set({ send_to_managers: v === true })}
                  disabled={off}
                />
                Send each person&apos;s report to their
              </label>
              <Select
                value={form.route_by}
                onValueChange={(v) => set({ route_by: v as AutoReports['route_by'] })}
                disabled={off || !form.send_to_managers}
              >
                <SelectTrigger size="sm" className="w-44" aria-label="Send each person's report to">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="manager">Manager</SelectItem>
                  <SelectItem value="department_head">Department head</SelectItem>
                  <SelectItem value="team_lead">Team lead</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <p className="text-[12px] text-muted-foreground">
              Each one gets only their own people, grouped by department. If that person isn&apos;t set, the manager
              (then the team lead) gets it. Unproductive alerts go to the same person.
            </p>
            <Label className="pt-1">Extra recipients</Label>
            <p className="text-[12px] text-muted-foreground">
              HR, a director and others. Each gets the departments and teams you choose (none chosen = everyone), for the
              reports you choose.
            </p>
            <ExtraRecipientsEditor
              value={form.extra_recipients}
              onChange={(extra_recipients) => set({ extra_recipients })}
              disabled={off}
            />
          </div>

          <div className="space-y-2">
            <Label>What to include</Label>
            <p className="text-[12px] text-muted-foreground">The employee&apos;s name is always shown.</p>
            <div className="grid gap-x-4 gap-y-2 sm:grid-cols-2 lg:grid-cols-3">
              {SECTION_OPTIONS.map((o) => (
                <label
                  key={o.value}
                  htmlFor={`section-${o.value}`}
                  className={cn('flex items-center gap-2 text-[13px]', off && 'opacity-60')}
                >
                  <Checkbox
                    id={`section-${o.value}`}
                    checked={form.sections.includes(o.value)}
                    onCheckedChange={(v) => toggleSection(o.value, v === true)}
                    disabled={off}
                  />
                  <span>
                    {o.label}
                    {o.hint && <span className="text-muted-foreground"> ({o.hint})</span>}
                  </span>
                </label>
              ))}
            </div>
            {!sectionsOk && <p className="text-[12px] text-destructive">Choose at least one thing to include.</p>}
          </div>

          <div className="space-y-2">
            <Label className="flex items-center gap-2">
              <Sparkles className="size-3.5 text-muted-foreground" /> AI summary
            </Label>
            <div className="flex flex-wrap items-center gap-3">
              <label htmlFor="auto-reports-ai" className={cn('flex items-center gap-2 text-[13px]', off && 'opacity-60')}>
                <Switch
                  id="auto-reports-ai"
                  checked={form.ai_summary && form.sections.includes('summary')}
                  onCheckedChange={(ai_summary) => set({ ai_summary })}
                  disabled={off || !form.sections.includes('summary')}
                />
                Write the summary with AI
              </label>
              {status.data &&
                (ai ? (
                  <Badge variant="success">AI ready</Badge>
                ) : (
                  <Badge variant="outline">No AI key on the server</Badge>
                ))}
            </div>
            <p className="text-[12px] text-muted-foreground">
              Only numbers and app/website names are sent to the AI — never names or e-mail addresses. Without AI, the
              summary is written from the numbers.
            </p>
          </div>
        </CardContent>
        {editable && (
          <CardFooter className="flex-wrap justify-between gap-2">
            <div className="flex flex-wrap gap-2">
              <Button type="button" size="sm" variant="outline" onClick={() => test('midday')} loading={sendTest.isPending && sendTest.variables === 'midday'}>
                <Send /> Test mid-day report
              </Button>
              <Button type="button" size="sm" variant="outline" onClick={() => test('evening')} loading={sendTest.isPending && sendTest.variables === 'evening'}>
                <Send /> Test evening report
              </Button>
            </div>
            <Button type="button" size="sm" onClick={save} disabled={!dirty || !timesOk || !alertsOk || !sectionsOk} loading={update.isPending}>
              Save
            </Button>
          </CardFooter>
        )}
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Unproductive time alert</CardTitle>
          <CardDescription>
            The employee and their manager get an e-mail, and an in-app alert is raised, within a few minutes of the
            time being recorded.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex flex-wrap items-center gap-3">
            <label className={cn('flex items-center gap-2 text-[13px] font-medium', !editable && 'opacity-60')}>
              <Switch
                checked={form.unproductive_alert_enabled}
                onCheckedChange={(unproductive_alert_enabled) => set({ unproductive_alert_enabled })}
                disabled={!editable}
              />
              {form.unproductive_alert_enabled ? 'On' : 'Off'}
            </label>
          </div>
          <div className="space-y-2">
            <div className="flex flex-wrap items-center gap-3 rounded-md border px-3 py-2">
              <label
                htmlFor="alert-total"
                className={cn('flex min-w-60 items-center gap-2 text-[13px]', alertOff && 'opacity-60')}
              >
                <Checkbox
                  id="alert-total"
                  checked={form.unproductive_total_enabled}
                  onCheckedChange={(v) => set({ unproductive_total_enabled: v === true })}
                  disabled={alertOff}
                />
                Daily total passes
              </label>
              <MinutesSelect
                value={form.unproductive_alert_minutes}
                onChange={(unproductive_alert_minutes) => set({ unproductive_alert_minutes })}
                disabled={alertOff || !form.unproductive_total_enabled}
                label="Daily total limit"
              />
              <span className="text-[12px] text-muted-foreground">once a day</span>
            </div>
            <div className="flex flex-wrap items-center gap-3 rounded-md border px-3 py-2">
              <label
                htmlFor="alert-continuous"
                className={cn('flex min-w-60 items-center gap-2 text-[13px]', alertOff && 'opacity-60')}
              >
                <Checkbox
                  id="alert-continuous"
                  checked={form.unproductive_continuous_enabled}
                  onCheckedChange={(v) => set({ unproductive_continuous_enabled: v === true })}
                  disabled={alertOff}
                />
                Continuously, without a break, for
              </label>
              <MinutesSelect
                value={form.unproductive_continuous_minutes}
                onChange={(unproductive_continuous_minutes) => set({ unproductive_continuous_minutes })}
                disabled={alertOff || !form.unproductive_continuous_enabled}
                label="Continuous limit"
              />
              <span className="text-[12px] text-muted-foreground">once per stretch</span>
            </div>
            {!alertsOk && <p className="text-[12px] text-destructive">Choose at least one alert.</p>}
          </div>
        </CardContent>
        {editable && (
          <CardFooter className="justify-end">
            <Button type="button" size="sm" onClick={save} disabled={!dirty || !timesOk || !alertsOk || !sectionsOk} loading={update.isPending}>
              Save
            </Button>
          </CardFooter>
        )}
      </Card>

      {editable && <AutoReportOverviewCard />}

      {editable && (status.data?.runs.length ?? 0) > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Recently sent</CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="divide-y text-[13px]">
              {status.data!.runs.map((r) => (
                <li key={`${r.day}-${r.slot}`} className="flex flex-wrap items-center gap-x-3 gap-y-1 py-2">
                  <span className="w-28 tabular">{formatDate(r.day)}</span>
                  <span className="w-24 text-muted-foreground">{r.slot === 'midday' ? 'Mid-day' : 'Evening'}</span>
                  {r.status === 'done' ? (
                    <span>
                      {r.sent ?? 0} e-mail{r.sent === 1 ? '' : 's'} · {r.people ?? 0} people
                      {r.failed ? <span className="text-destructive"> · {r.failed} failed</span> : null}
                      {r.ai ? <span className="text-muted-foreground"> · AI summary</span> : null}
                    </span>
                  ) : (
                    <Badge variant={r.status === 'failed' ? 'destructive' : 'outline'}>{r.status}</Badge>
                  )}
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
