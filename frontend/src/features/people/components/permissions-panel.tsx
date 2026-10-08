import { useState } from 'react'
import { Check, KeyRound, Mail, ShieldCheck } from 'lucide-react'
import { toast } from 'sonner'

import { ConfirmDialog } from '@/components/common/confirm-dialog'
import { EmptyState } from '@/components/common/empty-state'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { useInviteEmployee } from '@/features/people/api'
import { AccessBadge } from '@/features/people/components/badges'
import { ACCESS_STATE, PERMISSION_INFO } from '@/features/people/meta'
import { useChangeUserRole } from '@/features/settings/api'
import { errorMessage } from '@/lib/api-client'
import { assignableRoles, formatDateTime, ROLE_LABELS } from '@/lib/format'
import { useAuthStore, usePermissions } from '@/stores/auth-store'
import type { EmployeeDetail, Permission, Role } from '@/types/api'

export function PermissionsPanel({ employee }: { employee: EmployeeDetail }) {
  const { can } = usePermissions()
  const actor = useAuthStore((s) => s.user)
  const invite = useInviteEmployee(employee.id)
  const changeRole = useChangeUserRole()
  const [pendingRole, setPendingRole] = useState<Role | null>(null)
  const account = employee.account
  const isSelf = account?.user_id === actor?.id
  const canManageUsers = can('USER_MANAGE')
  const roles = assignableRoles(actor?.role)
  const canEditRole = Boolean(account) && canManageUsers && !isSelf && account!.role !== 'SUPER_ADMIN' && roles.includes(account!.role)

  const grouped = employee.permissions.reduce<Record<string, Permission[]>>((acc, p) => {
    ;(acc[PERMISSION_INFO[p].category] ??= []).push(p)
    return acc
  }, {})

  const sendInvite = () =>
    invite.mutate(account?.role ?? 'EMPLOYEE', {
      onSuccess: () => toast.success(`Invitation sent to ${employee.email}`),
      onError: (e) => toast.error(errorMessage(e)),
    })

  return (
    <div className="grid gap-6 lg:grid-cols-[340px_minmax(0,1fr)]">
      <Card>
        <CardHeader>
          <CardTitle>Account & role</CardTitle>
          <CardDescription>{ACCESS_STATE[employee.access].description}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center justify-between text-[13px]">
            <span className="text-muted-foreground">Access</span>
            <AccessBadge access={employee.access} />
          </div>
          {account && (
            <>
              <div className="space-y-1.5">
                <span className="text-[13px] text-muted-foreground">Role</span>
                {canEditRole ? (
                  <Select value={account.role} onValueChange={(v) => setPendingRole(v as Role)}>
                    <SelectTrigger aria-label="Role">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {roles.map((role) => (
                        <SelectItem key={role} value={role}>
                          {ROLE_LABELS[role]}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                ) : (
                  <div>
                    <Badge variant="soft">{ROLE_LABELS[account.role]}</Badge>
                    {isSelf && <p className="mt-1.5 text-[12px] text-muted-foreground">You can't change your own role.</p>}
                  </div>
                )}
              </div>
              <div className="flex items-center justify-between text-[13px]">
                <span className="text-muted-foreground">Last sign-in</span>
                <span>{formatDateTime(account.last_login_at)}</span>
              </div>
            </>
          )}
          {canManageUsers && can('EMPLOYEE_MANAGE') && employee.status !== 'terminated' && (employee.access === 'none' || employee.access === 'invited') && (
            <Button variant="outline" className="w-full" loading={invite.isPending} onClick={sendInvite}>
              <Mail /> {employee.access === 'none' ? 'Invite to WorkPulse' : 'Resend invitation'}
            </Button>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Effective permissions</CardTitle>
          <CardDescription>What this person can do across the workspace, derived from their role.</CardDescription>
        </CardHeader>
        <CardContent>
          {employee.access !== 'active' ? (
            <EmptyState
              size="sm"
              icon={KeyRound}
              title="No active account"
              description="Permissions apply once the employee has an active WorkPulse account."
            />
          ) : employee.permissions.length === 0 ? (
            <EmptyState
              size="sm"
              icon={ShieldCheck}
              title="Standard member access"
              description="Employees can access their own profile and data. No workspace-wide permissions are granted."
            />
          ) : (
            <div className="grid gap-5 sm:grid-cols-2">
              {Object.entries(grouped).map(([category, permissions]) => (
                <div key={category}>
                  <p className="mb-2 text-[11px] font-semibold tracking-wide text-muted-foreground uppercase">{category}</p>
                  <ul className="space-y-1.5">
                    {permissions.map((p) => (
                      <li key={p} className="flex items-center gap-2 text-[13px]">
                        <Check className="size-3.5 text-primary" /> {PERMISSION_INFO[p].name}
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      <ConfirmDialog
        open={Boolean(pendingRole)}
        onOpenChange={(open) => !open && setPendingRole(null)}
        title="Change role?"
        description={
          <>
            {employee.full_name} will become a <strong>{pendingRole ? ROLE_LABELS[pendingRole] : ''}</strong>. The change
            takes effect immediately.
          </>
        }
        confirmLabel="Change role"
        loading={changeRole.isPending}
        onConfirm={() =>
          account &&
          pendingRole &&
          changeRole.mutate(
            { userId: account.user_id, role: pendingRole },
            {
              onSuccess: () => {
                toast.success('Role updated')
                setPendingRole(null)
              },
              onError: (e) => toast.error(errorMessage(e)),
            },
          )
        }
      />
    </div>
  )
}
