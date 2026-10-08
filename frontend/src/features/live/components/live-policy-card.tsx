import { useState } from 'react'
import { MonitorPlay } from 'lucide-react'
import { toast } from 'sonner'

import { FormAlert } from '@/components/common/form-field'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardAction, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from '@/components/ui/card'
import { Switch } from '@/components/ui/form-controls'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/misc'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { useLivePolicy, useUpdateLivePolicy } from '@/features/live/api'
import { errorMessage } from '@/lib/api-client'
import { usePermissions } from '@/stores/auth-store'
import type { LivePolicy } from '@/types/api'

const LENGTHS = [5, 10, 15, 30, 60, 120, 240]

function PolicyForm({ policy, editable }: { policy: LivePolicy; editable: boolean }) {
  const update = useUpdateLivePolicy()
  const [form, setForm] = useState(policy)
  const dirty = form.enabled !== policy.enabled || form.max_session_minutes !== policy.max_session_minutes
  return (
    <>
      <CardContent className="space-y-1">
        {update.error && <FormAlert>{errorMessage(update.error)}</FormAlert>}
        <div className="divide-y">
          <div className="flex items-start justify-between gap-6 py-3">
            <div className="space-y-0.5">
              <Label htmlFor="live-enabled">Allow live viewing</Label>
              <p className="text-[12px] text-muted-foreground">
                People with the View live screens permission can watch an employee's screen during a work session. Turning this off ends every stream in
                progress.
              </p>
            </div>
            <Switch id="live-enabled" checked={form.enabled} onCheckedChange={(v) => setForm({ ...form, enabled: v })} disabled={!editable} />
          </div>
          <div className="flex flex-col gap-2 py-3 sm:flex-row sm:items-start sm:justify-between sm:gap-6">
            <div className="space-y-0.5">
              <Label htmlFor="live-length">Maximum stream length</Label>
              <p className="text-[12px] text-muted-foreground">Streams end automatically after this time.</p>
            </div>
            <Select value={String(form.max_session_minutes)} onValueChange={(v) => setForm({ ...form, max_session_minutes: Number(v) })} disabled={!editable}>
              <SelectTrigger id="live-length" className="w-44">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {(LENGTHS.includes(form.max_session_minutes) ? LENGTHS : [form.max_session_minutes, ...LENGTHS]).map((m) => (
                  <SelectItem key={m} value={String(m)}>
                    {m < 60 ? `${m} minutes` : `${m / 60} hour${m === 60 ? '' : 's'}`}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>
        <p className="rounded-lg border bg-subtle px-4 py-3 text-[12px] text-muted-foreground">
          Always on, whatever the settings: the employee gets a notification with the viewer's name when a stream starts and ends, and the tray icon shows a red
          badge while they are watched. Streams are only possible during a work session, video goes peer to peer and is never recorded, and every stream is
          written to the audit log.
        </p>
      </CardContent>
      {editable && (
        <CardFooter className="justify-end">
          <Button
            size="sm"
            disabled={!dirty}
            loading={update.isPending}
            onClick={() =>
              update.mutate(form, {
                onSuccess: (saved) => {
                  setForm(saved)
                  toast.success('Live view policy updated')
                },
              })
            }
          >
            Save policy
          </Button>
        </CardFooter>
      )}
    </>
  )
}

export function LivePolicyCard() {
  const { can } = usePermissions()
  const query = useLivePolicy()
  const editable = can('POLICY_MANAGE')
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <MonitorPlay className="size-4 text-muted-foreground" aria-hidden /> Live screen viewing
        </CardTitle>
        <CardDescription>{editable ? 'On-demand live view of an employee’s screen.' : 'Only administrators can change this policy.'}</CardDescription>
        {query.data && (
          <CardAction>
            <Badge variant={query.data.enabled ? 'destructive' : 'secondary'}>
              {query.data.enabled ? `On · up to ${query.data.max_session_minutes} min` : 'Off'}
            </Badge>
          </CardAction>
        )}
      </CardHeader>
      {query.isError ? (
        <CardContent>
          <FormAlert>{errorMessage(query.error)}</FormAlert>
        </CardContent>
      ) : !query.data ? (
        <CardContent>
          <Skeleton className="h-10" />
        </CardContent>
      ) : (
        <PolicyForm key={JSON.stringify(query.data)} policy={query.data} editable={editable} />
      )}
    </Card>
  )
}
