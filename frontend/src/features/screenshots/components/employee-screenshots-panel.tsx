import { useState } from 'react'
import { ShieldCheck } from 'lucide-react'
import { toast } from 'sonner'

import { FormAlert } from '@/components/common/form-field'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/misc'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { useEmployeeScreenshotSettings, useUpdateEmployeeScreenshotSettings } from '@/features/screenshots/api'
import { ScreenshotGallery } from '@/features/screenshots/components/screenshot-gallery'
import { INTERVALS } from '@/features/screenshots/components/screenshot-policy-card'
import { scheduleSummary } from '@/features/screenshots/format'
import { errorMessage } from '@/lib/api-client'
import { usePermissions } from '@/stores/auth-store'
import type { EmployeeScreenshotSettings, ScreenshotMode } from '@/types/api'

const MODES: { value: ScreenshotMode; label: string }[] = [
  { value: 'inherit', label: 'Follow workspace policy' },
  { value: 'enabled', label: 'Always on (during work)' },
  { value: 'disabled', label: 'Off for this person' },
]
const DEFAULT_INTERVAL = '__default__'

function OverrideForm({ employeeId, settings }: { employeeId: string; settings: EmployeeScreenshotSettings }) {
  const update = useUpdateEmployeeScreenshotSettings(employeeId)
  const [mode, setMode] = useState(settings.mode)
  const [interval, setInterval] = useState<number | null>(settings.interval_minutes)
  const dirty = mode !== settings.mode || interval !== settings.interval_minutes
  return (
    <div className="space-y-3 border-t pt-4">
      {update.error && <FormAlert>{errorMessage(update.error)}</FormAlert>}
      <div className="flex flex-wrap items-end gap-3">
        <div className="space-y-1.5">
          <Label htmlFor="shot-mode">Screenshots for this person</Label>
          <Select value={mode} onValueChange={(v) => setMode(v as ScreenshotMode)}>
            <SelectTrigger id="shot-mode" className="w-60">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {MODES.map((m) => (
                <SelectItem key={m.value} value={m.value}>
                  {m.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        {mode !== 'disabled' && (
          <div className="space-y-1.5">
            <Label htmlFor="shot-interval">Frequency</Label>
            <Select
              value={interval === null ? DEFAULT_INTERVAL : String(interval)}
              onValueChange={(v) => setInterval(v === DEFAULT_INTERVAL ? null : Number(v))}
            >
              <SelectTrigger id="shot-interval" className="w-52">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={DEFAULT_INTERVAL}>Workspace default</SelectItem>
                {INTERVALS.map((m) => (
                  <SelectItem key={m} value={String(m)}>
                    {m === 1 ? 'Every minute' : `Every ${m} minutes`}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        )}
        <Button
          size="sm"
          disabled={!dirty}
          loading={update.isPending}
          onClick={() =>
            update.mutate(
              { mode, interval_minutes: mode === 'disabled' ? null : interval },
              { onSuccess: () => toast.success('Screenshot settings updated') },
            )
          }
        >
          Save
        </Button>
      </div>
    </div>
  )
}

function SettingsCard({ employeeId, firstName, isSelf }: { employeeId: string; firstName: string; isSelf: boolean }) {
  const { can } = usePermissions()
  const query = useEmployeeScreenshotSettings(employeeId)
  const settings = query.data
  const effective = settings?.effective
  return (
    <Card>
      <CardHeader>
        <CardTitle>{isSelf ? 'Your screenshot policy' : 'Screenshot policy'}</CardTitle>
        <CardDescription>
          {effective
            ? effective.source === 'employee'
              ? `Set individually for ${isSelf ? 'you' : firstName}.`
              : 'Follows the workspace policy.'
            : 'Loading…'}
        </CardDescription>
        {effective && (
          <CardAction>
            <Badge variant={effective.enabled ? 'destructive' : 'secondary'}>
              {effective.enabled ? 'Screenshots on' : 'Screenshots off'}
            </Badge>
          </CardAction>
        )}
      </CardHeader>
      <CardContent className="space-y-4">
        {query.isError ? (
          <FormAlert>{errorMessage(query.error)}</FormAlert>
        ) : !settings || !effective ? (
          <Skeleton className="h-10" />
        ) : (
          <>
            <dl className="grid gap-3 text-[13px] sm:grid-cols-3">
              <div>
                <dt className="text-muted-foreground">Schedule</dt>
                <dd className="font-medium">{scheduleSummary(effective)}</dd>
              </div>
              <div>
                <dt className="text-muted-foreground">Timezone</dt>
                <dd className="font-medium">{effective.timezone.replaceAll('_', ' ')}</dd>
              </div>
              <div>
                <dt className="text-muted-foreground">Kept for</dt>
                <dd className="font-medium">{effective.retention_days} days</dd>
              </div>
            </dl>
            {can('POLICY_MANAGE') && <OverrideForm key={JSON.stringify(settings)} employeeId={employeeId} settings={settings} />}
          </>
        )}
      </CardContent>
    </Card>
  )
}

export function EmployeeScreenshotsPanel({
  employeeId,
  firstName,
  isSelf,
}: {
  employeeId: string
  firstName: string
  isSelf: boolean
}) {
  const { can } = usePermissions()
  return (
    <div className="space-y-6">
      <SettingsCard employeeId={employeeId} firstName={firstName} isSelf={isSelf} />
      {can('SCREENSHOT_VIEW') ? (
        <ScreenshotGallery
          employeeId={employeeId}
          emptyDescription={`No screenshots of ${firstName} on this day. They are taken only during work sessions, when the policy allows.`}
        />
      ) : (
        <Card className="flex-row items-start gap-3 p-5 text-[13px] text-muted-foreground">
          <ShieldCheck className="mt-0.5 size-4 shrink-0 text-success" />
          <p>
            Screenshots can only be opened by authorised managers, and every view is recorded in the audit log. The
            WorkPulse tray icon shows a red badge whenever a screenshot can be taken.
          </p>
        </Card>
      )}
    </div>
  )
}
