import { useState, type FormEvent, type ReactNode } from 'react'
import { Camera } from 'lucide-react'
import { toast } from 'sonner'

import { FormAlert } from '@/components/common/form-field'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardAction, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from '@/components/ui/card'
import { Switch } from '@/components/ui/form-controls'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/misc'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { useScreenshotPolicy, useUpdateScreenshotPolicy } from '@/features/screenshots/api'
import { scheduleSummary, WEEKDAYS } from '@/features/screenshots/format'
import { errorMessage } from '@/lib/api-client'
import { cn } from '@/lib/utils'
import { usePermissions } from '@/stores/auth-store'
import type { ScreenshotPolicy } from '@/types/api'

export const INTERVALS = [1, 2, 5, 10, 15, 20, 30, 60]
const RETENTION = [7, 14, 30, 60, 90, 180, 365]

function Row({ id, title, description, children }: { id: string; title: string; description: ReactNode; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-2 py-3 sm:flex-row sm:items-start sm:justify-between sm:gap-6">
      <div className="space-y-0.5">
        <Label htmlFor={id}>{title}</Label>
        <p className="text-[12px] text-muted-foreground">{description}</p>
      </div>
      <div className="shrink-0">{children}</div>
    </div>
  )
}

function PolicyForm({ policy, editable }: { policy: ScreenshotPolicy; editable: boolean }) {
  const update = useUpdateScreenshotPolicy()
  const [form, setForm] = useState(policy)
  const dirty = JSON.stringify(form) !== JSON.stringify(policy)
  const hoursInvalid = form.work_hours_only && form.work_start === form.work_end
  const disabled = !editable

  const toggleDay = (day: number) => {
    const days = form.work_days.includes(day) ? form.work_days.filter((d) => d !== day) : [...form.work_days, day]
    if (days.length) setForm({ ...form, work_days: days.sort((a, b) => a - b) })
  }

  const onSubmit = (event: FormEvent) => {
    event.preventDefault()
    const retentionShrinks = form.retention_days < policy.retention_days
    update.mutate(form, {
      onSuccess: (saved) => {
        setForm(saved)
        toast.success('Screenshot policy updated', {
          description: retentionShrinks
            ? `Screenshots older than ${saved.retention_days} days will be deleted shortly.`
            : 'Desktop agents pick up the change within a minute.',
        })
      },
    })
  }

  return (
    <form onSubmit={onSubmit} noValidate>
      <CardContent className="space-y-1">
        {update.error && <FormAlert>{errorMessage(update.error)}</FormAlert>}
        <div className="divide-y">
          <Row
            id="screenshots-enabled"
            title="Capture screenshots"
            description="Employees see a red badge on the WorkPulse tray icon, and a notice in the web app, whenever screenshots can be taken."
          >
            <Switch
              id="screenshots-enabled"
              checked={form.enabled}
              onCheckedChange={(v) => setForm({ ...form, enabled: v })}
              disabled={disabled}
            />
          </Row>
          <Row
            id="screenshots-interval"
            title="Frequency"
            description="One screenshot at a random moment within each interval, only during an active work session."
          >
            <Select
              value={String(form.interval_minutes)}
              onValueChange={(v) => setForm({ ...form, interval_minutes: Number(v) })}
              disabled={disabled}
            >
              <SelectTrigger id="screenshots-interval" className="w-44">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {(INTERVALS.includes(form.interval_minutes) ? INTERVALS : [form.interval_minutes, ...INTERVALS]).map((m) => (
                  <SelectItem key={m} value={String(m)}>
                    {m === 1 ? 'Every minute' : `Every ${m} minutes`}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Row>
          <Row
            id="screenshots-hours"
            title="Working hours only"
            description="Never capture outside these hours, in each employee's own timezone."
          >
            <Switch
              id="screenshots-hours"
              checked={form.work_hours_only}
              onCheckedChange={(v) => setForm({ ...form, work_hours_only: v })}
              disabled={disabled}
            />
          </Row>
          {form.work_hours_only && (
            <div className="space-y-3 py-3">
              <div className="flex flex-wrap items-end gap-3">
                <div className="space-y-1.5">
                  <Label htmlFor="work-start">From</Label>
                  <Input
                    id="work-start"
                    type="time"
                    value={form.work_start}
                    onChange={(e) => e.target.value && setForm({ ...form, work_start: e.target.value })}
                    disabled={disabled}
                    className="w-32"
                    aria-invalid={hoursInvalid || undefined}
                  />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="work-end">Until</Label>
                  <Input
                    id="work-end"
                    type="time"
                    value={form.work_end}
                    onChange={(e) => e.target.value && setForm({ ...form, work_end: e.target.value })}
                    disabled={disabled}
                    className="w-32"
                    aria-invalid={hoursInvalid || undefined}
                  />
                </div>
                {form.work_end < form.work_start && (
                  <p className="pb-2 text-[12px] text-muted-foreground">Overnight: ends the next morning.</p>
                )}
              </div>
              {hoursInvalid && <p className="text-[12px] text-destructive">Start and end must differ.</p>}
              <fieldset>
                <legend className="mb-1.5 text-[13px] font-medium">Working days</legend>
                <div className="flex flex-wrap gap-1.5">
                  {WEEKDAYS.map((day) => {
                    const on = form.work_days.includes(day.value)
                    return (
                      <button
                        key={day.value}
                        type="button"
                        aria-pressed={on}
                        aria-label={day.long}
                        disabled={disabled}
                        onClick={() => toggleDay(day.value)}
                        className={cn(
                          'h-8 w-11 rounded-md border text-[12px] font-medium transition outline-none focus-visible:ring-[3px] focus-visible:ring-ring/40 disabled:opacity-60',
                          on ? 'border-primary bg-primary-soft text-primary-soft-foreground' : 'bg-card text-muted-foreground hover:text-foreground',
                        )}
                      >
                        {day.short}
                      </button>
                    )
                  })}
                </div>
              </fieldset>
            </div>
          )}
          <Row
            id="screenshots-retention"
            title="Keep screenshots for"
            description="Deleted automatically afterwards. Shortening this also deletes older screenshots already stored."
          >
            <Select
              value={String(form.retention_days)}
              onValueChange={(v) => setForm({ ...form, retention_days: Number(v) })}
              disabled={disabled}
            >
              <SelectTrigger id="screenshots-retention" className="w-44">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {(RETENTION.includes(form.retention_days) ? RETENTION : [form.retention_days, ...RETENTION]).map((d) => (
                  <SelectItem key={d} value={String(d)}>
                    {d === 365 ? '1 year' : `${d} days`}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Row>
        </div>
        <p className="rounded-lg border bg-subtle px-4 py-3 text-[12px] text-muted-foreground">
          Screenshots are encrypted at rest and never available through public links. Only people with the{' '}
          <span className="font-medium text-foreground">View screenshots</span> permission can open them, and only for
          employees they manage. Every view is recorded in the audit log. No capture is taken while a password
          manager, private browsing window, messaging or e-mail app is in front.
        </p>
      </CardContent>
      {editable && (
        <CardFooter className="justify-end">
          <Button type="submit" size="sm" disabled={!dirty || hoursInvalid} loading={update.isPending}>
            Save policy
          </Button>
        </CardFooter>
      )}
    </form>
  )
}

/** Workspace screenshot policy: everyone can read it (transparency); administrators can change it. */
export function ScreenshotPolicyCard() {
  const { can } = usePermissions()
  const query = useScreenshotPolicy()
  const editable = can('POLICY_MANAGE')
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Camera className="size-4 text-muted-foreground" aria-hidden /> Screenshots
        </CardTitle>
        <CardDescription>
          {editable ? 'Periodic screenshots during work sessions.' : 'Only administrators can change this policy.'}
        </CardDescription>
        {query.data && (
          <CardAction>
            <Badge variant={query.data.enabled ? 'destructive' : 'secondary'}>{scheduleSummary(query.data)}</Badge>
          </CardAction>
        )}
      </CardHeader>
      {query.isError ? (
        <CardContent>
          <FormAlert>{errorMessage(query.error)}</FormAlert>
        </CardContent>
      ) : !query.data ? (
        <CardContent className="space-y-3">
          <Skeleton className="h-10" />
          <Skeleton className="h-10" />
        </CardContent>
      ) : (
        <PolicyForm key={JSON.stringify(query.data)} policy={query.data} editable={editable} />
      )}
    </Card>
  )
}
