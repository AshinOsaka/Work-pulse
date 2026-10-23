import { useState, type FormEvent } from 'react'
import { toast } from 'sonner'

import { FormAlert } from '@/components/common/form-field'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { useRaiseScreenshotRequest, useScreenshotMembers } from '@/features/screenshots/api'
import { errorMessage } from '@/lib/api-client'

export function RaiseRequestDialog({
  open,
  onOpenChange,
  defaultEmployeeId,
  defaultDay,
  today,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  defaultEmployeeId: string | null
  defaultDay: string
  today: string
}) {
  const members = useScreenshotMembers()
  const raise = useRaiseScreenshotRequest()
  const [employeeId, setEmployeeId] = useState(defaultEmployeeId ?? '')
  const [day, setDay] = useState(defaultDay)

  const submit = (event: FormEvent) => {
    event.preventDefault()
    if (!employeeId) return
    raise.mutate(
      { employee_id: employeeId, day },
      {
        onSuccess: () => {
          toast.success('Download requested — it will appear in Download Requests shortly.')
          onOpenChange(false)
        },
      },
    )
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <form onSubmit={submit} className="space-y-4">
          <DialogHeader>
            <DialogTitle>Request a screenshot download</DialogTitle>
            <DialogDescription>
              We&apos;ll package that person&apos;s screenshots for the chosen day into a ZIP you can download.
            </DialogDescription>
          </DialogHeader>
          {raise.error && <FormAlert>{errorMessage(raise.error)}</FormAlert>}
          <div className="space-y-1.5">
            <Label htmlFor="request-member">Member</Label>
            <Select value={employeeId} onValueChange={setEmployeeId}>
              <SelectTrigger id="request-member">
                <SelectValue placeholder="Choose a person" />
              </SelectTrigger>
              <SelectContent className="max-h-72">
                {(members.data ?? []).map((m) => (
                  <SelectItem key={m.employee.id} value={m.employee.id}>
                    {m.employee.full_name} · {m.employee.email}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="request-day">Date</Label>
            <Input
              id="request-day"
              type="date"
              value={day}
              max={today}
              onChange={(e) => e.target.value && setDay(e.target.value)}
            />
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" loading={raise.isPending} disabled={!employeeId}>
              Raise request
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
