import { BellRing, Clock, Laptop, ScrollText, ShieldCheck } from 'lucide-react'

import { FormAlert } from '@/components/common/form-field'
import { PersonAvatar } from '@/components/common/person'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { errorMessage } from '@/lib/api-client'
import type { LiveEmployee } from '@/types/api'

interface StartLiveDialogProps {
  target: LiveEmployee | null
  maxMinutes: number
  pending: boolean
  error: unknown
  onCancel: () => void
  onConfirm: (target: LiveEmployee) => void
}

function Point({ icon: Icon, children }: { icon: typeof Clock; children: React.ReactNode }) {
  return (
    <li className="flex gap-3 text-[13px]">
      <Icon className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden />
      <span>{children}</span>
    </li>
  )
}

/** Explicit confirmation before a live stream starts: who, what the employee sees, and the limits. */
export function StartLiveDialog({ target, maxMinutes, pending, error, onCancel, onConfirm }: StartLiveDialogProps) {
  const first = target?.employee.full_name.split(' ')[0] ?? ''
  return (
    <Dialog open={target !== null} onOpenChange={(open) => !open && onCancel()}>
      <DialogContent className="sm:max-w-md">
        {target && (
          <>
            <DialogHeader>
              <DialogTitle>Start Live Stream?</DialogTitle>
              <DialogDescription>Starting a live stream will create an audit record.</DialogDescription>
            </DialogHeader>
            <div className="flex items-center gap-3 rounded-lg border bg-subtle p-3">
              <PersonAvatar name={target.employee.full_name} seed={target.employee.id} className="size-10" />
              <dl className="grid min-w-0 flex-1 grid-cols-[auto_minmax(0,1fr)] gap-x-3 gap-y-0.5 text-[13px]">
                <dt className="text-muted-foreground">Employee</dt>
                <dd className="truncate font-medium">{target.employee.full_name}</dd>
                <dt className="text-muted-foreground">Device</dt>
                <dd className="flex min-w-0 items-center gap-1.5">
                  <Laptop className="size-3.5 shrink-0 text-muted-foreground" aria-hidden />
                  <span className="truncate">{target.device?.name ?? 'Desktop agent'}</span>
                </dd>
                <dt className="text-muted-foreground">Status</dt>
                <dd className="text-success">{target.presence === 'idle' ? 'Online · idle' : 'Online'}</dd>
              </dl>
            </div>
            <ul className="space-y-2.5">
              <Point icon={BellRing}>{first} is notified on their computer when the stream starts and ends, and sees your name.</Point>
              <Point icon={Clock}>
                The stream ends automatically after {maxMinutes} minutes, or as soon as {first} stops working.
              </Point>
              <Point icon={ScrollText}>Starting, connecting and ending the stream are recorded in the session timeline and the audit log.</Point>
              <Point icon={ShieldCheck}>Video goes directly from {first}'s computer to your browser and is not recorded.</Point>
            </ul>
            {error !== null && error !== undefined && <FormAlert>{errorMessage(error)}</FormAlert>}
            <DialogFooter>
              <Button variant="outline" onClick={onCancel} disabled={pending}>
                Cancel
              </Button>
              <Button onClick={() => onConfirm(target)} loading={pending}>
                Confirm &amp; Start Stream
              </Button>
            </DialogFooter>
          </>
        )}
      </DialogContent>
    </Dialog>
  )
}
