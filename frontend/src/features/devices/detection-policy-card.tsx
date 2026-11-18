import { useState, type ReactNode } from 'react'
import { Bot, ShieldCheck, Usb, X } from 'lucide-react'
import { toast } from 'sonner'

import { FormAlert } from '@/components/common/form-field'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from '@/components/ui/card'
import { Switch } from '@/components/ui/form-controls'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/misc'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { useActivityPolicy, useUpdateActivityPolicy } from '@/features/activity/api'
import { KINDS } from '@/features/devices/device-log'
import { errorMessage } from '@/lib/api-client'
import { cn } from '@/lib/utils'
import { usePermissions } from '@/stores/auth-store'
import type { ActivityPolicy, DeviceKind } from '@/types/api'

type Fields = Pick<
  ActivityPolicy,
  | 'ignore_software_input'
  | 'detect_automation'
  | 'presence_check_minutes'
  | 'track_devices'
  | 'track_usb_files'
  | 'device_alert_kinds'
  | 'usb_file_alerts'
  | 'allowed_devices'
>

const pick = (p: ActivityPolicy): Fields => ({
  ignore_software_input: p.ignore_software_input,
  detect_automation: p.detect_automation,
  presence_check_minutes: p.presence_check_minutes,
  track_devices: p.track_devices,
  track_usb_files: p.track_usb_files,
  device_alert_kinds: p.device_alert_kinds,
  usb_file_alerts: p.usb_file_alerts,
  allowed_devices: p.allowed_devices,
})

function Row({ id, title, description, children, indent }: { id: string; title: string; description: ReactNode; children: ReactNode; indent?: boolean }) {
  return (
    <div className={cn('flex items-start justify-between gap-6 py-3', indent && 'pl-5')}>
      <div className="space-y-0.5">
        <Label htmlFor={id}>{title}</Label>
        <p className="text-[12px] text-muted-foreground">{description}</p>
      </div>
      {children}
    </div>
  )
}

function Section({ icon: Icon, title, children }: { icon: typeof Bot; title: string; children: ReactNode }) {
  return (
    <div>
      <p className="flex items-center gap-2 text-[12px] font-semibold tracking-wide text-muted-foreground uppercase">
        <Icon className="size-3.5" aria-hidden /> {title}
      </p>
      <div className="divide-y">{children}</div>
    </div>
  )
}

function Form({ policy, editable }: { policy: ActivityPolicy; editable: boolean }) {
  const update = useUpdateActivityPolicy()
  const [form, setForm] = useState<Fields>(pick(policy))
  const dirty = JSON.stringify(form) !== JSON.stringify(pick(policy))
  const set = (changes: Partial<Fields>) => setForm((f) => ({ ...f, ...changes }))
  const toggleKind = (kind: DeviceKind) =>
    set({ device_alert_kinds: form.device_alert_kinds.includes(kind) ? form.device_alert_kinds.filter((k) => k !== kind) : [...form.device_alert_kinds, kind] })

  const save = () =>
    update.mutate(form, {
      onSuccess: (saved) => {
        setForm(pick(saved))
        toast.success('Saved', { description: 'Computers pick up the change within a minute (WorkPulse 1.0.2 or later).' })
      },
    })

  return (
    <>
      <CardContent className="space-y-5">
        {update.error && <FormAlert>{errorMessage(update.error)}</FormAlert>}
        <Section icon={Bot} title="Mouse movers">
          <Row
            id="ignore-software"
            title="Don't count software-made input as active"
            description="Mouse-mover apps (Move Mouse, Caffeine…) fake mouse movement. With this on, that movement is ignored and the person shows as idle. Input from remote-control tools (AnyDesk, TeamViewer) also counts as idle."
          >
            <Switch id="ignore-software" checked={form.ignore_software_input} onCheckedChange={(v) => set({ ignore_software_input: v })} disabled={!editable} />
          </Row>
          <Row
            id="detect-automation"
            title="Check a mouse that moves by itself"
            description="A USB jiggler, or a mouse on a watch or fan, moves like a real mouse. If the mouse moves non-stop with no click, scroll or typing, WorkPulse asks “Are you still working?”. If nobody answers within 3 minutes, the manager gets an alert (and one screenshot is taken if screenshots are on). Mouse-mover apps are reported too."
          >
            <Switch id="detect-automation" checked={form.detect_automation} onCheckedChange={(v) => set({ detect_automation: v })} disabled={!editable} />
          </Row>
          {form.detect_automation && (
            <Row id="check-minutes" title="Ask after" description="Minutes of mouse-only movement before the question appears." indent>
              <Select value={String(form.presence_check_minutes)} onValueChange={(v) => set({ presence_check_minutes: Number(v) })} disabled={!editable}>
                <SelectTrigger id="check-minutes" size="sm" className="w-32">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {[10, 15, 20, 30, 45, 60].map((m) => (
                    <SelectItem key={m} value={String(m)}>
                      {m} minutes
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </Row>
          )}
        </Section>

        <Section icon={Usb} title="Devices & USB drives">
          <Row
            id="track-devices"
            title="Record devices plugged in"
            description="USB drives, phones, mice, keyboards, cameras and headsets: the employee, the computer, the device name and the time it was plugged in and removed. See them in Alerts → Devices & USB."
          >
            <Switch
              id="track-devices"
              checked={form.track_devices}
              onCheckedChange={(v) => set({ track_devices: v, track_usb_files: v && form.track_usb_files })}
              disabled={!editable}
            />
          </Row>
          <Row
            id="track-files"
            title="Record files copied with USB drives"
            description="File names and sizes copied to, deleted from or renamed on a USB drive, and files copied from it to Desktop, Documents or Downloads. No file is ever opened. Not visible: files sent by phone cable, e-mail or upload."
            indent
          >
            <Switch id="track-files" checked={form.track_usb_files} onCheckedChange={(v) => set({ track_usb_files: v })} disabled={!editable || !form.track_devices} />
          </Row>
          <div className="space-y-2 py-3">
            <Label>Alert when plugged in</Label>
            <p className="text-[12px] text-muted-foreground">The other types are only logged. A new mouse can be a mouse jiggler.</p>
            <div className="flex flex-wrap gap-1.5">
              {(Object.keys(KINDS) as DeviceKind[]).map((k) => {
                const on = form.device_alert_kinds.includes(k)
                const Icon = KINDS[k].icon
                return (
                  <button
                    key={k}
                    type="button"
                    disabled={!editable || !form.track_devices}
                    onClick={() => toggleKind(k)}
                    aria-pressed={on}
                    className={cn(
                      'inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-[12.5px] transition-colors disabled:opacity-50',
                      on ? 'border-primary/50 bg-primary-soft text-primary-soft-foreground' : 'text-muted-foreground hover:bg-subtle',
                    )}
                  >
                    <Icon className="size-3.5" aria-hidden /> {KINDS[k].plural}
                  </button>
                )
              })}
            </div>
          </div>
          <Row id="file-alerts" title="Alert when files are copied" description="One alert per copy, with the number of files, total size and the first file names." indent>
            <Switch id="file-alerts" checked={form.usb_file_alerts} onCheckedChange={(v) => set({ usb_file_alerts: v })} disabled={!editable || !form.track_usb_files} />
          </Row>
          <div className="space-y-2 py-3">
            <Label>Allowed devices</Label>
            <p className="text-[12px] text-muted-foreground">Known devices (an office headset, a company drive) are still logged but never alert. Add them with “Allow” in Alerts → Devices & USB.</p>
            {form.allowed_devices.length === 0 ? (
              <p className="text-[13px] text-muted-foreground">None yet.</p>
            ) : (
              <ul className="flex flex-wrap gap-1.5">
                {form.allowed_devices.map((d) => (
                  <li key={d.key}>
                    <Badge variant="secondary" className="gap-1 py-1 pr-1 text-[12px]">
                      <ShieldCheck /> {d.name || d.key}
                      {editable && (
                        <button
                          type="button"
                          className="rounded p-0.5 hover:bg-background"
                          aria-label={`Remove ${d.name}`}
                          onClick={() => set({ allowed_devices: form.allowed_devices.filter((x) => x.key !== d.key) })}
                        >
                          <X className="size-3" />
                        </button>
                      )}
                    </Badge>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </Section>
        <p className="rounded-md bg-subtle px-3 py-2 text-[12px] text-muted-foreground">
          Employees see all of this in their monitoring policy. Needs WorkPulse 1.0.2 or later on each computer.
        </p>
      </CardContent>
      {editable && (
        <CardFooter className="justify-end gap-2">
          {dirty && (
            <Button variant="ghost" size="sm" onClick={() => setForm(pick(policy))}>
              Discard
            </Button>
          )}
          <Button size="sm" disabled={!dirty} loading={update.isPending} onClick={save}>
            Save
          </Button>
        </CardFooter>
      )}
    </>
  )
}

/** Mouse movers, devices plugged in and USB file copies (workspace settings; everyone can read them). */
export function DetectionPolicyCard() {
  const { can } = usePermissions()
  const query = useActivityPolicy()
  const editable = can('POLICY_MANAGE')
  return (
    <Card>
      <CardHeader>
        <CardTitle>Devices &amp; automated input</CardTitle>
        <CardDescription>Stop mouse-mover tricks, and see USB drives, phones and other devices plugged into work computers.</CardDescription>
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
        <Form key={JSON.stringify(pick(query.data))} policy={query.data} editable={editable} />
      )}
    </Card>
  )
}
