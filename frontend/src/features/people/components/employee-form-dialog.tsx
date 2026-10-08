import { useMemo, useState, type FormEvent } from 'react'
import { Mail } from 'lucide-react'
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
import { Switch } from '@/components/ui/form-controls'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { EmployeePicker } from '@/features/people/components/employee-picker'
import { useCreateEmployee, useDepartments, useTeams, useUpdateEmployee } from '@/features/people/api'
import { EMPLOYMENT_TYPES } from '@/features/people/meta'
import { ApiError, errorField, errorMessage } from '@/lib/api-client'
import { assignableRoles, ROLE_LABELS, timezones } from '@/lib/format'
import { useAuthStore, usePermissions } from '@/stores/auth-store'
import type { EmployeeDetail, EmployeeInput, EmploymentType, Role } from '@/types/api'

const NONE = '__none__'

interface FormState {
  full_name: string
  email: string
  job_title: string
  employee_code: string
  department_id: string | null
  team_id: string | null
  manager_employee_id: string | null
  employment_type: EmploymentType
  timezone: string
  location: string
  hired_on: string
  invite: boolean
  role: Role
}

function initialState(employee: EmployeeDetail | undefined, companyTimezone: string): FormState {
  return {
    full_name: employee?.full_name ?? '',
    email: employee?.email ?? '',
    job_title: employee?.job_title ?? '',
    employee_code: employee?.employee_code ?? '',
    department_id: employee?.department?.id ?? null,
    team_id: employee?.team?.id ?? null,
    manager_employee_id: employee?.manager?.id ?? null,
    employment_type: employee?.employment_type ?? 'full_time',
    timezone: employee?.timezone ?? companyTimezone,
    location: employee?.location ?? '',
    hired_on: employee?.hired_on ?? '',
    invite: false,
    role: 'EMPLOYEE',
  }
}

interface EmployeeFormDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  /** Edit this employee; omit to create a new one. */
  employee?: EmployeeDetail
  onSaved?: (employee: EmployeeDetail) => void
}

export function EmployeeFormDialog(props: EmployeeFormDialogProps) {
  // Remount on open so the form always starts from fresh values.
  if (!props.open) return <Dialog open={false} onOpenChange={props.onOpenChange} />
  return <EmployeeFormDialogInner key={props.employee?.id ?? 'new'} {...props} />
}

function EmployeeFormDialogInner({ open, onOpenChange, employee, onSaved }: EmployeeFormDialogProps) {
  const isEdit = Boolean(employee)
  const companyTimezone = useAuthStore((s) => s.company?.timezone ?? 'UTC')
  const actorRole = useAuthStore((s) => s.user?.role)
  const { can } = usePermissions()
  const [form, setForm] = useState<FormState>(() => initialState(employee, companyTimezone))
  const departments = useDepartments()
  const teams = useTeams()
  const create = useCreateEmployee()
  const update = useUpdateEmployee(employee?.id ?? '')
  const mutation = isEdit ? update : create
  const zones = useMemo(() => timezones(), [])

  const set = <K extends keyof FormState>(key: K, value: FormState[K]) => setForm((f) => ({ ...f, [key]: value }))

  const availableTeams = (teams.data ?? []).filter(
    (t) => !form.department_id || !t.department || t.department.id === form.department_id,
  )

  const validation = mutation.error instanceof ApiError ? mutation.error.fieldErrors : {}
  const domain = errorField(mutation.error)
  const fieldError = (field: string) => validation[field] ?? (domain?.field === field ? domain.message : undefined)
  const generalError = mutation.error && !Object.keys(validation).length && !domain ? errorMessage(mutation.error) : null

  const onSubmit = (event: FormEvent) => {
    event.preventDefault()
    const payload: EmployeeInput = {
      full_name: form.full_name.trim(),
      email: form.email.trim(),
      job_title: form.job_title.trim() || null,
      employee_code: form.employee_code.trim() || null,
      department_id: form.department_id,
      team_id: form.team_id,
      manager_employee_id: form.manager_employee_id,
      employment_type: form.employment_type,
      timezone: form.timezone,
      location: form.location.trim() || null,
      hired_on: form.hired_on || null,
    }
    if (!isEdit && form.invite) {
      payload.invite = true
      payload.role = form.role
    }
    mutation.mutate(payload, {
      onSuccess: (saved) => {
        toast.success(isEdit ? 'Employee updated' : `${saved.full_name} added`, {
          description: !isEdit && form.invite ? `An invitation was sent to ${saved.email}.` : undefined,
        })
        onOpenChange(false)
        onSaved?.(saved)
      },
    })
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[calc(100svh-2rem)] overflow-y-auto sm:max-w-2xl">
        <form onSubmit={onSubmit} noValidate className="space-y-5">
          <DialogHeader>
            <DialogTitle>{isEdit ? `Edit ${employee?.full_name}` : 'Add employee'}</DialogTitle>
            <DialogDescription>
              {isEdit ? 'Update employment details and reporting line.' : 'Add a person to your organisation directory.'}
            </DialogDescription>
          </DialogHeader>

          {generalError && <FormAlert>{generalError}</FormAlert>}

          <section className="grid gap-4 sm:grid-cols-2">
            <FormField
              label="Full name"
              value={form.full_name}
              onChange={(e) => set('full_name', e.target.value)}
              error={fieldError('full_name')}
              autoComplete="off"
            />
            <FormField
              label="Work email"
              type="email"
              value={form.email}
              onChange={(e) => set('email', e.target.value)}
              error={fieldError('email')}
              disabled={Boolean(employee?.account)}
              hint={employee?.account ? 'Linked to a user account — sign-in email cannot be changed here.' : undefined}
              autoComplete="off"
            />
            <FormField
              label="Job title"
              value={form.job_title}
              onChange={(e) => set('job_title', e.target.value)}
              error={fieldError('job_title')}
              placeholder="e.g. Product Designer"
            />
            <FormField
              label="Employee ID"
              value={form.employee_code}
              onChange={(e) => set('employee_code', e.target.value)}
              error={fieldError('employee_code')}
              placeholder="Optional, e.g. EMP-0042"
            />
          </section>

          <section className="grid gap-4 border-t pt-5 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="department">Department</Label>
              <Select
                value={form.department_id ?? NONE}
                onValueChange={(v) => {
                  const department = v === NONE ? null : v
                  setForm((f) => {
                    const team = teams.data?.find((t) => t.id === f.team_id)
                    const keepTeam = !department || !team?.department || team.department.id === department
                    return { ...f, department_id: department, team_id: keepTeam ? f.team_id : null }
                  })
                }}
              >
                <SelectTrigger id="department" aria-invalid={Boolean(fieldError('department_id')) || undefined}>
                  <SelectValue placeholder="No department" />
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
              <FieldHint error={fieldError('department_id')} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="team">Team</Label>
              <Select
                value={form.team_id ?? NONE}
                onValueChange={(v) => {
                  const team = teams.data?.find((t) => t.id === v)
                  setForm((f) => ({
                    ...f,
                    team_id: v === NONE ? null : v,
                    department_id: team?.department?.id ?? f.department_id,
                  }))
                }}
              >
                <SelectTrigger id="team" aria-invalid={Boolean(fieldError('team_id')) || undefined}>
                  <SelectValue placeholder="No team" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={NONE}>No team</SelectItem>
                  {availableTeams.map((t) => (
                    <SelectItem key={t.id} value={t.id}>
                      {t.name}
                      {t.department && !form.department_id ? ` · ${t.department.name}` : ''}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <FieldHint error={fieldError('team_id')} />
            </div>
            <div className="space-y-1.5 sm:col-span-2">
              <Label htmlFor="manager">Manager</Label>
              <EmployeePicker
                id="manager"
                value={form.manager_employee_id}
                onChange={(v) => set('manager_employee_id', v)}
                exclude={employee ? [employee.id] : []}
                placeholder="No manager"
                fallbackLabel={employee?.manager?.full_name}
                invalid={Boolean(fieldError('manager_employee_id'))}
              />
              <FieldHint error={fieldError('manager_employee_id')} />
            </div>
          </section>

          <section className="grid gap-4 border-t pt-5 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="employment-type">Employment type</Label>
              <Select value={form.employment_type} onValueChange={(v) => set('employment_type', v as EmploymentType)}>
                <SelectTrigger id="employment-type">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {Object.entries(EMPLOYMENT_TYPES).map(([value, label]) => (
                    <SelectItem key={value} value={value}>
                      {label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <FormField
              label="Hire date"
              type="date"
              value={form.hired_on}
              onChange={(e) => set('hired_on', e.target.value)}
              error={fieldError('hired_on')}
            />
            <div className="space-y-1.5">
              <Label htmlFor="timezone">Timezone</Label>
              <Select value={form.timezone} onValueChange={(v) => set('timezone', v)}>
                <SelectTrigger id="timezone" aria-invalid={Boolean(fieldError('timezone')) || undefined}>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent className="max-h-72">
                  {(zones.includes(form.timezone) ? zones : [form.timezone, ...zones]).map((zone) => (
                    <SelectItem key={zone} value={zone}>
                      {zone.replaceAll('_', ' ')}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <FieldHint error={fieldError('timezone')} />
            </div>
            <FormField
              label="Location"
              value={form.location}
              onChange={(e) => set('location', e.target.value)}
              error={fieldError('location')}
              placeholder="e.g. Berlin office"
            />
          </section>

          {!isEdit && can('USER_MANAGE') && (
            <section className="rounded-lg border bg-subtle p-4">
              <div className="flex items-start gap-3">
                <Mail className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
                <div className="flex-1">
                  <Label htmlFor="invite" className="text-[13px]">
                    Invite to WorkPulse
                  </Label>
                  <p className="mt-1 text-[12px] text-muted-foreground">
                    Create a user account and email an invitation to set a password.
                  </p>
                </div>
                <Switch id="invite" checked={form.invite} onCheckedChange={(v) => set('invite', v)} />
              </div>
              {form.invite && (
                <div className="mt-4 space-y-1.5 border-t pt-4 sm:max-w-xs">
                  <Label htmlFor="role">Role</Label>
                  <Select value={form.role} onValueChange={(v) => set('role', v as Role)}>
                    <SelectTrigger id="role" aria-invalid={Boolean(fieldError('role')) || undefined}>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {assignableRoles(actorRole).map((role) => (
                        <SelectItem key={role} value={role}>
                          {ROLE_LABELS[role]}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <FieldHint error={fieldError('role')} />
                </div>
              )}
            </section>
          )}

          <DialogFooter className="border-t pt-5">
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" loading={mutation.isPending}>
              {isEdit ? 'Save changes' : form.invite ? 'Add & send invite' : 'Add employee'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

function FieldHint({ error }: { error?: string }) {
  if (!error) return null
  return <p className="text-[12px] text-destructive">{error}</p>
}
