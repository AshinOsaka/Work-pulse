import { useState, type FormEvent } from 'react'
import { Pencil, Plus, ShieldPlus, Trash2 } from 'lucide-react'
import { toast } from 'sonner'

import { ConfirmDialog } from '@/components/common/confirm-dialog'
import { EmptyState } from '@/components/common/empty-state'
import { FormAlert, FormField } from '@/components/common/form-field'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Checkbox } from '@/components/ui/form-controls'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { useCreateRole, useDeleteRole, useRoleCatalog, useUpdateRole } from '@/hooks/use-role-catalog'
import { useRoles } from '@/hooks/use-system'
import { errorMessage } from '@/lib/api-client'
import { canAssignLevel, roleKeyLabel } from '@/lib/format'
import { useAuthStore, usePermissions } from '@/stores/auth-store'
import type { Permission, PermissionInfo, Role, RoleInfo } from '@/types/api'

/** Built-in levels a custom role can be based on (Super Admin is reserved for the platform). */
const BASE_LEVELS: Role[] = ['EMPLOYEE', 'TEAM_LEAD', 'MANAGER', 'COMPANY_ADMIN']

const SCOPE_HINT: Record<Role, string> = {
  EMPLOYEE: 'Sees only their own data.',
  TEAM_LEAD: 'Sees the people they manage and the teams they lead.',
  MANAGER: 'Sees the people they manage, their teams and the departments they head.',
  COMPANY_ADMIN: 'Sees everyone in the workspace.',
  SUPER_ADMIN: 'Platform operator.',
}

function RoleDialog({ role, onClose }: { role?: RoleInfo; onClose: () => void }) {
  const roles = useRoles()
  const actor = useAuthStore((s) => s.user)
  const { can } = usePermissions()
  const create = useCreateRole()
  const update = useUpdateRole(role?.key ?? '')
  const mutation = role ? update : create
  const builtIn = (level: Role) => roles.data?.roles.find((r) => r.key === level)?.permissions ?? []
  const [name, setName] = useState(role?.name ?? '')
  const [base, setBase] = useState<Role>(role?.base_level ?? 'TEAM_LEAD')
  const [chosen, setChosen] = useState<Set<Permission>>(() => new Set(role ? role.permissions : builtIn('TEAM_LEAD')))
  const catalog = roles.data?.permissions ?? []
  const byCategory = catalog.reduce<Record<string, PermissionInfo[]>>((acc, p) => {
    ;(acc[p.category] ??= []).push(p)
    return acc
  }, {})
  const levels = BASE_LEVELS.filter((l) => canAssignLevel(actor?.role, l))

  const toggle = (key: Permission, on: boolean) =>
    setChosen((current) => {
      const next = new Set(current)
      if (on) next.add(key)
      else next.delete(key)
      return next
    })

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    const input = { name: name.trim(), base_level: base, permissions: [...chosen] }
    try {
      if (role) await update.mutateAsync(input)
      else await create.mutateAsync(input)
      toast.success(role ? `${input.name} updated` : `${input.name} added`)
      onClose()
    } catch {
      /* shown in the form */
    }
  }

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-xl">
        <form onSubmit={submit} noValidate className="space-y-5">
          <DialogHeader>
            <DialogTitle>{role ? `Edit ${role.name}` : 'New role'}</DialogTitle>
            <DialogDescription>
              Name the role, choose whose data it sees, and tick what it can do. Changes apply to everyone with the role
              at once.
            </DialogDescription>
          </DialogHeader>
          {mutation.error && <FormAlert>{errorMessage(mutation.error)}</FormAlert>}
          <FormField
            label="Role name"
            placeholder="e.g. HR Manager, BDM, Supervisor"
            value={name}
            onChange={(e) => setName(e.target.value)}
            maxLength={60}
            required
          />
          <div className="space-y-1.5">
            <Label htmlFor="role-base">Sees data of</Label>
            <Select
              value={base}
              onValueChange={(v) => {
                const level = v as Role
                setBase(level)
                // A new role starts from the level's usual permissions; an existing role keeps its ticks.
                if (!role) setChosen(new Set(builtIn(level)))
              }}
            >
              <SelectTrigger id="role-base" className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {levels.map((level) => (
                  <SelectItem key={level} value={level}>
                    Like a {roleKeyLabel(level)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <p className="text-[12px] text-muted-foreground">{SCOPE_HINT[base]}</p>
          </div>

          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <Label>What this role can do</Label>
              <Button type="button" size="sm" variant="ghost" onClick={() => setChosen(new Set(builtIn(base)))}>
                Reset to {roleKeyLabel(base)}
              </Button>
            </div>
            {Object.entries(byCategory).map(([category, permissions]) => (
              <fieldset key={category} className="space-y-2 rounded-lg border p-3">
                <legend className="px-1 text-[11px] font-semibold tracking-wide text-muted-foreground uppercase">
                  {category}
                </legend>
                {permissions.map((p) => {
                  const grantable = can(p.key)
                  return (
                    <label
                      key={p.key}
                      htmlFor={`perm-${p.key}`}
                      className={`flex cursor-pointer items-start gap-2.5 text-[13px] ${grantable ? '' : 'cursor-not-allowed opacity-50'}`}
                      title={grantable ? undefined : "You can't give a permission you don't have yourself."}
                    >
                      <Checkbox
                        id={`perm-${p.key}`}
                        className="mt-0.5"
                        checked={chosen.has(p.key)}
                        disabled={!grantable}
                        onCheckedChange={(v) => toggle(p.key, v === true)}
                        aria-label={p.name}
                      />
                      <span>
                        <span className="font-medium">{p.name}</span>
                        <span className="block text-[12px] text-muted-foreground">{p.description}</span>
                      </span>
                    </label>
                  )
                })}
              </fieldset>
            ))}
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit" loading={mutation.isPending} disabled={name.trim().length < 2}>
              {role ? 'Save role' : 'Add role'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

/** Company roles beyond the built-in ones, each with its own permissions. */
export function CustomRolesCard() {
  const catalog = useRoleCatalog()
  const remove = useDeleteRole()
  const [editing, setEditing] = useState<RoleInfo | 'new' | null>(null)
  const [deleting, setDeleting] = useState<RoleInfo | null>(null)
  const custom = catalog.roles.filter((r) => !r.is_system)

  return (
    <Card className="overflow-hidden">
      <CardHeader className="flex flex-row items-start justify-between gap-4 pb-4">
        <div className="space-y-1.5">
          <CardTitle>Custom roles</CardTitle>
          <CardDescription>
            Your own roles, like HR Manager or BDM, with exactly the permissions you choose. Assign them to members
            above.
          </CardDescription>
        </div>
        <Button size="sm" onClick={() => setEditing('new')}>
          <Plus /> New role
        </Button>
      </CardHeader>
      {custom.length === 0 ? (
        <EmptyState
          size="sm"
          icon={ShieldPlus}
          title="No custom roles yet"
          description="Add roles such as Supervisor, Assistant Manager, BDM or HR Manager."
        />
      ) : (
        <ul className="divide-y border-t">
          {custom.map((role) => (
            <li key={role.key} className="flex items-center gap-3 px-5 py-3">
              <div className="min-w-0 flex-1">
                <p className="text-[13px] font-semibold">{role.name}</p>
                <p className="text-[12px] text-muted-foreground">
                  Sees data like a {roleKeyLabel(role.base_level)} · {role.permissions.length} permission
                  {role.permissions.length === 1 ? '' : 's'}
                </p>
              </div>
              <Badge variant="soft">{roleKeyLabel(role.base_level)}</Badge>
              <Button size="sm" variant="ghost" aria-label={`Edit ${role.name}`} onClick={() => setEditing(role)}>
                <Pencil />
              </Button>
              <Button size="sm" variant="ghost" aria-label={`Delete ${role.name}`} onClick={() => setDeleting(role)}>
                <Trash2 />
              </Button>
            </li>
          ))}
        </ul>
      )}
      {editing && <RoleDialog role={editing === 'new' ? undefined : editing} onClose={() => setEditing(null)} />}
      <ConfirmDialog
        open={Boolean(deleting)}
        onOpenChange={(open) => !open && setDeleting(null)}
        title={`Delete ${deleting?.name ?? 'this role'}?`}
        description="Only a role nobody has can be deleted: move its members to another role first."
        confirmLabel="Delete role"
        destructive
        loading={remove.isPending}
        onConfirm={() =>
          deleting &&
          remove.mutate(deleting.key, {
            onSuccess: () => {
              toast.success(`${deleting.name} deleted`)
              setDeleting(null)
            },
            onError: (e) => toast.error(errorMessage(e)),
          })
        }
      />
    </Card>
  )
}
