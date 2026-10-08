import { useMemo, useState } from 'react'
import { Activity, AppWindow, Laptop, Monitor, Moon, PowerOff, Search, UsersRound, type LucideIcon } from 'lucide-react'

import { EmptyState } from '@/components/common/empty-state'
import { Person } from '@/components/common/person'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/misc'
import { SegmentedControl } from '@/components/ui/segmented-control'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { WidgetCard, WidgetError, WidgetUnavailable } from '@/features/dashboard/components/widget'
import type { AppCategory, LiveEmployee, PresenceStatus } from '@/features/dashboard/data/types'
import { useNow } from '@/hooks/use-now'
import { formatDuration } from '@/lib/format'
import { cn } from '@/lib/utils'

const STATUS: Record<PresenceStatus, { label: string; icon: LucideIcon; color: string; order: number }> = {
  active: { label: 'Active', icon: Activity, color: 'var(--presence-active)', order: 0 },
  idle: { label: 'Idle', icon: Moon, color: 'var(--presence-idle)', order: 1 },
  offline: { label: 'Offline', icon: PowerOff, color: 'var(--presence-offline)', order: 2 },
}

const CATEGORY: Record<AppCategory, { label: string; className: string }> = {
  productive: { label: 'Productive', className: 'bg-success-soft text-success' },
  neutral: { label: 'Neutral', className: 'bg-muted text-muted-foreground' },
  unproductive: { label: 'Unproductive', className: 'bg-warning-soft text-warning' },
}

type Filter = 'all' | PresenceStatus
const PAGE = 8

export function PresenceStatusLabel({ status }: { status: PresenceStatus }) {
  const meta = STATUS[status]
  const Icon = meta.icon
  return (
    <span className="inline-flex items-center gap-1.5 whitespace-nowrap">
      <span className="flex size-5 items-center justify-center rounded-full" style={{ background: `color-mix(in oklch, ${meta.color} 18%, transparent)` }}>
        <Icon className="size-3" style={{ color: meta.color }} aria-hidden />
      </span>
      {meta.label}
    </span>
  )
}

interface LiveEmployeesCardProps {
  data: LiveEmployee[] | undefined
  isPending: boolean
  isError: boolean
  error: unknown
  isRefreshing: boolean
  onRetry: () => void
  available: boolean
  sample: boolean
}

export function LiveEmployeesCard({ data, isPending, isError, error, isRefreshing, onRetry, available, sample }: LiveEmployeesCardProps) {
  const now = useNow(1000)
  const [filter, setFilter] = useState<Filter>('all')
  const [search, setSearch] = useState('')
  const [expanded, setExpanded] = useState(false)

  const counts = useMemo(() => {
    const result = { all: 0, active: 0, idle: 0, offline: 0 }
    data?.forEach((e) => {
      result.all += 1
      result[e.status] += 1
    })
    return result
  }, [data])

  const rows = useMemo(() => {
    const term = search.trim().toLowerCase()
    return (data ?? [])
      .filter((e) => filter === 'all' || e.status === filter)
      .filter((e) => !term || e.person.name.toLowerCase().includes(term) || e.teamName.toLowerCase().includes(term))
      .sort((a, b) => STATUS[a.status].order - STATUS[b.status].order || a.since.localeCompare(b.since))
  }, [data, filter, search])

  const visible = expanded ? rows : rows.slice(0, PAGE)
  const hasData = available && data && data.length > 0

  return (
    <WidgetCard
      title="Live employees"
      description="Current status, application and task for each person"
      sample={sample}
      refreshing={isRefreshing}
      className="xl:col-span-3"
    >
      {isError ? (
        <WidgetError error={error} onRetry={onRetry} />
      ) : isPending ? (
        <div className="space-y-2 p-5">
          {Array.from({ length: 6 }, (_, i) => (
            <Skeleton key={i} className="h-11" />
          ))}
        </div>
      ) : !hasData ? (
        <WidgetUnavailable
          icon={Monitor}
          title="No live employee data yet"
          description="Each person's status, session time and device appear here once they sign in to the WorkPulse desktop agent."
          phase={4}
        />
      ) : (
        <>
          <div className="flex flex-col gap-2 px-5 pt-3 pb-3 sm:flex-row sm:items-center sm:justify-between">
            <SegmentedControl<Filter>
              size="sm"
              label="Filter by status"
              value={filter}
              onChange={(v) => {
                setFilter(v)
                setExpanded(false)
              }}
              options={[
                { value: 'all', label: `All ${counts.all}` },
                { value: 'active', label: `Active ${counts.active}` },
                { value: 'idle', label: `Idle ${counts.idle}` },
                { value: 'offline', label: `Offline ${counts.offline}` },
              ]}
            />
            <div className="relative sm:w-60">
              <Search className="absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2 text-muted-foreground" />
              <Input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Find a person or team"
                className="h-7 pl-8 text-[12px]"
                aria-label="Search live employees"
              />
            </div>
          </div>
          {rows.length === 0 ? (
            <EmptyState size="sm" icon={UsersRound} title="Nobody matches" description="Try another status or search term." className="border-t" />
          ) : (
            <Table>
              <caption className="sr-only">Live employee status</caption>
              <TableHeader>
                <TableRow className="hover:bg-transparent">
                  <TableHead className="pl-5">Employee</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Current application</TableHead>
                  <TableHead className="hidden lg:table-cell">Current task</TableHead>
                  <TableHead className="text-right">Duration</TableHead>
                  <TableHead className="hidden pr-5 md:table-cell">Device</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {visible.map((employee) => (
                  <TableRow key={employee.person.id} className="transition-colors">
                    <TableCell className="max-w-56 pl-5">
                      <Person
                        id={employee.person.employeeId ?? employee.person.id}
                        name={employee.person.name}
                        subtitle={`${employee.title} · ${employee.teamName}`}
                        link={Boolean(employee.person.employeeId)}
                      />
                    </TableCell>
                    <TableCell>
                      <PresenceStatusLabel status={employee.status} />
                    </TableCell>
                    <TableCell className="max-w-56">
                      {employee.application ? (
                        <span className="flex min-w-0 items-center gap-2">
                          <AppWindow className="size-3.5 shrink-0 text-muted-foreground" aria-hidden />
                          <span className={cn('truncate', employee.status === 'idle' && 'text-muted-foreground')}>{employee.application.name}</span>
                          {employee.application.category && (
                            <span className={cn('hidden shrink-0 rounded px-1 text-[10px] font-medium xl:inline', CATEGORY[employee.application.category].className)}>
                              {CATEGORY[employee.application.category].label}
                            </span>
                          )}
                        </span>
                      ) : (
                        <span className="text-muted-foreground">—</span>
                      )}
                    </TableCell>
                    <TableCell className="hidden max-w-60 truncate text-muted-foreground lg:table-cell">{employee.task ?? '—'}</TableCell>
                    <TableCell className="text-right whitespace-nowrap tabular">
                      {employee.status === 'offline' ? (
                        <span className="text-muted-foreground">—</span>
                      ) : (
                        <span title={`${STATUS[employee.status].label} since ${new Date(employee.since).toLocaleTimeString()}`}>
                          {formatDuration(now - new Date(employee.since).getTime())}
                        </span>
                      )}
                    </TableCell>
                    <TableCell className="hidden pr-5 md:table-cell">
                      {employee.device ? (
                        <span className="flex items-center gap-1.5 whitespace-nowrap text-muted-foreground">
                          <Laptop className="size-3.5" aria-hidden /> {employee.device.name}
                        </span>
                      ) : (
                        <span className="text-muted-foreground">—</span>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
          {rows.length > PAGE && (
            <div className="border-t px-5 py-2.5 text-center">
              <Button variant="ghost" size="sm" onClick={() => setExpanded((v) => !v)}>
                {expanded ? 'Show fewer' : `Show all ${rows.length}`}
              </Button>
            </div>
          )}
        </>
      )}
    </WidgetCard>
  )
}
