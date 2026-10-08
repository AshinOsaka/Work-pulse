import { useState, type FormEvent } from 'react'
import { Check, Copy, KeyRound, Laptop, Plus, ShieldOff } from 'lucide-react'
import { toast } from 'sonner'

import { ConfirmDialog } from '@/components/common/confirm-dialog'
import { EmptyState } from '@/components/common/empty-state'
import { FormAlert, FormField } from '@/components/common/form-field'
import { StatusDot } from '@/components/common/status'
import { Button } from '@/components/ui/button'
import { Card, CardAction, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/misc'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { useEmployeeDevices, useRegisterDevice, useRevokeDevice } from '@/features/people/api'
import { DEVICE_OS, DEVICE_STATUS } from '@/features/people/meta'
import { ApiError, errorMessage } from '@/lib/api-client'
import { formatDate, formatDateTime } from '@/lib/format'
import type { Device, DeviceOs, DeviceRegistered, EmployeeDetail } from '@/types/api'

function RegisterDeviceDialog({
  employee,
  open,
  onOpenChange,
}: {
  employee: EmployeeDetail
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const register = useRegisterDevice(employee.id)
  const [form, setForm] = useState({ name: '', hostname: '', os: 'windows' as DeviceOs, os_version: '' })
  const [registered, setRegistered] = useState<DeviceRegistered | null>(null)
  const [copied, setCopied] = useState(false)
  const errors = register.error instanceof ApiError ? register.error.fieldErrors : {}

  const close = (next: boolean) => {
    if (!next) {
      setRegistered(null)
      setCopied(false)
      setForm({ name: '', hostname: '', os: 'windows', os_version: '' })
      register.reset()
    }
    onOpenChange(next)
  }

  const onSubmit = (event: FormEvent) => {
    event.preventDefault()
    register.mutate(
      {
        name: form.name.trim(),
        hostname: form.hostname.trim() || null,
        os: form.os,
        os_version: form.os_version.trim() || null,
      },
      { onSuccess: setRegistered },
    )
  }

  const copy = async () => {
    if (!registered) return
    try {
      await navigator.clipboard.writeText(registered.enrollment_code)
      setCopied(true)
    } catch {
      toast.error('Copy failed — select the code and copy it manually.')
    }
  }

  return (
    <Dialog open={open} onOpenChange={close}>
      <DialogContent className="sm:max-w-md">
        {registered ? (
          <>
            <DialogHeader>
              <DialogTitle>Device registered</DialogTitle>
              <DialogDescription>
                Enter this one-time code in the WorkPulse desktop agent on <strong>{registered.name}</strong>. It is
                shown only once and expires {formatDateTime(registered.enrollment_expires_at)}.
              </DialogDescription>
            </DialogHeader>
            <div className="flex items-center gap-2 rounded-lg border bg-subtle p-3">
              <KeyRound className="size-4 text-muted-foreground" />
              <code className="flex-1 font-mono text-base font-semibold tracking-widest select-all">
                {registered.enrollment_code}
              </code>
              <Button size="sm" variant="outline" onClick={copy}>
                {copied ? <Check /> : <Copy />} {copied ? 'Copied' : 'Copy'}
              </Button>
            </div>
            <p className="flex items-center gap-2 text-[12px] text-muted-foreground">
              Enter it in the WorkPulse desktop agent under <em>Sign in → Use an enrolment code instead</em>.
            </p>
            <DialogFooter>
              <Button onClick={() => close(false)}>Done</Button>
            </DialogFooter>
          </>
        ) : (
          <form onSubmit={onSubmit} className="space-y-4" noValidate>
            <DialogHeader>
              <DialogTitle>Register a device</DialogTitle>
              <DialogDescription>Add a computer used by {employee.full_name}.</DialogDescription>
            </DialogHeader>
            {register.error && !Object.keys(errors).length && <FormAlert>{errorMessage(register.error)}</FormAlert>}
            <FormField
              label="Device name"
              placeholder="e.g. Work laptop"
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              error={errors.name}
            />
            <FormField
              label="Hostname"
              placeholder="Optional, e.g. ACME-LT-042"
              value={form.hostname}
              onChange={(e) => setForm({ ...form, hostname: e.target.value })}
              error={errors.hostname}
            />
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label htmlFor="device-os">Operating system</Label>
                <Select value={form.os} onValueChange={(v) => setForm({ ...form, os: v as DeviceOs })}>
                  <SelectTrigger id="device-os">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {Object.entries(DEVICE_OS).map(([value, label]) => (
                      <SelectItem key={value} value={value}>
                        {label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <FormField
                label="Version"
                placeholder="e.g. 11 23H2"
                value={form.os_version}
                onChange={(e) => setForm({ ...form, os_version: e.target.value })}
                error={errors.os_version}
              />
            </div>
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => close(false)}>
                Cancel
              </Button>
              <Button type="submit" loading={register.isPending} disabled={form.name.trim().length < 2}>
                Register device
              </Button>
            </DialogFooter>
          </form>
        )}
      </DialogContent>
    </Dialog>
  )
}

export function DevicesPanel({ employee, canManage }: { employee: EmployeeDetail; canManage: boolean }) {
  const devices = useEmployeeDevices(employee.id)
  const revoke = useRevokeDevice()
  const [registerOpen, setRegisterOpen] = useState(false)
  const [revoking, setRevoking] = useState<Device | null>(null)
  const terminated = employee.status === 'terminated'

  return (
    <Card className="overflow-hidden">
      <CardHeader className="pb-4">
        <CardTitle>Devices</CardTitle>
        <CardDescription>Computers that will run the WorkPulse desktop agent.</CardDescription>
        {canManage && !terminated && (
          <CardAction>
            <Button size="sm" variant="outline" onClick={() => setRegisterOpen(true)}>
              <Plus /> Register device
            </Button>
          </CardAction>
        )}
      </CardHeader>
      {devices.isPending ? (
        <div className="space-y-2 px-5 pb-5">
          <Skeleton className="h-10" />
          <Skeleton className="h-10" />
        </div>
      ) : devices.data && devices.data.length > 0 ? (
        <Table>
          <TableHeader>
            <TableRow className="hover:bg-transparent">
              <TableHead className="pl-5">Device</TableHead>
              <TableHead>System</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Last seen</TableHead>
              {canManage && <TableHead className="w-12" />}
            </TableRow>
          </TableHeader>
          <TableBody>
            {devices.data.map((device) => (
              <TableRow key={device.id}>
                <TableCell className="pl-5">
                  <div className="flex items-center gap-3">
                    <div className="flex size-8 items-center justify-center rounded-md border bg-subtle text-muted-foreground">
                      <Laptop className="size-4" />
                    </div>
                    <div className="min-w-0">
                      <p className="truncate font-medium">{device.name}</p>
                      <p className="truncate font-mono text-[11px] text-muted-foreground">{device.hostname ?? '—'}</p>
                    </div>
                  </div>
                </TableCell>
                <TableCell className="text-muted-foreground">
                  {DEVICE_OS[device.os]} {device.os_version}
                </TableCell>
                <TableCell>
                  <span className="inline-flex items-center gap-1.5 whitespace-nowrap">
                    <StatusDot tone={DEVICE_STATUS[device.status].tone} />
                    {DEVICE_STATUS[device.status].label}
                  </span>
                  {device.status === 'pending' && device.enrollment_expires_at && (
                    <p className="text-[11px] text-muted-foreground">Code expires {formatDate(device.enrollment_expires_at)}</p>
                  )}
                </TableCell>
                <TableCell className="text-muted-foreground">
                  {device.last_seen_at ? formatDateTime(device.last_seen_at) : 'Never'}
                  {device.agent_version && <p className="text-[11px]">Agent {device.agent_version}</p>}
                </TableCell>
                {canManage && (
                  <TableCell>
                    {device.status !== 'revoked' && (
                      <Button size="icon-sm" variant="ghost" aria-label={`Revoke ${device.name}`} onClick={() => setRevoking(device)}>
                        <ShieldOff />
                      </Button>
                    )}
                  </TableCell>
                )}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      ) : (
        <EmptyState
          size="sm"
          icon={Laptop}
          title="No devices registered"
          description={
            canManage
              ? 'Register a device to generate an enrolment code for the desktop agent.'
              : 'Devices are registered by workspace administrators.'
          }
          className="border-t"
        />
      )}

      <RegisterDeviceDialog employee={employee} open={registerOpen} onOpenChange={setRegisterOpen} />
      <ConfirmDialog
        open={Boolean(revoking)}
        onOpenChange={(open) => !open && setRevoking(null)}
        title={`Revoke ${revoking?.name ?? 'device'}?`}
        description="The device's enrolment code stops working immediately. A revoked device cannot be re-activated; register it again if needed."
        confirmLabel="Revoke device"
        destructive
        loading={revoke.isPending}
        onConfirm={() =>
          revoking &&
          revoke.mutate(revoking.id, {
            onSuccess: () => {
              toast.success('Device revoked')
              setRevoking(null)
            },
            onError: (e) => toast.error(errorMessage(e)),
          })
        }
      />
    </Card>
  )
}
