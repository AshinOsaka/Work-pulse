import { useState, type FormEvent } from 'react'
import { toast } from 'sonner'

import { FormAlert, FormField } from '@/components/common/form-field'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Textarea } from '@/components/ui/form-controls'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useCreateMilestone, useUpdateMilestone } from '@/features/work/api'
import { ApiError, errorMessage } from '@/lib/api-client'
import type { Milestone } from '@/types/api'

/** Create a milestone in a project, or edit one. */
export function MilestoneDialog({
  projectId,
  milestone,
  onOpenChange,
}: {
  projectId: string
  milestone?: Milestone
  onOpenChange: (open: boolean) => void
}) {
  const create = useCreateMilestone()
  const update = useUpdateMilestone()
  const mutation = milestone ? update : create
  const [name, setName] = useState(milestone?.name ?? '')
  const [due, setDue] = useState(milestone?.due_date ?? '')
  const [description, setDescription] = useState(milestone?.description ?? '')
  const errors = mutation.error instanceof ApiError ? mutation.error.fieldErrors : {}

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    const input = { name: name.trim(), due_date: due || null, description: description.trim() || null }
    try {
      if (milestone) await update.mutateAsync({ id: milestone.id, ...input })
      else await create.mutateAsync({ projectId, ...input })
      toast.success(milestone ? 'Milestone updated' : `${input.name} added`)
      onOpenChange(false)
    } catch (error) {
      if (!(error instanceof ApiError) || !Object.keys(error.fieldErrors).length) toast.error(errorMessage(error))
    }
  }

  return (
    <Dialog open onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <form onSubmit={submit} noValidate className="space-y-4">
          <DialogHeader>
            <DialogTitle>{milestone ? 'Edit milestone' : 'New milestone'}</DialogTitle>
            <DialogDescription>A dated goal for this project. Its progress comes from the tasks you put in it.</DialogDescription>
          </DialogHeader>
          {mutation.error && !Object.keys(errors).length && <FormAlert>{errorMessage(mutation.error)}</FormAlert>}
          <FormField label="Name" value={name} onChange={(e) => setName(e.target.value)} error={errors.name} maxLength={80} required />
          <div className="space-y-1.5">
            <Label htmlFor="milestone-due">Due date</Label>
            <Input id="milestone-due" type="date" value={due} onChange={(e) => setDue(e.target.value)} className="h-9 w-44" />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="milestone-description">Description</Label>
            <Textarea
              id="milestone-description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              className="min-h-20 text-[13px]"
              maxLength={2000}
            />
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" loading={mutation.isPending} disabled={!name.trim()}>
              {milestone ? 'Save' : 'Add milestone'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
