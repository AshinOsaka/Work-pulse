import { Fragment, useMemo, useRef, useState, type FormEvent } from 'react'
import { BadgeCheck, Check, ListChecks, LogOut, Minus, MoreHorizontal, Pencil, Plus, Search, ShieldCheck, ShieldOff, Trash2, UsersRound } from 'lucide-react'
import { toast } from 'sonner'

import { ConfirmDialog } from '@/components/common/confirm-dialog'
import { EmptyState } from '@/components/common/empty-state'
import { FilterSelect } from '@/components/common/filter-select'
import { FormAlert, FormField } from '@/components/common/form-field'
import { Pagination } from '@/components/common/pagination'
import { Person } from '@/components/common/person'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from '@/components/ui/dropdown-menu'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/misc'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { RequirePermission } from '@/features/auth/guards'
import { useWorkProfiles } from '@/features/productivity/api'
import { useResetUserMfa, useRevokeUserSessions } from '@/features/security/api'
import { useChangeUserRole, useUsers } from '@/features/settings/api'
import { useRoles } from '@/hooks/use-system'
import { ApiError, errorMessage } from '@/lib/api-client'
import { useRoleCatalog, useCreateRole, useDeleteRole, useUpdateRole } from '@/hooks/use-role-catalog'
import { assignableRoles, canAssignLevel, formatDateTime, ROLE_LABELS } from '@/lib/format'
import { useAuthStore } from '@/stores/auth-store'
import type { PermissionInfo, Role, RoleInfo, UserAdmin } from '@/types/api'

const ALL = '__all__'

function PermissionMatrix() {
  const roles = useRoles()
  if (roles.isPending) {
    return (
      <Card className="space-y-2 p-5">
        {Array.from({ length: 8 }, (_, i) => (
          <Skeleton key={i} className="h-8" />
        ))}
      </Card>
    )
  }
  if (roles.isError) {
    return (
      <Card>
        <EmptyState
          icon={ListChecks}
          title="Couldn't load roles"
          description={errorMessage(roles.error)}
          action={
            <Button size="sm" variant="outline" onClick={() => roles.refetch()}>
              Try again
            </Button>
          }
        />
      </Card>
    )
  }

  const byCategory = roles.data.permissions.reduce<Record<string, PermissionInfo[]>>((acc, p) => {
    ;(acc[p.category] ??= []).push(p)
    return acc
  }, {})

  return (
    <Card className="overflow-hidden">
      <CardHeader className="pb-4">
        <CardTitle>Permission matrix</CardTitle>
        <CardDescription>
          What each system role can do. Permissions are enforced by the API on every request; data access is further
          limited by scope (managers see their reporting line, team leads their teams).
        </CardDescription>
      </CardHeader>
      <Table>
        <TableHeader>
          <TableRow className="hover:bg-transparent">
            <TableHead className="min-w-[220px] pl-5">Permission</TableHead>
            {roles.data.roles.map((role) => (
              <TableHead key={role.key} className="text-center" title={role.description}>
                {role.name}
              </TableHead>
            ))}
          </TableRow>
        </TableHeader>
        <TableBody>
          {Object.entries(byCategory).map(([category, permissions]) => (
            <Fragment key={category}>
              <TableRow className="bg-subtle/60 hover:bg-subtle/60">
                <TableCell
                  colSpan={roles.data.roles.length + 1}
                  className="pl-5 text-[11px] font-semibold tracking-wide text-muted-foreground uppercase"
                >
                  {category}
                </TableCell>
              </TableRow>
              {permissions.map((permission) => (
                <TableRow key={permission.key}>
                  <TableCell className="pl-5">
                    <p className="font-medium">{permission.name}</p>
                    <p className="text-[12px] text-muted-foreground">{permission.description}</p>
                  </TableCell>
                  {roles.data.roles.map((role) => (
                    <TableCell key={role.key} className="text-center">
                      {role.permissions.includes(permission.key) ? (
                        <Check className="mx-auto size-4 text-primary" aria-label="Granted" />
                      ) : (
                        <Minus className="mx-auto size-4 text-muted-foreground" aria-label="Not granted" />
                      )}
                    </TableCell>
                  ))}
                </TableRow>
              ))}
            </Fragment>
          ))}
        </TableBody>
      </Table>
    </Card>
  )
}

function Members() {
  const actor = useAuthStore((s) => s.user)
  const [search, setSearch] = useState('')
  const [query, setQuery] = useState('')
  const [role, setRole] = useState<string>(ALL)
  const [jobRole, setJobRole] = useState<string | null>(null)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(25)
  const [pending, setPending] = useState<{ user: UserAdmin; roleKey: string } | null>(null)
  const [access, setAccess] = useState<{ user: UserAdmin; action: 'sessions' | 'mfa' } | null>(null)
  const revokeSessions = useRevokeUserSessions()
  const resetMfa = useResetUserMfa()
  const timer = useRef<number | undefined>(undefined)
  const profiles = useWorkProfiles()
  // Job-role membership isn't a server-side filter on /users, so when one is chosen we load the full list
  // (the workspace is small) and narrow to that job role's members client-side.
  const filteringByJob = jobRole !== null
  const users = useUsers({
    search: query || undefined,
    role: role === ALL ? undefined : (role as Role),
    page: filteringByJob ? 1 : page,
    page_size: filteringByJob ? 200 : pageSize,
  })
  const changeRole = useChangeUserRole()
  const catalog = useRoleCatalog()
  const assignable = catalog.assignable(actor?.role)

  const memberIds = useMemo(
    () => new Set(profiles.data?.find((p) => p.id === jobRole)?.members.map((m) => m.id) ?? []),
    [profiles.data, jobRole],
  )
  const items = (users.data?.items ?? []).filter(
    (u) => !filteringByJob || (u.employee_id ? memberIds.has(u.employee_id) : false),
  )

  const onSearch = (value: string) => {
    setSearch(value)
    window.clearTimeout(timer.current)
    timer.current = window.setTimeout(() => {
      setQuery(value.trim())
      setPage(1)
    }, 300)
  }

  return (
    <Card className="overflow-hidden">
      <CardHeader className="pb-4">
        <CardTitle>Members</CardTitle>
        <CardDescription>Everyone with a WorkPulse account. Role changes take effect immediately.</CardDescription>
      </CardHeader>
      <div className="flex flex-col gap-2 border-t px-5 py-3 sm:flex-row">
        <div className="relative sm:w-72">
          <Search className="absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input value={search} onChange={(e) => onSearch(e.target.value)} placeholder="Search members" className="h-8 pl-8 text-[13px]" aria-label="Search members" />
        </div>
        <FilterSelect
          label="Filter by role"
          value={role === ALL ? null : role}
          onChange={(v) => {
            setRole(v ?? ALL)
            setPage(1)
          }}
          options={catalog.roles.map((r) => ({ value: r.key, label: r.name }))}
          allLabel="All roles"
        />
        <FilterSelect
          label="Filter by job role"
          value={jobRole}
          onChange={(v) => {
            setJobRole(v)
            setPage(1)
          }}
          options={(profiles.data ?? []).map((p) => ({ value: p.id, label: `${p.name} (${p.members.length})` }))}
          allLabel="All job roles"
        />
      </div>
      {users.isPending ? (
        <div className="space-y-2 p-5">
          {Array.from({ length: 4 }, (_, i) => (
            <Skeleton key={i} className="h-10" />
          ))}
        </div>
      ) : users.isError ? (
        <EmptyState icon={UsersRound} title="Couldn't load members" description={errorMessage(users.error)} />
      ) : items.length === 0 ? (
        <EmptyState
          icon={UsersRound}
          title="No members found"
          description={
            filteringByJob
              ? 'Nobody with an account is in this job role yet. Assign members under People → Job roles.'
              : 'Try a different search or role filter.'
          }
        />
      ) : (
        <>
          <Table>
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                <TableHead className="pl-5">Member</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Last sign-in</TableHead>
                <TableHead className="w-52">Role</TableHead>
                <TableHead className="w-12 pr-5">
                  <span className="sr-only">Account actions</span>
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {items.map((user) => {
                const isSelf = user.id === actor?.id
                const editable = !isSelf && user.role !== 'SUPER_ADMIN' && canAssignLevel(actor?.role, user.role)
                return (
                  <TableRow key={user.id}>
                    <TableCell className="max-w-72 pl-5">
                      {user.employee_id ? (
                        <Person id={user.employee_id} name={user.full_name} subtitle={user.email} />
                      ) : (
                        <Person id={user.id} name={user.full_name} subtitle={user.email} link={false} />
                      )}
                    </TableCell>
                    <TableCell>
                      <Badge variant={user.status === 'active' ? 'success' : user.status === 'invited' ? 'warning' : 'secondary'}>
                        {user.status.charAt(0).toUpperCase() + user.status.slice(1)}
                      </Badge>
                      {user.mfa_enabled && (
                        <Badge variant="soft" className="ml-1.5" title="Two-step verification is on">
                          <ShieldCheck className="size-3" aria-hidden /> 2-step
                        </Badge>
                      )}
                    </TableCell>
                    <TableCell className="text-muted-foreground">{formatDateTime(user.last_login_at)}</TableCell>
                    <TableCell>
                      {editable ? (
                        <Select value={user.role_key} onValueChange={(v) => setPending({ user, roleKey: v })}>
                          <SelectTrigger size="sm" aria-label={`Role for ${user.full_name}`}>
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            {assignable.map((r) => (
                              <SelectItem key={r.key} value={r.key}>
                                {r.name}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      ) : (
                        <span className="flex items-center gap-2 text-[13px]">
                          {catalog.name(user.role_key)}
                          {isSelf && <span className="text-[11px] text-muted-foreground">(you)</span>}
                        </span>
                      )}
                    </TableCell>
                    <TableCell className="pr-5">
                      {editable && (
                        <DropdownMenu>
                          <DropdownMenuTrigger asChild>
                            <Button size="icon-sm" variant="ghost" aria-label={`Account actions for ${user.full_name}`}>
                              <MoreHorizontal />
                            </Button>
                          </DropdownMenuTrigger>
                          <DropdownMenuContent align="end">
                            <DropdownMenuItem onSelect={() => setAccess({ user, action: 'sessions' })}>
                              <LogOut /> Sign out everywhere
                            </DropdownMenuItem>
                            {user.mfa_enabled && (
                              <DropdownMenuItem onSelect={() => setAccess({ user, action: 'mfa' })}>
                                <ShieldOff /> Reset two-step verification
                              </DropdownMenuItem>
                            )}
                          </DropdownMenuContent>
                        </DropdownMenu>
                      )}
                    </TableCell>
                  </TableRow>
                )
              })}
            </TableBody>
          </Table>
          {!filteringByJob && users.data && (
            <div className="border-t">
              <Pagination
                page={users.data.page}
                pages={users.data.pages}
                pageSize={users.data.page_size}
                total={users.data.total}
                onPageChange={setPage}
                onPageSizeChange={(size) => {
                  setPageSize(size)
                  setPage(1)
                }}
              />
            </div>
          )}
        </>
      )}
      <ConfirmDialog
        open={Boolean(pending)}
        onOpenChange={(open) => !open && setPending(null)}
        title="Change role?"
        description={
          pending && (
            <>
              <strong>{pending.user.full_name}</strong> will change from {catalog.name(pending.user.role_key)} to{' '}
              <strong>{catalog.name(pending.roleKey)}</strong>. Their access updates on their next request.
            </>
          )
        }
        confirmLabel="Change role"
        loading={changeRole.isPending}
        onConfirm={() =>
          pending &&
          changeRole.mutate(
            { userId: pending.user.id, role: pending.roleKey },
            {
              onSuccess: () => {
                toast.success(`${pending.user.full_name} is now ${catalog.name(pending.roleKey)}`)
                setPending(null)
              },
              onError: (e) => {
                toast.error(errorMessage(e))
                setPending(null)
              },
            },
          )
        }
      />
      <ConfirmDialog
        open={Boolean(access)}
        onOpenChange={(open) => !open && setAccess(null)}
        title={access?.action === 'mfa' ? 'Reset two-step verification?' : 'Sign out everywhere?'}
        description={
          access &&
          (access.action === 'mfa' ? (
            <>
              <strong>{access.user.full_name}</strong> will be able to sign in with their password alone, and can set up two-step
              verification again. Use this when they've lost their phone and recovery codes. It is recorded in the audit log.
            </>
          ) : (
            <>
              Every browser where <strong>{access.user.full_name}</strong> is signed in is signed out immediately, for example after a
              lost laptop. It is recorded in the audit log.
            </>
          ))
        }
        confirmLabel={access?.action === 'mfa' ? 'Reset' : 'Sign out everywhere'}
        destructive
        loading={revokeSessions.isPending || resetMfa.isPending}
        onConfirm={() => {
          if (!access) return
          const done = (message: string) => {
            toast.success(message)
            setAccess(null)
          }
          const failed = (e: unknown) => {
            toast.error(errorMessage(e))
            setAccess(null)
          }
          if (access.action === 'mfa') {
            resetMfa.mutate(access.user.id, { onSuccess: () => done(`Two-step verification reset for ${access.user.full_name}`), onError: failed })
          } else {
            revokeSessions.mutate(access.user.id, {
              onSuccess: (r) => done(`${access.user.full_name} was signed out of ${r.revoked} ${r.revoked === 1 ? 'session' : 'sessions'}`),
              onError: failed,
            })
          }
        }}
      />
    </Card>
  )
}

function RoleDialog({ role, onOpenChange }: { role: RoleInfo | null; onOpenChange: (open: boolean) => void }) {
  const actor = useAuthStore((s) => s.user)
  const editing = role !== null
  const create = useCreateRole()
  const update = useUpdateRole(role?.key ?? '')
  const [name, setName] = useState(role?.name ?? '')
  const [level, setLevel] = useState<Role>(role?.base_level ?? 'EMPLOYEE')
  const levels = assignableRoles(actor?.role).filter((l) => l !== 'SUPER_ADMIN')
  const mutation = editing ? update : create
  const errors = mutation.error instanceof ApiError ? mutation.error.fieldErrors : {}

  const submit = (event: FormEvent) => {
    event.preventDefault()
    const trimmed = name.trim()
    if (trimmed.length < 2) return
    const done = (verb: string) => {
      toast.success(`Role ${verb}`)
      onOpenChange(false)
    }
    if (editing) update.mutate({ name: trimmed, base_level: level }, { onSuccess: () => done('updated') })
    else create.mutate({ name: trimmed, base_level: level }, { onSuccess: () => done('created') })
  }

  return (
    <Dialog open onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <form onSubmit={submit} noValidate className="space-y-4">
          <DialogHeader>
            <DialogTitle>{editing ? 'Edit role' : 'Add role'}</DialogTitle>
            <DialogDescription>
              A role groups people and grants a base access level. Fine-tune what each person sees in Dashboard access.
            </DialogDescription>
          </DialogHeader>
          {mutation.error && !Object.keys(errors).length && <FormAlert>{errorMessage(mutation.error)}</FormAlert>}
          <FormField
            label="Role name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            error={errors.name}
            placeholder="e.g. BDM, HR Manager"
            maxLength={60}
            required
          />
          <div className="space-y-1.5">
            <Label>Base access level</Label>
            <Select value={level} onValueChange={(v) => setLevel(v as Role)}>
              <SelectTrigger aria-label="Base access level">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {levels.map((l) => (
                  <SelectItem key={l} value={l}>
                    {ROLE_LABELS[l]}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <p className="text-[12px] text-muted-foreground">Decides what people with this role can access.</p>
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" loading={mutation.isPending}>
              {editing ? 'Save role' : 'Add role'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

function RolesManager() {
  const catalog = useRoleCatalog()
  const del = useDeleteRole()
  const [dialog, setDialog] = useState<{ role: RoleInfo | null } | null>(null)
  const [confirmDelete, setConfirmDelete] = useState<RoleInfo | null>(null)

  return (
    <Card className="overflow-hidden">
      <CardHeader className="flex flex-row items-center justify-between gap-3 pb-4">
        <div className="min-w-0">
          <CardTitle>Roles</CardTitle>
          <CardDescription>Built-in access levels and your own roles. Each role grants a base access level.</CardDescription>
        </div>
        <Button size="sm" onClick={() => setDialog({ role: null })}>
          <Plus /> Add role
        </Button>
      </CardHeader>
      <CardContent className="pt-0">
        <ul className="divide-y rounded-lg border">
          {catalog.roles.map((r) => (
            <li key={r.key} className="flex items-center gap-3 px-4 py-2.5">
              <span className="min-w-0 flex-1 truncate text-[13px] font-medium">
                {r.name}
                {r.is_system && (
                  <Badge variant="secondary" className="ml-2 align-middle">
                    Built-in
                  </Badge>
                )}
              </span>
              <Badge variant="soft" title="Base access level">
                <BadgeCheck className="size-3" aria-hidden /> {ROLE_LABELS[r.base_level]}
              </Badge>
              {!r.is_system && (
                <div className="flex gap-1">
                  <Button size="icon-sm" variant="ghost" aria-label={`Edit ${r.name}`} onClick={() => setDialog({ role: r })}>
                    <Pencil />
                  </Button>
                  <Button size="icon-sm" variant="ghost" aria-label={`Delete ${r.name}`} onClick={() => setConfirmDelete(r)}>
                    <Trash2 />
                  </Button>
                </div>
              )}
            </li>
          ))}
        </ul>
      </CardContent>
      {dialog && <RoleDialog role={dialog.role} onOpenChange={(open) => !open && setDialog(null)} />}
      <ConfirmDialog
        open={Boolean(confirmDelete)}
        onOpenChange={(open) => !open && setConfirmDelete(null)}
        title={`Delete ${confirmDelete?.name ?? 'role'}?`}
        description="You can only delete a role once nobody is assigned to it. This can't be undone."
        confirmLabel="Delete role"
        destructive
        loading={del.isPending}
        onConfirm={() =>
          confirmDelete &&
          del.mutate(confirmDelete.key, {
            onSuccess: () => {
              toast.success('Role deleted')
              setConfirmDelete(null)
            },
            onError: (e) => {
              toast.error(errorMessage(e))
              setConfirmDelete(null)
            },
          })
        }
      />
    </Card>
  )
}

export default function RolesPage() {
  return (
    <RequirePermission permission="USER_MANAGE">
      <div className="space-y-6">
        <Members />
        <RolesManager />
        <PermissionMatrix />
        <p className="text-[12px] text-muted-foreground">
          Custom roles are aliases over the built-in access levels above. Assign them to people here, and control what
          each person sees in Settings → Dashboard access.
        </p>
      </div>
    </RequirePermission>
  )
}
