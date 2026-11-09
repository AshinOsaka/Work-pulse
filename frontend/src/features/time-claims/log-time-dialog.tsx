import { useState, type FormEvent } from 'react'
import { toast } from 'sonner'

import { FormAlert, FormField } from '@/components/common/form-field'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Textarea } from '@/components/ui/form-controls'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { shiftDay, todayIn } from '@/features/activity/format'
import { useLogTime } from '@/features/time-claims/api'
import { KINDS, KIND_LABEL, formatMinutes } from '@/features/time-claims/meta'
import { ApiError, errorField, errorMessage } from '@/lib/api-client'
import { useAuthStore } from '@/stores/auth-store'
import type { TimeClaimKind } from '@/types/api'

function minutesBetween(start: string, end: string): number {
  if (!start || !end) return 0
  const [sh, sm] = start.split(':').map(Number)
  const [eh, em] = end.split(':').map(Number)
  return eh * 60 + em - (sh * 60 + sm)
}

/** Log time away from the computer: a meeting, client visit or call. */
export function LogTimeDialog({ autoMinutes, onOpenChange }: { autoMinutes: number; onOpenChange: (open: boolean) => void }) {
  const timeZone = useAuthStore((s) => s.company?.timezone ?? 'UTC')
  const today = todayIn(timeZone)
  const log = useLogTime()
  const [day, setDay] = useState(today)
  const [start, setStart] = useState('')
  const [end, setEnd] = useState('')
  const [kind, setKind] = useState<TimeClaimKind>('meeting')
  const [withWhom, setWithWhom] = useState('')
  const [note, setNote] = useState('')

  const minutes = minutesBetween(start, end)
  const badRange = Boolean(start && end) && minutes <= 0
  const fieldError = errorField(log.error)
  const validation = log.error instanceof ApiError ? log.error.fieldErrors : {}
  const errorFor = (field: string) => validation[field] ?? (fieldError?.field === field ? fieldError.message : undefined)
  const shownGeneral = log.error && !fieldError && !Object.keys(validation).length

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    try {
      const claim = await log.mutateAsync({ day, start_time: start, end_time: end, kind, with_whom: withWhom.trim(), note: note.trim() || null })
      toast.success(
        claim.status === 'approved'
          ? `${formatMinutes(claim.minutes)} logged and counted. Your manager has been told.`
          : `${formatMinutes(claim.minutes)} logged. It's over the daily limit, so it waits for your manager's approval.`,
      )
      onOpenChange(false)
    } catch (error) {
      if (!(error instanceof ApiError)) toast.error(errorMessage(error))
    }
  }

  return (
    <Dialog open onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <form onSubmit={submit} noValidate className="space-y-4">
          <DialogHeader>
            <DialogTitle>Log time away from the computer</DialogTitle>
            <DialogDescription>
              {autoMinutes > 0
                ? `Up to ${formatMinutes(autoMinutes)} a day counts straight away; more than that needs your manager's approval. Your manager is told either way.`
                : 'Your manager approves it before it counts. They are told straight away.'}
            </DialogDescription>
          </DialogHeader>
          {shownGeneral && <FormAlert>{errorMessage(log.error)}</FormAlert>}

          <div className="space-y-1.5">
            <Label htmlFor="claim-kind">What was it?</Label>
            <Select value={kind} onValueChange={(v) => setKind(v as TimeClaimKind)}>
              <SelectTrigger id="claim-kind" className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {KINDS.map((k) => (
                  <SelectItem key={k} value={k}>
                    {KIND_LABEL[k]}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="grid grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)_minmax(0,1fr)] gap-2">
            <div className="space-y-1.5">
              <Label htmlFor="claim-day">Date</Label>
              <Input id="claim-day" type="date" value={day} min={shiftDay(today, -7)} max={today} onChange={(e) => setDay(e.target.value)} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="claim-start">From</Label>
              <Input id="claim-start" type="time" value={start} onChange={(e) => setStart(e.target.value)} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="claim-end">To</Label>
              <Input id="claim-end" type="time" value={end} onChange={(e) => setEnd(e.target.value)} aria-invalid={badRange || undefined} />
            </div>
          </div>
          {(badRange || errorFor('day') || errorFor('start_time') || errorFor('end_time')) && (
            <p className="-mt-2 text-[12px] text-destructive" role="alert">
              {badRange ? 'The end time must be after the start time.' : (errorFor('day') ?? errorFor('start_time') ?? errorFor('end_time'))}
            </p>
          )}
          {minutes > 0 && !badRange && <p className="-mt-2 text-[12px] text-muted-foreground">{formatMinutes(minutes)}</p>}

          <FormField
            label="With whom"
            placeholder="e.g. ABC Company, or the design team"
            value={withWhom}
            onChange={(e) => setWithWhom(e.target.value)}
            error={errorFor('with_whom')}
            maxLength={120}
            required
          />
          <div className="space-y-1.5">
            <Label htmlFor="claim-note">Note (optional)</Label>
            <Textarea
              id="claim-note"
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="What it was about"
              className="min-h-16 text-[13px]"
              maxLength={500}
            />
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" loading={log.isPending} disabled={!day || !start || !end || badRange || !withWhom.trim()}>
              Log time
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
