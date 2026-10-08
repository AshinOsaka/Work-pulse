import { useRef, useState } from 'react'
import { ArrowDown, ArrowUp, ArrowUpDown, ChevronDown, ListFilter, Plus, Search, SearchX, Users, X } from 'lucide-react'
import { useNavigate, useSearchParams } from 'react-router'

import { EmptyState } from '@/components/common/empty-state'
import { FilterSelect, toOptions } from '@/components/common/filter-select'
import { Pagination } from '@/components/common/pagination'
import { Person } from '@/components/common/person'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/misc'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { useDepartments, useEmployees, useManagers, useTeams } from '@/features/people/api'
import { AccessBadge, EmployeeStatusBadge } from '@/features/people/components/badges'
import { EmployeeFormDialog } from '@/features/people/components/employee-form-dialog'
import { EMPLOYEE_STATUS } from '@/features/people/meta'
import { errorMessage } from '@/lib/api-client'
import { cn } from '@/lib/utils'
import { usePermissions } from '@/stores/auth-store'
import type { EmployeeSort, EmployeeStatus } from '@/types/api'

const STATUSES = Object.keys(EMPLOYEE_STATUS) as EmployeeStatus[]
const DEFAULT_STATUSES: EmployeeStatus[] = ['active', 'on_leave']

/** Filters live in the URL so views can be bookmarked and shared. */
function useEmployeeFilters() {
  const [params, setParams] = useSearchParams()
  const statusParam = params.get('status')
  const filters = {
    search: params.get('q') ?? '',
    status: statusParam === null ? DEFAULT_STATUSES : (statusParam.split(',').filter(Boolean) as EmployeeStatus[]),
    department_id: params.get('department') ?? undefined,
    team_id: params.get('team') ?? undefined,
    manager_id: params.get('manager') ?? undefined,
    sort: (params.get('sort') as EmployeeSort | null) ?? 'full_name',
    order: (params.get('order') as 'asc' | 'desc' | null) ?? 'asc',
    page: Number(params.get('page') ?? 1) || 1,
    page_size: Number(params.get('size') ?? 25) || 25,
  }

  const update = (changes: Record<string, string | null>, resetPage = true) =>
    setParams(
      (prev) => {
        const next = new URLSearchParams(prev)
        for (const [key, value] of Object.entries(changes)) {
          if (value === null || value === '') next.delete(key)
          else next.set(key, value)
        }
        if (resetPage) next.delete('page')
        return next
      },
      { replace: true },
    )

  const activeCount =
    (statusParam !== null ? 1 : 0) + [filters.department_id, filters.team_id, filters.manager_id].filter(Boolean).length

  return { filters, update, activeCount, reset: () => setParams({}, { replace: true }) }
}

function SortHeader({
  label,
  field,
  sort,
  order,
  onSort,
  className,
}: {
  label: string
  field: EmployeeSort
  sort: EmployeeSort
  order: 'asc' | 'desc'
  onSort: (field: EmployeeSort) => void
  className?: string
}) {
  const active = sort === field
  const Icon = !active ? ArrowUpDown : order === 'asc' ? ArrowUp : ArrowDown
  return (
    <TableHead className={className} aria-sort={active ? (order === 'asc' ? 'ascending' : 'descending') : 'none'}>
      <button
        type="button"
        onClick={() => onSort(field)}
        className={cn(
          '-ml-1.5 inline-flex items-center gap-1 rounded px-1.5 py-1 uppercase transition hover:bg-accent hover:text-foreground',
          active && 'text-foreground',
        )}
      >
        {label}
        <Icon className={cn('size-3', !active && 'opacity-40')} />
      </button>
    </TableHead>
  )
}


export default function EmployeesPage() {
  const navigate = useNavigate()
  const { can } = usePermissions()
  const { filters, update, activeCount, reset } = useEmployeeFilters()
  const [search, setSearch] = useState(filters.search)
  const searchTimer = useRef<number | undefined>(undefined)
  const [createOpen, setCreateOpen] = useState(false)

  const onSearchChange = (value: string) => {
    setSearch(value)
    window.clearTimeout(searchTimer.current)
    searchTimer.current = window.setTimeout(() => update({ q: value.trim() || null }), 300)
  }
  const clearAll = () => {
    window.clearTimeout(searchTimer.current)
    setSearch('')
    reset()
  }

  const departments = useDepartments()
  const teams = useTeams()
  const managers = useManagers()
  const query = useEmployees({
    search: filters.search || undefined,
    status: filters.status,
    department_id: filters.department_id,
    team_id: filters.team_id,
    manager_id: filters.manager_id,
    sort: filters.sort,
    order: filters.order,
    page: filters.page,
    page_size: filters.page_size,
  })

  const onSort = (field: EmployeeSort) => {
    const order = filters.sort === field && filters.order === 'asc' ? 'desc' : 'asc'
    update({ sort: field, order }, false)
  }

  const toggleStatus = (status: EmployeeStatus, checked: boolean) => {
    const next = checked ? [...filters.status, status] : filters.status.filter((s) => s !== status)
    update({ status: next.join(',') || STATUSES.join(',') })
  }

  const teamOptions = (teams.data ?? []).filter(
    (t) => !filters.department_id || t.department?.id === filters.department_id,
  )
  const data = query.data
  const filtered = Boolean(filters.search) || activeCount > 0

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-center">
        <div className="relative lg:w-72">
          <Search className="absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={search}
            onChange={(e) => onSearchChange(e.target.value)}
            placeholder="Search name, email, ID or title"
            className="h-8 pl-8 text-[13px]"
            aria-label="Search employees"
          />
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="outline" size="sm" className="font-normal">
                <ListFilter /> Status
                <span className="rounded bg-muted px-1 text-[11px] tabular">{filters.status.length}</span>
                <ChevronDown className="opacity-50" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="start" className="w-48">
              <DropdownMenuLabel className="text-[12px] text-muted-foreground">Employment status</DropdownMenuLabel>
              <DropdownMenuSeparator />
              {STATUSES.map((status) => (
                <DropdownMenuCheckboxItem
                  key={status}
                  checked={filters.status.includes(status)}
                  onCheckedChange={(checked) => toggleStatus(status, checked)}
                  onSelect={(e) => e.preventDefault()}
                >
                  {EMPLOYEE_STATUS[status].label}
                </DropdownMenuCheckboxItem>
              ))}
            </DropdownMenuContent>
          </DropdownMenu>
          <FilterSelect
            label="Department"
            value={filters.department_id}
            onChange={(v) => update({ department: v, team: null })}
            options={toOptions(departments.data)}
            allLabel="All departments"
            className="sm:w-auto sm:min-w-36"
          />
          <FilterSelect
            label="Team"
            value={filters.team_id}
            onChange={(v) => update({ team: v })}
            options={toOptions(teamOptions)}
            allLabel="All teams"
            className="sm:w-auto sm:min-w-36"
          />
          <FilterSelect
            label="Manager"
            value={filters.manager_id}
            onChange={(v) => update({ manager: v })}
            options={(managers.data ?? []).map((m) => ({ value: m.id, label: m.full_name }))}
            allLabel="All managers"
            className="sm:w-auto sm:min-w-36"
          />
          {filtered && (
            <Button
              variant="ghost"
              size="sm"
              onClick={clearAll}
            >
              <X /> Reset
            </Button>
          )}
        </div>
        {can('EMPLOYEE_MANAGE') && (
          <Button size="sm" className="lg:ml-auto" onClick={() => setCreateOpen(true)}>
            <Plus /> Add employee
          </Button>
        )}
      </div>

      <Card className="overflow-hidden">
        <Table>
          <TableHeader>
            <TableRow className="hover:bg-transparent">
              <SortHeader label="Employee" field="full_name" sort={filters.sort} order={filters.order} onSort={onSort} className="pl-4" />
              <SortHeader label="Title" field="job_title" sort={filters.sort} order={filters.order} onSort={onSort} />
              <TableHead>Department / Team</TableHead>
              <TableHead>Manager</TableHead>
              <SortHeader label="Status" field="status" sort={filters.sort} order={filters.order} onSort={onSort} />
              <TableHead>Access</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody className={cn(query.isPlaceholderData && 'opacity-60 transition-opacity')}>
            {query.isPending &&
              Array.from({ length: 6 }, (_, i) => (
                <TableRow key={i}>
                  <TableCell className="pl-4">
                    <div className="flex items-center gap-2.5">
                      <Skeleton className="size-8 rounded-full" />
                      <div className="space-y-1.5">
                        <Skeleton className="h-3 w-32" />
                        <Skeleton className="h-2.5 w-44" />
                      </div>
                    </div>
                  </TableCell>
                  {Array.from({ length: 5 }, (__, j) => (
                    <TableCell key={j}>
                      <Skeleton className="h-3 w-20" />
                    </TableCell>
                  ))}
                </TableRow>
              ))}
            {data?.items.map((employee) => (
              <TableRow
                key={employee.id}
                className="cursor-pointer"
                onClick={(e) => {
                  if (!(e.target as HTMLElement).closest('a')) navigate(`/people/employees/${employee.id}`)
                }}
              >
                <TableCell className="max-w-64 pl-4">
                  <Person id={employee.id} name={employee.full_name} subtitle={employee.email} />
                </TableCell>
                <TableCell className="max-w-48 truncate text-muted-foreground">{employee.job_title ?? '—'}</TableCell>
                <TableCell className="max-w-52">
                  <span className="block truncate">{employee.department?.name ?? '—'}</span>
                  {employee.team && <span className="block truncate text-[12px] text-muted-foreground">{employee.team.name}</span>}
                </TableCell>
                <TableCell className="max-w-44">
                  {employee.manager ? (
                    <Person id={employee.manager.id} name={employee.manager.full_name} size="sm" />
                  ) : (
                    <span className="text-muted-foreground">—</span>
                  )}
                </TableCell>
                <TableCell>
                  <EmployeeStatusBadge status={employee.status} />
                </TableCell>
                <TableCell>
                  <AccessBadge access={employee.access} />
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>

        {query.isError && (
          <EmptyState
            icon={SearchX}
            title="Couldn't load employees"
            description={errorMessage(query.error)}
            action={
              <Button size="sm" variant="outline" onClick={() => query.refetch()}>
                Try again
              </Button>
            }
          />
        )}
        {data && data.total === 0 &&
          (filtered ? (
            <EmptyState
              icon={SearchX}
              title="No employees match these filters"
              description="Try a different search term or clear the filters."
              action={
                <Button
                  size="sm"
                  variant="outline"
                  onClick={clearAll}
                >
                  Clear filters
                </Button>
              }
            />
          ) : (
            <EmptyState
              icon={Users}
              title="No employees yet"
              description="Add the people in your organisation to start building your directory."
              action={
                can('EMPLOYEE_MANAGE') && (
                  <Button size="sm" onClick={() => setCreateOpen(true)}>
                    <Plus /> Add employee
                  </Button>
                )
              }
            />
          ))}
        {data && data.total > 0 && (
          <div className="border-t">
            <Pagination
              page={data.page}
              pages={data.pages}
              pageSize={data.page_size}
              total={data.total}
              onPageChange={(page) => update({ page: String(page) }, false)}
              onPageSizeChange={(size) => update({ size: String(size) })}
            />
          </div>
        )}
      </Card>

      <EmployeeFormDialog
        open={createOpen}
        onOpenChange={setCreateOpen}
        onSaved={(employee) => navigate(`/people/employees/${employee.id}`)}
      />
    </div>
  )
}
