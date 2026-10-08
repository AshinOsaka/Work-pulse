import { useState, type FormEvent } from 'react'
import { toast } from 'sonner'

import { FormAlert, FormField } from '@/components/common/form-field'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/form-controls'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useEmployeeOptions } from '@/features/people/api'
import { useCreateProject, useSetMembers, useUpdateProject } from '@/features/work/api'
import { AssigneePicker } from '@/features/work/components/assignee-picker'
import { PROJECT_COLOR, PROJECT_COLORS } from '@/features/work/meta'
import { ApiError, errorMessage } from '@/lib/api-client'
import { cn } from '@/lib/utils'
import type { EmployeeRef, Project, ProjectColor } from '@/types/api'

/** Create a project, or edit one (details and members). */
export function ProjectDialog({ open, onOpenChange, project, onCreated }: { open: boolean; onOpenChange: (open: boolean) => void; project?: Project; onCreated?: (p: Project) => void }) {
  const create = useCreateProject()
  const update = useUpdateProject()
  const setMembers = useSetMembers()
  const people = useEmployeeOptions(open)
  const [name, setName] = useState(project?.name ?? '')
  const [key, setKey] = useState(project?.key ?? '')
  const [description, setDescription] = useState(project?.description ?? '')
  const [color, setColor] = useState<ProjectColor>(project?.color ?? 'indigo')
  const [due, setDue] = useState(project?.due_date ?? '')
  const [members, setMemberIds] = useState<string[]>(project?.members.map((m) => m.id) ?? [])
  const mutation = project ? update : create
  const errors = mutation.error instanceof ApiError ? mutation.error.fieldErrors : {}
  const everyone: EmployeeRef[] = (people.data ?? []).map((p) => ({ id: p.id, full_name: p.full_name, email: '', job_title: p.job_title ?? null, status: 'active' }))

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    try {
      if (project) {
        await update.mutateAsync({ id: project.id, name, description: description || null, color, due_date: due || null })
        if (members.join() !== project.members.map((m) => m.id).join()) await setMembers.mutateAsync({ id: project.id, member_ids: members })
        toast.success('Project updated')
      } else {
        const created = await create.mutateAsync({ name, key: key || undefined, description: description || null, color, due_date: due || null, member_ids: members })
        toast.success(`${created.name} created`)
        onCreated?.(created)
      }
      onOpenChange(false)
    } catch (error) {
      if (!(error instanceof ApiError) || !Object.keys(error.fieldErrors).length) toast.error(errorMessage(error))
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <form onSubmit={submit} noValidate className="space-y-4">
          <DialogHeader>
            <DialogTitle>{project ? 'Edit project' : 'New project'}</DialogTitle>
            <DialogDescription>Members can see the project, add tasks, comment and track time.</DialogDescription>
          </DialogHeader>
          {mutation.error && !Object.keys(errors).length && <FormAlert>{errorMessage(mutation.error)}</FormAlert>}
          <div className="grid grid-cols-[minmax(0,1fr)] gap-4 sm:grid-cols-[minmax(0,1fr)_110px]">
            <FormField label="Name" value={name} onChange={(e) => setName(e.target.value)} error={errors.name} required />
            <FormField
              label="Key"
              value={key}
              onChange={(e) => setKey(e.target.value.toUpperCase().slice(0, 6))}
              error={errors.key}
              placeholder="Auto"
              disabled={Boolean(project)}
              hint={project ? undefined : 'e.g. WEB → WEB-12'}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="project-description">Description</Label>
            <Textarea id="project-description" value={description} onChange={(e) => setDescription(e.target.value)} className="min-h-20 text-[13px]" maxLength={2000} />
          </div>
          <div className="flex flex-wrap items-end gap-4">
            <fieldset className="space-y-1.5">
              <legend className="mb-1.5 text-[13px] font-medium">Colour</legend>
              <div className="flex gap-1.5">
                {PROJECT_COLORS.map((c) => (
                  <button
                    key={c}
                    type="button"
                    aria-label={c}
                    aria-pressed={color === c}
                    onClick={() => setColor(c)}
                    className={cn('size-6 rounded-full ring-offset-2 ring-offset-background transition', PROJECT_COLOR[c], color === c ? 'ring-2 ring-ring' : 'hover:scale-110')}
                  />
                ))}
              </div>
            </fieldset>
            <div className="space-y-1.5">
              <Label htmlFor="project-due">Due date</Label>
              <Input id="project-due" type="date" value={due} onChange={(e) => setDue(e.target.value)} className="h-9 w-40" />
            </div>
          </div>
          <div className="space-y-1.5">
            <Label>Members</Label>
            <AssigneePicker members={everyone} value={members} onChange={setMemberIds} label="Project members" />
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" loading={mutation.isPending || setMembers.isPending} disabled={name.trim().length < 2}>
              {project ? 'Save' : 'Create project'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
