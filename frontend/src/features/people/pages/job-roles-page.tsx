import { useMemo, useState, type FormEvent } from 'react'
import { BriefcaseBusiness, Plus, Search, Trash2, Users } from 'lucide-react'
import { toast } from 'sonner'

import { ConfirmDialog } from '@/components/common/confirm-dialog'
import { EmptyState } from '@/components/common/empty-state'
import { FormAlert, FormField } from '@/components/common/form-field'
import { AvatarGroup } from '@/components/common/person'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/misc'
import { useEmployeeOptions } from '@/features/people/api'
import { useCreateProfile, useDeleteProfile, useSetProfileMembers, useUpdateProfile, useWorkProfiles } from '@/features/productivity/api'
import { AssigneePicker } from '@/features/work/components/assignee-picker'
import { ApiError, errorMessage } from '@/lib/api-client'
import { usePermissions } from '@/stores/auth-store'
import type { EmployeeRef, WorkProfile } from '@/types/api'

/** Create a new job role, or rename an existing one. */
function JobRoleDialog({ role, onOpenChange }: { role: WorkProfile | null; onOpenChange: (open: boolean) => void }) {
  const create = useCreateProfile()
  const update = useUpdateProfile()
  const editing = role !== null
  const [name, setName] = useState(role?.name ?? '')
  const mutation = editing ? update : create
  const errors = mutation.error instanceof ApiError ? mutation.error.fieldErrors : {}

  const submit = (event: FormEvent) => {
    event.preventDefault()
    const trimmed = name.trim()
    if (trimmed.length < 2) return
    const done = (verb: string) => {
      toast.success(`Job role ${verb}`)
      onOpenChange(false)
    }
    if (editing) update.mutate({ id: role.id, name: trimmed }, { onSuccess: () => done('updated') })
    else create.mutate({ name: trimmed }, { onSuccess: () => done('created') })
  }

  return (
    <Dialog open onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <form onSubmit={submit} noValidate className="space-y-4">
          <DialogHeader>
            <DialogTitle>{editing ? 'Edit job role' : 'Add new job role'}</DialogTitle>
            <DialogDescription>
              A job role groups people with the same work (e.g. Developer, Ticketing, Sales). Its activity rules apply
              to its members on top of the company, department and team rules.
            </DialogDescription>
          </DialogHeader>
          {mutation.error && !Object.keys(errors).length && <FormAlert>{errorMessage(mutation.error)}</FormAlert>}
          <FormField
            label="Job role"
            value={name}
            onChange={(e) => setName(e.target.value)}
            error={errors.name}
            placeholder="e.g., Software Engineer"
            maxLength={60}
            required
          />
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" loading={mutation.isPending} disabled={name.trim().length < 2}>
              {editing ? 'Save changes' : 'Save job role'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

function MembersDialog({ role, onOpenChange }: { role: WorkProfile; onOpenChange: (open: boolean) => void }) {
  const people = useEmployeeOptions()
  const save = useSetProfileMembers()
  const [ids, setIds] = useState(role.members.map((m) => m.id))
  const everyone: EmployeeRef[] = (people.data ?? []).map((p) => ({
    id: p.id,
    full_name: p.full_name,
    email: '',
    job_title: p.job_title ?? null,
    status: 'active',
  }))
  return (
    <Dialog open onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Members of {role.name}</DialogTitle>
          <DialogDescription>Each person has at most one job role; adding someone here moves them from any other role.</DialogDescription>
        </DialogHeader>
        <AssigneePicker members={everyone} value={ids} onChange={setIds} label={`${role.name} members`} placeholder="Add people" />
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            loading={save.isPending}
            onClick={() =>
              save.mutate(
                { id: role.id, employee_ids: ids },
                {
                  onSuccess: () => {
                    toast.success('Members updated')
                    onOpenChange(false)
                  },
                  onError: (e) => toast.error(errorMessage(e)),
                },
              )
            }
          >
            Save
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export default function JobRolesPage() {
  const { can } = usePermissions()
  const editable = can('POLICY_MANAGE')
  const profiles = useWorkProfiles()
  const remove = useDeleteProfile()
  const [search, setSearch] = useState('')
  const [editingRole, setEditingRole] = useState<WorkProfile | 'new' | null>(null)
  const [members, setMembers] = useState<WorkProfile | null>(null)
  const [deleting, setDeleting] = useState<WorkProfile | null>(null)

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase()
    const list = profiles.data ?? []
    return q ? list.filter((p) => p.name.toLowerCase().includes(q)) : list
  }, [profiles.data, search])

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center gap-3">
        <div className="relative min-w-56 flex-1">
          <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
          <Input
            type="search"
            placeholder="Search for a job role…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pl-9"
          />
        </div>
        {editable && (
          <Button onClick={() => setEditingRole('new')}>
            <Plus /> Add Job Role
          </Button>
        )}
      </div>

      {!profiles.data ? (
        <div className="space-y-2">
          <Skeleton className="h-16" />
          <Skeleton className="h-16" />
        </div>
      ) : filtered.length === 0 ? (
        <EmptyState
          icon={BriefcaseBusiness}
          title={search ? 'No job roles match' : 'No job roles yet'}
          description={
            editable
              ? 'Add roles like Developer, Ticketing or Sales, then assign people to them.'
              : 'An administrator can add job roles.'
          }
        />
      ) : (
        <ul className="space-y-2.5">
          {filtered.map((role) => (
            <li
              key={role.id}
              className="flex flex-wrap items-center gap-3 rounded-xl border bg-card px-4 py-3 shadow-xs"
            >
              <div className="min-w-0 flex-1">
                <p className="text-[14px] font-semibold">
                  {role.name}{' '}
                  <span className="text-[12px] font-normal text-muted-foreground">
                    ({role.members.length} {role.members.length === 1 ? 'member' : 'members'})
                  </span>
                </p>
                <p className="text-[12px] text-muted-foreground">
                  {role.rule_count} rule{role.rule_count === 1 ? '' : 's'}
                  {role.description && ` · ${role.description}`}
                </p>
              </div>
              <AvatarGroup people={role.members} max={6} />
              <span className="flex gap-1">
                {editable && (
                  <Button size="sm" variant="outline" onClick={() => setEditingRole(role)}>
                    Edit
                  </Button>
                )}
                <Button size="sm" variant="outline" onClick={() => setMembers(role)}>
                  <Users /> View Members
                </Button>
                {editable && (
                  <Button
                    size="sm"
                    variant="ghost"
                    className="text-destructive hover:text-destructive"
                    onClick={() => setDeleting(role)}
                  >
                    <Trash2 /> Delete
                  </Button>
                )}
              </span>
            </li>
          ))}
        </ul>
      )}

      {editingRole && (
        <JobRoleDialog
          role={editingRole === 'new' ? null : editingRole}
          onOpenChange={(open) => !open && setEditingRole(null)}
        />
      )}
      {members && <MembersDialog key={members.id} role={members} onOpenChange={(open) => !open && setMembers(null)} />}
      <ConfirmDialog
        open={deleting !== null}
        onOpenChange={(open) => !open && setDeleting(null)}
        title={`Delete ${deleting?.name ?? ''}?`}
        description="Its rules are removed and its members fall back to the company, department and team rules. All productivity figures are recalculated."
        confirmLabel="Delete job role"
        destructive
        loading={remove.isPending}
        onConfirm={() => deleting && remove.mutate(deleting.id, { onSuccess: () => setDeleting(null), onError: (e) => toast.error(errorMessage(e)) })}
      />
    </div>
  )
}
