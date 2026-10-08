import { Fragment, useRef, useState } from 'react'
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
import { useResetUserMfa, useRevokeUserSessions } from '@/features/security/api'
import { useChangeUserRole, useUsers } from '@/features/settings/api'
import { useRoles } from '@/hooks/use-system'
import { errorMessage } from '@/lib/api-client'
import { assignableRoles, formatDateTime, ROLE_LABELS } from '@/lib/format'
import { useAuthStore } from '@/stores/auth-store'
import type { PermissionInfo, Role, UserAdmin } from '@/types/api'

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
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(25)
  const [pending, setPending] = useState<{ user: UserAdmin; role: Role } | null>(null)
  const [access, setAccess] = useState<{ user: UserAdmin; action: 'sessions' | 'mfa' } | null>(null)
  const revokeSessions = useRevokeUserSessions()
  const resetMfa = useResetUserMfa()
  const timer = useRef<number | undefined>(undefined)
  const users = useUsers({ search: query || undefined, role: role === ALL ? undefined : (role as Role), page, page_size: pageSize })
  const changeRole = useChangeUserRole()
  const assignable = assignableRoles(actor?.role)

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
          options={(Object.keys(ROLE_LABELS) as Role[]).map((r) => ({ value: r, label: ROLE_LABELS[r] }))}
          allLabel="All roles"
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
      ) : users.data.total === 0 ? (
        <EmptyState icon={UsersRound} title="No members found" description="Try a different search or role filter." />
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
              {users.data.items.map((user) => {
                const isSelf = user.id === actor?.id
                const editable = !isSelf && assignable.includes(user.role)
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
                        <Select value={user.role} onValueChange={(v) => setPending({ user, role: v as Role })}>
                          <SelectTrigger size="sm" aria-label={`Role for ${user.full_name}`}>
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            {assignable.map((r) => (
                              <SelectItem key={r} value={r}>
                                {ROLE_LABELS[r]}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      ) : (
                        <span className="flex items-center gap-2 text-[13px]">
                          {ROLE_LABELS[user.role]}
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
        </>
      )}
      <ConfirmDialog
        open={Boolean(pending)}
        onOpenChange={(open) => !open && setPending(null)}
        title="Change role?"
        description={
          pending && (
            <>
              <strong>{pending.user.full_name}</strong> will change from {ROLE_LABELS[pending.user.role]} to{' '}
              <strong>{ROLE_LABELS[pending.role]}</strong>. Their permissions update on their next request.
            </>
          )
        }
        confirmLabel="Change role"
        loading={changeRole.isPending}
        onConfirm={() =>
          pending &&
          changeRole.mutate(
            { userId: pending.user.id, role: pending.role },
            {
              onSuccess: () => {
                toast.success(`${pending.user.full_name} is now ${ROLE_LABELS[pending.role]}`)
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

export default function RolesPage() {
  return (
    <RequirePermission permission="USER_MANAGE">
      <div className="space-y-6">
        <Members />
        <PermissionMatrix />
        <p className="text-[12px] text-muted-foreground">
          Custom roles with tailored permission sets are planned for a later phase; today every member holds one of the
          five system roles above.
        </p>
      </div>
    </RequirePermission>
  )
}
