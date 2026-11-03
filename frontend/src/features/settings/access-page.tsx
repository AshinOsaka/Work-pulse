import { useRef, useState } from 'react'
import { MonitorCog, Search, SlidersHorizontal, UsersRound } from 'lucide-react'
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
import { useEmployee, useSetEmployeeAccess } from '@/features/people/api'
import { useChangeUserRole, useUsers } from '@/features/settings/api'
import { useWorkProfiles } from '@/features/productivity/api'
import { useRoleCatalog } from '@/hooks/use-role-catalog'
import { errorMessage } from '@/lib/api-client'
import { canAssignLevel } from '@/lib/format'
import { cn } from '@/lib/utils'
import { useAuthStore } from '@/stores/auth-store'
import type { EmployeeDetail } from '@/types/api'

const ALL = '__all__'
const serialise = (keys: Iterable<string>) => [...keys].sort().join('|')

type Picked = { employeeId: string; name: string }

/** The switches for one selected person: on = section visible, off = hidden from their dashboard. */
function AccessEditor({ employee }: { employee: EmployeeDetail }) {
  const me = useAuthStore((s) => s.user?.id)
  const actorRole = useAuthStore((s) => s.user?.role)
  const account = employee.account
  const save = useSetEmployeeAccess(employee.id)
  const changeRole = useChangeUserRole()
  const catalog = useRoleCatalog()
  const [hidden, setHidden] = useState<Set<string>>(() => new Set(employee.hidden_sections))
  const [pendingRole, setPendingRole] = useState<string | null>(null)

  const dirty = serialise(hidden) !== serialise(employee.hidden_sections)
  const isSelf = me === account?.user_id
  const assignable = catalog.assignable(actorRole)
  const canEditRole = Boolean(account) && !isSelf && account!.role !== 'SUPER_ADMIN' && canAssignLevel(actorRole, account!.role)

  const toggle = (key: string, visible: boolean) =>
    setHidden((prev) => {
      const next = new Set(prev)
      if (visible) next.delete(key)
      else next.add(key)
      return next
    })

  if (!account) {
    return (
      <EmptyState
        size="sm"
        icon={MonitorCog}
        title="No account yet"
        description="This person hasn't been invited to WorkPulse, so there's no dashboard to configure. Invite them from their profile first."
      />
    )
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-3 rounded-lg border px-4 py-3">
        <div className="min-w-0">
          <p className="text-[13px] font-medium">Role</p>
          <p className="text-[12px] text-muted-foreground">Sets their default access across the workspace.</p>
        </div>
        {canEditRole ? (
          <Select value={account.role_key} onValueChange={(v) => setPendingRole(v)}>
            <SelectTrigger size="sm" className="w-44" aria-label={`Role for ${employee.full_name}`}>
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
          <Badge variant="soft">
            {catalog.name(account.role_key)}
            {isSelf && ' (you)'}
          </Badge>
        )}
      </div>

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
                aria-label={`${section.label} visible to ${employee.full_name}`}
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
              onSuccess: () => toast.success(`Dashboard updated for ${employee.full_name}`),
              onError: (e) => toast.error(errorMessage(e)),
            })
          }
        >
          Save changes
        </Button>
      </div>

      <ConfirmDialog
        open={Boolean(pendingRole)}
        onOpenChange={(open) => !open && setPendingRole(null)}
        title="Change login role?"
        description={
          pendingRole ? (
            <>
              <strong>{employee.full_name}</strong> will change from {catalog.name(account.role_key)} to{' '}
              <strong>{catalog.name(pendingRole)}</strong>. This changes their default access and takes effect on their
              next request.
            </>
          ) : null
        }
        confirmLabel="Change role"
        loading={changeRole.isPending}
        onConfirm={() =>
          pendingRole &&
          changeRole.mutate(
            { userId: account.user_id, role: pendingRole },
            {
              onSuccess: () => {
                toast.success(`${employee.full_name} is now ${catalog.name(pendingRole)}`)
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

/** Loads the full employee record for the chosen person, then renders the editor. */
function SelectedEditor({ employeeId }: { employeeId: string }) {
  const query = useEmployee(employeeId)
  if (query.isPending) {
    return (
      <div className="space-y-2">
        {Array.from({ length: 6 }, (_, i) => (
          <Skeleton key={i} className="h-10" />
        ))}
      </div>
    )
  }
  if (query.isError || !query.data) {
    return <EmptyState size="sm" icon={MonitorCog} title="Couldn't load this person" description={errorMessage(query.error)} />
  }
  return <AccessEditor employee={query.data} />
}

function DashboardAccess() {
  const [search, setSearch] = useState('')
  const [query, setQuery] = useState('')
  const [profileId, setProfileId] = useState<string>(ALL)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(10)
  const [selected, setSelected] = useState<Picked | null>(null)
  const timer = useRef<number | undefined>(undefined)

  const isAll = profileId === ALL
  const profiles = useWorkProfiles()
  const catalog = useRoleCatalog()
  const users = useUsers({ search: query || undefined, page, page_size: pageSize })

  const onSearch = (value: string) => {
    setSearch(value)
    window.clearTimeout(timer.current)
    timer.current = window.setTimeout(() => {
      setQuery(value.trim())
      setPage(1)
    }, 300)
  }

  const profileOptions = (profiles.data ?? []).map((p) => ({ value: p.id, label: `${p.name} (${p.members.length})` }))
  const activeProfile = isAll ? null : profiles.data?.find((p) => p.id === profileId)

  // People shown: everyone (accounts) for "All people", or the chosen job role's members.
  const term = query.toLowerCase()
  const rows: { key: string; employeeId: string | null; name: string; subtitle: string; hidden?: number }[] = isAll
    ? (users.data?.items ?? []).map((u) => ({
        key: u.id,
        employeeId: u.employee_id,
        name: u.full_name,
        subtitle: catalog.name(u.role_key),
        hidden: u.hidden_sections.length,
      }))
    : (activeProfile?.members ?? [])
        .filter((m) => !term || m.full_name.toLowerCase().includes(term) || m.email.toLowerCase().includes(term))
        .map((m) => ({ key: m.id, employeeId: m.id, name: m.full_name, subtitle: m.job_title ?? 'No job title' }))

  const loading = isAll ? users.isPending : profiles.isPending
  const errored = isAll ? users.isError : profiles.isError

  const pick = (row: { employeeId: string | null; name: string }) => {
    if (!row.employeeId) {
      toast.error("This account isn't linked to an employee, so there's no dashboard to configure.")
      return
    }
    setSelected({ employeeId: row.employeeId, name: row.name })
  }

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
            value={isAll ? null : profileId}
            onChange={(v) => {
              setProfileId(v ?? ALL)
              setPage(1)
            }}
            options={profileOptions}
            allLabel="All people"
          />
        </div>
        {loading ? (
          <div className="space-y-2 p-5">
            {Array.from({ length: 5 }, (_, i) => (
              <Skeleton key={i} className="h-11" />
            ))}
          </div>
        ) : errored ? (
          <EmptyState icon={UsersRound} title="Couldn't load people" description={errorMessage(isAll ? users.error : profiles.error)} />
        ) : rows.length === 0 ? (
          <EmptyState
            icon={UsersRound}
            title="No people found"
            description={isAll ? 'Try a different search.' : 'Nobody is assigned to this job role yet. Assign members under People → Job roles.'}
          />
        ) : (
          <>
            <ul className="divide-y">
              {rows.map((row) => (
                <li key={row.key}>
                  <button
                    type="button"
                    onClick={() => pick(row)}
                    className={cn(
                      'flex w-full items-center gap-3 px-5 py-2.5 text-left transition hover:bg-subtle/60',
                      selected?.employeeId === row.employeeId && 'bg-primary-soft/40',
                    )}
                  >
                    <PersonAvatar name={row.name} seed={row.employeeId ?? row.key} className="size-8 text-[11px]" />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-[13px] font-medium">{row.name}</span>
                      <span className="block truncate text-[12px] text-muted-foreground">{row.subtitle}</span>
                    </span>
                    {row.hidden ? <span className="shrink-0 text-[11px] text-muted-foreground">{row.hidden} hidden</span> : null}
                  </button>
                </li>
              ))}
            </ul>
            {isAll && users.data && (
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
      </Card>

      <Card className="overflow-hidden">
        <CardHeader className="pb-4">
          <CardTitle>Dashboard sections</CardTitle>
          <CardDescription>
            {selected
              ? `What ${selected.name} sees on their dashboard. Turning a section off only hides it for them — it never changes their role, permissions or what the system records.`
              : 'Select a person to show or hide sections of their dashboard.'}
          </CardDescription>
        </CardHeader>
        <CardContent>
          {selected ? (
            <SelectedEditor key={selected.employeeId} employeeId={selected.employeeId} />
          ) : (
            <EmptyState size="sm" icon={SlidersHorizontal} title="Nobody selected" description="Pick a person on the left to begin." />
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
