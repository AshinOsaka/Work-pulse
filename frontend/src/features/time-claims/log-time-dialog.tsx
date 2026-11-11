import { useMemo, useState, type FormEvent } from 'react'
import { Search } from 'lucide-react'
import { toast } from 'sonner'

import { FormAlert, FormField } from '@/components/common/form-field'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Checkbox, Textarea } from '@/components/ui/form-controls'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { shiftDay, todayIn } from '@/features/activity/format'
import { useEmployeeOptions } from '@/features/people/api'
import { useEditClaim, useLogForTeam, useLogTime } from '@/features/time-claims/api'
import { KINDS, KIND_LABEL, formatMinutes } from '@/features/time-claims/meta'
import { ApiError, errorField, errorMessage } from '@/lib/api-client'
import { useAuthStore } from '@/stores/auth-store'
import type { TimeClaim, TimeClaimKind } from '@/types/api'

/** How far back people can log: their own time 7 days, a manager for their people 31 days. */
const OWN_DAYS = 7
const MANAGER_DAYS = 31

function minutesBetween(start: string, end: string): number {
  if (!start || !end) return 0
  const [sh, sm] = start.split(':').map(Number)
  const [eh, em] = end.split(':').map(Number)
  return eh * 60 + em - (sh * 60 + sm)
}

/** "HH:MM" of an instant in the workspace time zone (24-hour, as the time inputs expect). */
function clockIn(value: string, timeZone: string): string {
  return new Intl.DateTimeFormat('en-GB', { timeZone, hour: '2-digit', minute: '2-digit', hourCycle: 'h23' }).format(new Date(value))
}

type Mode =
  | { kind: 'self'; autoMinutes: number }
  | { kind: 'edit'; claim: TimeClaim; asManager: boolean }
  | { kind: 'team'; preselected?: string[] }

/** Log, change, or log-for-the-team time away from the computer: a meeting, client visit or call. */
export function LogTimeDialog({ mode, onOpenChange }: { mode: Mode; onOpenChange: (open: boolean) => void }) {
  const timeZone = useAuthStore((s) => s.company?.timezone ?? 'UTC')
  const today = todayIn(timeZone)
  const log = useLogTime()
  const edit = useEditClaim()
  const team = useLogForTeam()
  const mutation = mode.kind === 'self' ? log : mode.kind === 'edit' ? edit : team
  const editing = mode.kind === 'edit' ? mode.claim : null
  const [day, setDay] = useState(editing?.day ?? today)
  const [start, setStart] = useState(editing ? clockIn(editing.started_at, timeZone) : '')
  const [end, setEnd] = useState(editing ? clockIn(editing.ended_at, timeZone) : '')
  const [kind, setKind] = useState<TimeClaimKind>(editing?.kind ?? 'meeting')
  const [withWhom, setWithWhom] = useState(editing?.with_whom ?? '')
  const [note, setNote] = useState(editing?.note ?? '')
  const [people, setPeople] = useState<Set<string>>(() => new Set(mode.kind === 'team' ? (mode.preselected ?? []) : []))
  const [search, setSearch] = useState('')
  const options = useEmployeeOptions(mode.kind === 'team')
  const shown = useMemo(() => {
    const term = search.trim().toLowerCase()
    return (options.data ?? []).filter((p) => !term || p.full_name.toLowerCase().includes(term))
  }, [options.data, search])

  const daysBack = mode.kind === 'self' || (mode.kind === 'edit' && !mode.asManager) ? OWN_DAYS : MANAGER_DAYS
  const minutes = minutesBetween(start, end)
  const badRange = Boolean(start && end) && minutes <= 0
  const fieldError = errorField(mutation.error)
  const validation = mutation.error instanceof ApiError ? mutation.error.fieldErrors : {}
  const errorFor = (field: string) => validation[field] ?? (fieldError?.field === field ? fieldError.message : undefined)
  const shownGeneral = mutation.error && !fieldError && !Object.keys(validation).length
  const missingPeople = mode.kind === 'team' && people.size === 0

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    const input = { day, start_time: start, end_time: end, kind, with_whom: withWhom.trim(), note: note.trim() || null }
    try {
      if (mode.kind === 'self') {
        const claim = await log.mutateAsync(input)
        toast.success(
          claim.status === 'approved'
            ? `${formatMinutes(claim.minutes)} logged and counted. Your manager has been told.`
            : `${formatMinutes(claim.minutes)} logged. It's over the daily limit, so it waits for your manager's approval.`,
        )
      } else if (mode.kind === 'edit') {
        await edit.mutateAsync({ id: mode.claim.id, ...input, note: note.trim() })
        toast.success(mode.asManager ? `Changed. ${mode.claim.employee.name} has been told.` : 'Changed')
      } else {
        const result = await team.mutateAsync({ ...input, employee_ids: [...people] })
        if (result.created.length) toast.success(`${formatMinutes(minutes)} logged for ${result.created.length} ${result.created.length === 1 ? 'person' : 'people'}. They have been told.`)
        for (const skip of result.skipped) toast.warning(`${skip.employee.name}: not added — ${skip.reason.toLowerCase()}`)
      }
      onOpenChange(false)
    } catch (error) {
      if (!(error instanceof ApiError)) toast.error(errorMessage(error))
    }
  }

  const title =
    mode.kind === 'self' ? 'Log time away from the computer' : mode.kind === 'edit' ? `Change ${mode.asManager ? `${mode.claim.employee.name}'s` : 'logged'} time` : 'Log time for your team'
  const description =
    mode.kind === 'self'
      ? mode.autoMinutes > 0
        ? `Up to ${formatMinutes(mode.autoMinutes)} a day counts straight away; more than that needs your manager's approval. Your manager is told either way.`
        : 'Your manager approves it before it counts. They are told straight away.'
      : mode.kind === 'edit'
        ? mode.asManager
          ? 'They are told what changed. It keeps its current approval.'
          : 'It counts against your daily limit again, like a new entry.'
        : 'One meeting for several people: each of them gets it in their attendance, already approved, and is told.'

  return (
    <Dialog open onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[92vh] overflow-y-auto sm:max-w-md">
        <form onSubmit={submit} noValidate className="space-y-4">
          <DialogHeader>
            <DialogTitle>{title}</DialogTitle>
            <DialogDescription>{description}</DialogDescription>
          </DialogHeader>
          {shownGeneral && <FormAlert>{errorMessage(mutation.error)}</FormAlert>}

          {mode.kind === 'team' && (
            <div className="space-y-1.5">
              <Label htmlFor="team-search">People who attended</Label>
              <div className="relative">
                <Search className="absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
                <Input id="team-search" value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search your people" className="pl-8" />
              </div>
              <ul className="max-h-40 space-y-0.5 overflow-y-auto rounded-md border p-1.5">
                {shown.length === 0 && <li className="px-2 py-1.5 text-[12px] text-muted-foreground">No one matches.</li>}
                {shown.map((person) => (
                  <li key={person.id}>
                    <label htmlFor={`attendee-${person.id}`} className="flex cursor-pointer items-center gap-2 rounded px-2 py-1.5 text-[13px] hover:bg-accent">
                      <Checkbox
                        id={`attendee-${person.id}`}
                        checked={people.has(person.id)}
                        onCheckedChange={(v) =>
                          setPeople((current) => {
                            const next = new Set(current)
                            if (v === true) next.add(person.id)
                            else next.delete(person.id)
                            return next
                          })
                        }
                      />
                      {person.full_name}
                    </label>
                  </li>
                ))}
              </ul>
              <p className="text-[12px] text-muted-foreground">{people.size} selected</p>
            </div>
          )}

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
              <Input id="claim-day" type="date" value={day} min={shiftDay(today, -daysBack)} max={today} onChange={(e) => setDay(e.target.value)} />
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
            <Button type="submit" loading={mutation.isPending} disabled={!day || !start || !end || badRange || !withWhom.trim() || missingPeople}>
              {mode.kind === 'edit' ? 'Save changes' : mode.kind === 'team' ? `Log for ${people.size || ''} ${people.size === 1 ? 'person' : 'people'}`.replace('  ', ' ') : 'Log time'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
