import { useMemo, useRef, useState } from 'react'
import { Check, MonitorCog, Search, ShieldCheck, SlidersHorizontal, UsersRound } from 'lucide-react'
import { toast } from 'sonner'

import { ConfirmDialog } from '@/components/common/confirm-dialog'
import { EmptyState } from '@/components/common/empty-state'
import { FilterSelect } from '@/components/common/filter-select'
import { Pagination } from '@/components/common/pagination'
import { PersonAvatar } from '@/components/common/person'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Switch } from '@/components/ui/form-controls'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/misc'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { SECTIONS } from '@/config/sections'
import { RequirePermission } from '@/features/auth/guards'
import { useSetEmployeeAccess } from '@/features/people/api'
import { PERMISSION_INFO } from '@/features/people/meta'
import { useChangeUserRole, useUsers } from '@/features/settings/api'
import { useRoles } from '@/hooks/use-system'
import { errorMessage } from '@/lib/api-client'
import { assignableRoles, ROLE_LABELS } from '@/lib/format'
import { cn } from '@/lib/utils'
import { useAuthStore } from '@/stores/auth-store'
import type { Permission, Role, UserAdmin } from '@/types/api'

const ALL = '__all__'
const serialise = (keys: Iterable<string>) => [...keys].sort().join('|')

/** The switches for one selected person: on = section visible, off = hidden from their dashboard. */
function AccessEditor({
  member,
  onSaved,
  onRoleChanged,
}: {
  member: UserAdmin
  onSaved: (hidden: string[]) => void
  onRoleChanged: (role: Role) => void
}) {
  const me = useAuthStore((s) => s.user?.id)
  const actorRole = useAuthStore((s) => s.user?.role)
  const save = useSetEmployeeAccess(member.employee_id ?? '')
  const changeRole = useChangeUserRole()
  const [hidden, setHidden] = useState<Set<string>>(() => new Set(member.hidden_sections))
  const [pendingRole, setPendingRole] = useState<Role | null>(null)

  // Re-seed when a different member is chosen (the key prop below remounts, so this runs fresh).
  const dirty = serialise(hidden) !== serialise(member.hidden_sections)
  const isSelf = me === member.id
  const assignable = assignableRoles(actorRole)
  const canEditRole = !isSelf && member.role !== 'SUPER_ADMIN' && assignable.includes(member.role)

  const toggle = (key: string, visible: boolean) =>
    setHidden((prev) => {
      const next = new Set(prev)
      if (visible) next.delete(key)
      else next.add(key)
      return next
    })

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-3 rounded-lg border px-4 py-3">
        <div className="min-w-0">
          <p className="text-[13px] font-medium">Role</p>
          <p className="text-[12px] text-muted-foreground">Sets their default access across the workspace.</p>
        </div>
        {canEditRole ? (
          <Select value={member.role} onValueChange={(v) => setPendingRole(v as Role)}>
            <SelectTrigger size="sm" className="w-44" aria-label={`Role for ${member.full_name}`}>
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
          <Badge variant="soft">
            {ROLE_LABELS[member.role]}
            {isSelf && ' (you)'}
          </Badge>
        )}
      </div>

      {!member.employee_id ? (
        <EmptyState
          size="sm"
          icon={MonitorCog}
          title="Not an employee account"
          description="This account isn't linked to an employee, so there's no employee dashboard to configure."
        />
      ) : (
        <>
      <ul className="divide-y rounded-lg border">
        {SECTIONS.map((section) => {
          const visible = !hidden.has(section.key)
          return (
            <li key={section.key} className="flex items-center justify-between gap-3 px-4 py-3">
              <div className="min-w-0">
                <p className="text-[13px] font-medium">{section.label}</p>
                <p className="text-[12px] text-muted-foreground">{section.hint}</p>
              </div>
              <Switch
                checked={visible}
                onCheckedChange={(v) => toggle(section.key, v)}
                aria-label={`${section.label} visible to ${member.full_name}`}
              />
            </li>
          )
        })}
      </ul>
      <div className="flex items-center justify-between gap-3">
        <p className="text-[12px] text-muted-foreground">
          {isSelf ? 'Changes to your own view apply after you refresh.' : 'Applies on their next sign-in or refresh.'}
        </p>
        <Button
          size="sm"
          disabled={!dirty}
          loading={save.isPending}
          onClick={() =>
            save.mutate([...hidden], {
              onSuccess: (detail) => {
                onSaved(detail.hidden_sections)
                toast.success(`Dashboard updated for ${member.full_name}`)
              },
              onError: (e) => toast.error(errorMessage(e)),
            })
          }
        >
          Save changes
        </Button>
      </div>
        </>
      )}

      <ConfirmDialog
        open={Boolean(pendingRole)}
        onOpenChange={(open) => !open && setPendingRole(null)}
        title="Change role?"
        description={
          pendingRole ? (
            <>
              <strong>{member.full_name}</strong> will change from {ROLE_LABELS[member.role]} to{' '}
              <strong>{ROLE_LABELS[pendingRole]}</strong>. This changes their default access and takes effect on
              their next request.
            </>
          ) : null
        }
        confirmLabel="Change role"
        loading={changeRole.isPending}
        onConfirm={() =>
          pendingRole &&
          changeRole.mutate(
            { userId: member.id, role: pendingRole },
            {
              onSuccess: () => {
                onRoleChanged(pendingRole)
                toast.success(`${member.full_name} is now ${ROLE_LABELS[pendingRole]}`)
                setPendingRole(null)
              },
              onError: (e) => {
                toast.error(errorMessage(e))
                setPendingRole(null)
              },
            },
          )
        }
      />
    </div>
  )
}

/** What a role can access by default — shown when a role is selected but no individual yet. */
function RolePermissions({ role }: { role: Role }) {
  const roles = useRoles()
  const info = roles.data?.roles.find((r) => r.key === role)

  if (roles.isPending) {
    return (
      <div className="space-y-2">
        {Array.from({ length: 5 }, (_, i) => (
          <Skeleton key={i} className="h-5" />
        ))}
      </div>
    )
  }
  if (!info) {
    return <EmptyState size="sm" icon={ShieldCheck} title="Role unavailable" description="Couldn't load this role's permissions." />
  }

  const grouped = info.permissions.reduce<Record<string, Permission[]>>((acc, p) => {
    ;(acc[PERMISSION_INFO[p].category] ??= []).push(p)
    return acc
  }, {})

  return (
    <div className="space-y-4">
      <p className="text-[13px] text-muted-foreground">
        What a <span className="font-medium text-foreground">{info.name}</span> can access by default. This applies to
        everyone with the role — pick a person on the left to customise what they see.
      </p>
      {info.permissions.length === 0 ? (
        <EmptyState
          size="sm"
          icon={ShieldCheck}
          title="Standard member access"
          description="Employees have no workspace-wide permissions. They see their own profile and data — activity, productivity and screenshots — which you can hide per person."
        />
      ) : (
        <div className="grid gap-5 sm:grid-cols-2">
          {Object.entries(grouped).map(([category, perms]) => (
            <div key={category}>
              <p className="mb-2 text-[11px] font-semibold tracking-wide text-muted-foreground uppercase">{category}</p>
              <ul className="space-y-1.5">
                {perms.map((p) => (
                  <li key={p} className="flex items-center gap-2 text-[13px]">
                    <Check className="size-3.5 text-primary" /> {PERMISSION_INFO[p].name}
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function DashboardAccess() {
  const [search, setSearch] = useState('')
  const [query, setQuery] = useState('')
  const [role, setRole] = useState<string>(ALL)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(10)
  const [selected, setSelected] = useState<UserAdmin | null>(null)
  const timer = useRef<number | undefined>(undefined)
  const users = useUsers({ search: query || undefined, role: role === ALL ? undefined : (role as Role), page, page_size: pageSize })

  const onSearch = (value: string) => {
    setSearch(value)
    window.clearTimeout(timer.current)
    timer.current = window.setTimeout(() => {
      setQuery(value.trim())
      setPage(1)
    }, 300)
  }

  const roleOptions = useMemo(() => (Object.keys(ROLE_LABELS) as Role[]).map((r) => ({ value: r, label: ROLE_LABELS[r] })), [])

  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)]">
      <Card className="overflow-hidden">
        <CardHeader className="pb-4">
          <CardTitle>Choose a person</CardTitle>
          <CardDescription>Filter by role, then pick who to configure.</CardDescription>
        </CardHeader>
        <div className="flex flex-col gap-2 border-t px-5 py-3 sm:flex-row">
          <div className="relative sm:w-56">
            <Search className="absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input value={search} onChange={(e) => onSearch(e.target.value)} placeholder="Search people" className="h-8 pl-8 text-[13px]" aria-label="Search people" />
          </div>
          <FilterSelect
            label="Filter by role"
            value={role === ALL ? null : role}
            onChange={(v) => {
              setRole(v ?? ALL)
              setPage(1)
            }}
            options={roleOptions}
            allLabel="All roles"
          />
        </div>
        {users.isPending ? (
          <div className="space-y-2 p-5">
            {Array.from({ length: 5 }, (_, i) => (
              <Skeleton key={i} className="h-11" />
            ))}
          </div>
        ) : users.isError ? (
          <EmptyState icon={UsersRound} title="Couldn't load people" description={errorMessage(users.error)} />
        ) : users.data.total === 0 ? (
          <EmptyState icon={UsersRound} title="No people found" description="Try a different search or role filter." />
        ) : (
          <>
            <ul className="divide-y">
              {users.data.items.map((user) => (
                <li key={user.id}>
                  <button
                    type="button"
                    onClick={() => setSelected(user)}
                    className={cn(
                      'flex w-full items-center gap-3 px-5 py-2.5 text-left transition hover:bg-subtle/60',
                      selected?.id === user.id && 'bg-primary-soft/40',
                    )}
                  >
                    <PersonAvatar name={user.full_name} seed={user.employee_id ?? user.id} className="size-8 text-[11px]" />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-[13px] font-medium">{user.full_name}</span>
                      <span className="block truncate text-[12px] text-muted-foreground">{ROLE_LABELS[user.role]}</span>
                    </span>
                    {user.hidden_sections.length > 0 && (
                      <span className="shrink-0 text-[11px] text-muted-foreground">{user.hidden_sections.length} hidden</span>
                    )}
                  </button>
                </li>
              ))}
            </ul>
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
      </Card>

      <Card className="overflow-hidden">
        <CardHeader className="pb-4">
          <CardTitle>Dashboard sections</CardTitle>
          <CardDescription>
            {selected
              ? `What ${selected.full_name} sees on their dashboard. Turning a section off only hides it for them — it never changes their role, permissions or what the system records.`
              : role !== ALL
                ? `Default access for the ${ROLE_LABELS[role as Role]} role.`
                : 'Select a role to see its access, or a person to show or hide sections of their dashboard.'}
          </CardDescription>
        </CardHeader>
        <CardContent>
          {selected ? (
            <AccessEditor
              key={selected.id}
              member={selected}
              onSaved={(hidden) => setSelected((prev) => (prev ? { ...prev, hidden_sections: hidden } : prev))}
              onRoleChanged={(r) => setSelected((prev) => (prev ? { ...prev, role: r } : prev))}
            />
          ) : role !== ALL ? (
            <RolePermissions role={role as Role} />
          ) : (
            <EmptyState size="sm" icon={SlidersHorizontal} title="Nothing selected" description="Pick a role to see its access, or a person on the left to begin." />
          )}
        </CardContent>
      </Card>
    </div>
  )
}

export default function AccessPage() {
  return (
    <RequirePermission permission="USER_MANAGE">
      <DashboardAccess />
    </RequirePermission>
  )
}
