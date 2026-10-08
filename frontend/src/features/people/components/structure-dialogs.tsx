import { useState, type FormEvent } from 'react'
import { toast } from 'sonner'

import { FormAlert, FormField } from '@/components/common/form-field'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Textarea } from '@/components/ui/form-controls'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { useDepartments, useSaveDepartment, useSaveTeam } from '@/features/people/api'
import { EmployeePicker } from '@/features/people/components/employee-picker'
import { ApiError, errorField, errorMessage } from '@/lib/api-client'
import type { Department, Team } from '@/types/api'

const NONE = '__none__'

function useFieldErrors(error: unknown) {
  const validation = error instanceof ApiError ? error.fieldErrors : {}
  const domain = errorField(error)
  return {
    field: (name: string) => validation[name] ?? (domain?.field === name ? domain.message : undefined),
    general: error && !Object.keys(validation).length && !domain ? errorMessage(error) : null,
  }
}

interface DialogProps<T> {
  open: boolean
  onOpenChange: (open: boolean) => void
  item?: T
}

export function DepartmentDialog(props: DialogProps<Department>) {
  if (!props.open) return <Dialog open={false} onOpenChange={props.onOpenChange} />
  return <DepartmentDialogInner key={props.item?.id ?? 'new'} {...props} />
}

function DepartmentDialogInner({ open, onOpenChange, item }: DialogProps<Department>) {
  const save = useSaveDepartment(item?.id)
  const [name, setName] = useState(item?.name ?? '')
  const [description, setDescription] = useState(item?.description ?? '')
  const [head, setHead] = useState<string | null>(item?.head?.id ?? null)
  const errors = useFieldErrors(save.error)

  const onSubmit = (event: FormEvent) => {
    event.preventDefault()
    save.mutate(
      { name: name.trim(), description: description.trim() || null, head_employee_id: head },
      {
        onSuccess: (saved) => {
          toast.success(item ? 'Department updated' : `${saved.name} created`)
          onOpenChange(false)
        },
      },
    )
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <form onSubmit={onSubmit} className="space-y-4" noValidate>
          <DialogHeader>
            <DialogTitle>{item ? 'Edit department' : 'New department'}</DialogTitle>
            <DialogDescription>Departments group teams and employees by function.</DialogDescription>
          </DialogHeader>
          {errors.general && <FormAlert>{errors.general}</FormAlert>}
          <FormField label="Name" value={name} onChange={(e) => setName(e.target.value)} error={errors.field('name')} placeholder="e.g. Engineering" />
          <div className="space-y-1.5">
            <Label htmlFor="department-description">Description</Label>
            <Textarea
              id="department-description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="What does this department do?"
              rows={3}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="department-head">Department head</Label>
            <EmployeePicker
              id="department-head"
              value={head}
              onChange={setHead}
              placeholder="No department head"
              fallbackLabel={item?.head?.full_name}
              invalid={Boolean(errors.field('head_employee_id'))}
            />
            <p className="text-[12px] text-muted-foreground">
              {errors.field('head_employee_id') ?? 'Managers who head a department can view its employees.'}
            </p>
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" loading={save.isPending} disabled={name.trim().length < 2}>
              {item ? 'Save changes' : 'Create department'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

export function TeamDialog(props: DialogProps<Team> & { defaultDepartmentId?: string }) {
  if (!props.open) return <Dialog open={false} onOpenChange={props.onOpenChange} />
  return <TeamDialogInner key={props.item?.id ?? 'new'} {...props} />
}

function TeamDialogInner({ open, onOpenChange, item, defaultDepartmentId }: DialogProps<Team> & { defaultDepartmentId?: string }) {
  const save = useSaveTeam(item?.id)
  const departments = useDepartments()
  const [name, setName] = useState(item?.name ?? '')
  const [description, setDescription] = useState(item?.description ?? '')
  const [department, setDepartment] = useState<string | null>(item?.department?.id ?? defaultDepartmentId ?? null)
  const [lead, setLead] = useState<string | null>(item?.lead?.id ?? null)
  const errors = useFieldErrors(save.error)
  const departmentChanged = Boolean(item && item.member_count > 0 && department && department !== item.department?.id)

  const onSubmit = (event: FormEvent) => {
    event.preventDefault()
    save.mutate(
      { name: name.trim(), description: description.trim() || null, department_id: department, lead_employee_id: lead },
      {
        onSuccess: (saved) => {
          toast.success(item ? 'Team updated' : `${saved.name} created`)
          onOpenChange(false)
        },
      },
    )
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <form onSubmit={onSubmit} className="space-y-4" noValidate>
          <DialogHeader>
            <DialogTitle>{item ? 'Edit team' : 'New team'}</DialogTitle>
            <DialogDescription>Teams are the day-to-day working groups inside a department.</DialogDescription>
          </DialogHeader>
          {errors.general && <FormAlert>{errors.general}</FormAlert>}
          <FormField label="Name" value={name} onChange={(e) => setName(e.target.value)} error={errors.field('name')} placeholder="e.g. Platform" />
          <div className="space-y-1.5">
            <Label htmlFor="team-department">Department</Label>
            <Select value={department ?? NONE} onValueChange={(v) => setDepartment(v === NONE ? null : v)}>
              <SelectTrigger id="team-department" aria-invalid={Boolean(errors.field('department_id')) || undefined}>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={NONE}>No department</SelectItem>
                {departments.data?.map((d) => (
                  <SelectItem key={d.id} value={d.id}>
                    {d.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {departmentChanged && (
              <p className="text-[12px] text-warning">
                The team's {item?.member_count} {item?.member_count === 1 ? 'member' : 'members'} will move to the new department.
              </p>
            )}
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="team-lead">Team lead</Label>
            <EmployeePicker
              id="team-lead"
              value={lead}
              onChange={setLead}
              placeholder="No team lead"
              fallbackLabel={item?.lead?.full_name}
              invalid={Boolean(errors.field('lead_employee_id'))}
            />
            <p className="text-[12px] text-muted-foreground">
              {errors.field('lead_employee_id') ?? 'Team leads can view their team members.'}
            </p>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="team-description">Description</Label>
            <Textarea id="team-description" value={description} onChange={(e) => setDescription(e.target.value)} rows={2} />
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" loading={save.isPending} disabled={name.trim().length < 2}>
              {item ? 'Save changes' : 'Create team'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
