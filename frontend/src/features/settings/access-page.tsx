import { useMemo, useRef, useState } from 'react'
import { MonitorCog, Search, SlidersHorizontal, UsersRound } from 'lucide-react'
import { toast } from 'sonner'

import { EmptyState } from '@/components/common/empty-state'
import { FilterSelect } from '@/components/common/filter-select'
import { Pagination } from '@/components/common/pagination'
import { PersonAvatar } from '@/components/common/person'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Switch } from '@/components/ui/form-controls'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/misc'
import { SECTIONS } from '@/config/sections'
import { RequirePermission } from '@/features/auth/guards'
import { useSetEmployeeAccess } from '@/features/people/api'
import { useUsers } from '@/features/settings/api'
import { errorMessage } from '@/lib/api-client'
import { ROLE_LABELS } from '@/lib/format'
import { cn } from '@/lib/utils'
import { useAuthStore } from '@/stores/auth-store'
import type { Role, UserAdmin } from '@/types/api'

const ALL = '__all__'
const serialise = (keys: Iterable<string>) => [...keys].sort().join('|')

/** The switches for one selected person: on = section visible, off = hidden from their dashboard. */
function AccessEditor({ member, onSaved }: { member: UserAdmin; onSaved: (hidden: string[]) => void }) {
  const me = useAuthStore((s) => s.user?.id)
  const save = useSetEmployeeAccess(member.employee_id ?? '')
  const [hidden, setHidden] = useState<Set<string>>(() => new Set(member.hidden_sections))

  // Re-seed when a different member is chosen (the key prop below remounts, so this runs fresh).
  const dirty = serialise(hidden) !== serialise(member.hidden_sections)
  const isSelf = me === member.id

  const toggle = (key: string, visible: boolean) =>
    setHidden((prev) => {
      const next = new Set(prev)
      if (visible) next.delete(key)
      else next.add(key)
      return next
    })

  if (!member.employee_id) {
    return (
      <EmptyState
        size="sm"
        icon={MonitorCog}
        title="Not an employee account"
        description="This account isn't linked to an employee, so there's no employee dashboard to configure."
      />
    )
  }

  return (
    <div className="space-y-4">
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
              : 'Select a person to show or hide sections of their dashboard.'}
          </CardDescription>
        </CardHeader>
        <CardContent>
          {selected ? (
            <AccessEditor
              key={selected.id}
              member={selected}
              onSaved={(hidden) => setSelected((prev) => (prev ? { ...prev, hidden_sections: hidden } : prev))}
            />
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
