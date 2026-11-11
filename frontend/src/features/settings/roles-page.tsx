import { Fragment, useMemo, useRef, useState } from 'react'
import { Check, ListChecks, LogOut, Minus, MoreHorizontal, Search, ShieldCheck, ShieldOff, UsersRound } from 'lucide-react'
import { toast } from 'sonner'

import { ConfirmDialog } from '@/components/common/confirm-dialog'
import { EmptyState } from '@/components/common/empty-state'
import { FilterSelect } from '@/components/common/filter-select'
import { Pagination } from '@/components/common/pagination'
import { Person } from '@/components/common/person'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from '@/components/ui/dropdown-menu'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/misc'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { RequirePermission } from '@/features/auth/guards'
import { useSetProfileMembers, useWorkProfiles } from '@/features/productivity/api'
import { CustomRolesCard } from '@/features/settings/custom-roles-card'
import { useResetUserMfa, useRevokeUserSessions } from '@/features/security/api'
import { useChangeUserRole, useUsers } from '@/features/settings/api'
import { useRoleCatalog } from '@/hooks/use-role-catalog'
import { useRoles } from '@/hooks/use-system'
import { errorMessage } from '@/lib/api-client'
import { canAssignLevel, formatDateTime } from '@/lib/format'
import { usePermissions, useAuthStore } from '@/stores/auth-store'
import type { PermissionInfo, UserAdmin, WorkProfile } from '@/types/api'

const NONE = '__none__'

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
          What each role can do, built-in and custom. Permissions are enforced by the API on every request; data access is further
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
  const [jobRole, setJobRole] = useState<string | null>(null)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(25)
  const [access, setAccess] = useState<{ user: UserAdmin; action: 'sessions' | 'mfa' } | null>(null)
  const { can } = usePermissions()
  const revokeSessions = useRevokeUserSessions()
  const resetMfa = useResetUserMfa()
  const setMembers = useSetProfileMembers()
  const timer = useRef<number | undefined>(undefined)
  const profiles = useWorkProfiles()
  // A single role filter = the company's roles. Membership isn't a server-side filter on /users, so when a
  // role is chosen we load the full list (the workspace is small) and narrow to its members client-side.
  const filteringByJob = jobRole !== null
  const users = useUsers({
    search: query || undefined,
    page: filteringByJob ? 1 : page,
    page_size: filteringByJob ? 200 : pageSize,
  })
  const canEditRole = can('POLICY_MANAGE')
  // Access role = what the person can see and do (Employee, Manager, a custom role…). Job role = their
  // work profile (Developer, Sales…), which only decides productivity rules.
  const catalog = useRoleCatalog()
  const changeAccess = useChangeUserRole()
  const [pendingAccess, setPendingAccess] = useState<{ user: UserAdmin; role: string } | null>(null)

  // Each person's current role, derived from which work profile holds them.
  const roleByEmployee = useMemo(() => {
    const map = new Map<string, WorkProfile>()
    for (const p of profiles.data ?? []) for (const m of p.members) map.set(m.id, p)
    return map
  }, [profiles.data])

  const memberIds = useMemo(
    () => new Set(profiles.data?.find((p) => p.id === jobRole)?.members.map((m) => m.id) ?? []),
    [profiles.data, jobRole],
  )
  const items = (users.data?.items ?? []).filter(
    (u) => !filteringByJob || (u.employee_id ? memberIds.has(u.employee_id) : false),
  )

  // Move a person to a role (work profile), or clear it. The target keeps its members; the person
  // automatically leaves whatever role they were in (membership is a single field on the employee).
  const assignRole = (employeeId: string, current: WorkProfile | undefined, targetId: string) => {
    if (targetId === (current?.id ?? NONE)) return
    const ok = (message: string) => () => toast.success(message)
    const fail = (e: unknown) => toast.error(errorMessage(e))
    if (targetId === NONE) {
      if (!current) return
      const ids = current.members.filter((m) => m.id !== employeeId).map((m) => m.id)
      setMembers.mutate({ id: current.id, employee_ids: ids }, { onSuccess: ok('Job role removed'), onError: fail })
      return
    }
    const target = profiles.data?.find((p) => p.id === targetId)
    if (!target) return
    const ids = [...target.members.map((m) => m.id).filter((id) => id !== employeeId), employeeId]
    setMembers.mutate({ id: targetId, employee_ids: ids }, { onSuccess: ok(`Job role set to ${target.name}`), onError: fail })
  }

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
        <CardDescription>
          Everyone with a WorkPulse account. <strong>Access role</strong> decides what they can see and do;{' '}
          <strong>Job role</strong> only decides which apps count as productive for them. Changes apply immediately.
        </CardDescription>
      </CardHeader>
      <div className="flex flex-col gap-2 border-t px-5 py-3 sm:flex-row">
        <div className="relative sm:w-72">
          <Search className="absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input value={search} onChange={(e) => onSearch(e.target.value)} placeholder="Search members" className="h-8 pl-8 text-[13px]" aria-label="Search members" />
        </div>
        <FilterSelect
          label="Filter by job role"
          value={jobRole}
          onChange={(v) => {
            setJobRole(v)
            setPage(1)
          }}
          options={(profiles.data ?? []).map((p) => ({ value: p.id, label: p.name }))}
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
                <TableHead className="w-52">Access role</TableHead>
                <TableHead className="w-52">Job role</TableHead>
                <TableHead className="w-12 pr-5">
                  <span className="sr-only">Account actions</span>
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {items.map((user) => {
                const isSelf = user.id === actor?.id
                const current = user.employee_id ? roleByEmployee.get(user.employee_id) : undefined
                const canSetRole = canEditRole && Boolean(user.employee_id)
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
                      {can('USER_MANAGE') && !isSelf && user.role !== 'SUPER_ADMIN' && canAssignLevel(actor?.role, user.role) ? (
                        <Select value={user.role_key} onValueChange={(v) => v !== user.role_key && setPendingAccess({ user, role: v })}>
                          <SelectTrigger size="sm" aria-label={`Access role for ${user.full_name}`}>
                            <SelectValue>{catalog.name(user.role_key)}</SelectValue>
                          </SelectTrigger>
                          <SelectContent>
                            {catalog.assignable(actor?.role).map((role) => (
                              <SelectItem key={role.key} value={role.key}>
                                {role.name}
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
                    <TableCell>
                      {canSetRole ? (
                        <Select
                          value={current?.id}
                          onValueChange={(v) => assignRole(user.employee_id!, current, v)}
                        >
                          <SelectTrigger size="sm" aria-label={`Job role for ${user.full_name}`}>
                            <SelectValue placeholder="No job role" />
                          </SelectTrigger>
                          <SelectContent>
                            {(profiles.data ?? []).map((p) => (
                              <SelectItem key={p.id} value={p.id}>
                                {p.name}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      ) : (
                        <span className="flex items-center gap-2 text-[13px]">
                          {current?.name ?? 'No job role'}
                        </span>
                      )}
                    </TableCell>
                    <TableCell className="pr-5">
                      {!isSelf && can('USER_MANAGE') && (
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
      <ConfirmDialog
        open={Boolean(pendingAccess)}
        onOpenChange={(open) => !open && setPendingAccess(null)}
        title="Change access role?"
        description={
          <>
            {pendingAccess?.user.full_name} will become <strong>{pendingAccess ? catalog.name(pendingAccess.role) : ''}</strong>{' '}
            and see only what that role allows. Their open WorkPulse updates at once.
          </>
        }
        confirmLabel="Change access role"
        loading={changeAccess.isPending}
        onConfirm={() =>
          pendingAccess &&
          changeAccess.mutate(
            { userId: pendingAccess.user.id, role: pendingAccess.role },
            {
              onSuccess: () => {
                toast.success(`${pendingAccess.user.full_name} is now ${catalog.name(pendingAccess.role)}`)
                setPendingAccess(null)
              },
              onError: (e) => toast.error(errorMessage(e)),
            },
          )
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
        <CustomRolesCard />
        <PermissionMatrix />
        <p className="text-[12px] text-muted-foreground">
          Roles decide what each member can access. Control what each person sees on their dashboard in Settings →
          Dashboard access.
        </p>
      </div>
    </RequirePermission>
  )
}
