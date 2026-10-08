import { useDeferredValue, useMemo, useState } from 'react'
import { AppWindow, HeartPulse, History, Laptop, MonitorPlay, MonitorX, Radio, ScrollText, Search, Settings2, Users, Wifi, WifiOff } from 'lucide-react'
import { Link, useNavigate } from 'react-router'

import { EmptyState } from '@/components/common/empty-state'
import { FilterSelect, toOptions } from '@/components/common/filter-select'
import { PageHeader } from '@/components/common/page-header'
import { PersonAvatar } from '@/components/common/person'
import { StatTile } from '@/components/common/stat-tile'
import { VirtualGrid } from '@/components/common/virtual'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/misc'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { RequirePermission } from '@/features/auth/guards'
import { WidgetError } from '@/features/dashboard/components/widget'
import { useLiveEmployees, useLiveSessionLog, useStartLive } from '@/features/live/api'
import { StartLiveDialog } from '@/features/live/components/start-live-dialog'
import { AVAILABILITY, LOG_REASONS } from '@/features/live/meta'
import { useDocumentTitle } from '@/hooks/use-document-title'
import { useNow } from '@/hooks/use-now'
import { formatDateTime, formatDuration, formatRelative, formatTime } from '@/lib/format'
import { cn } from '@/lib/utils'
import { usePermissions } from '@/stores/auth-store'
import type { LiveEmployee, LiveSession } from '@/types/api'

type View = 'people' | 'log'

function StatusDot({ employee }: { employee: LiveEmployee }) {
  const tone =
    employee.availability === 'in_session'
      ? 'bg-destructive'
      : employee.presence === 'active'
        ? 'bg-presence-active'
        : employee.presence === 'idle'
          ? 'bg-presence-idle'
          : employee.online
            ? 'bg-info'
            : 'bg-presence-offline'
  return <span className={cn('absolute right-0 bottom-0 size-3 rounded-full ring-2 ring-card', tone)} aria-hidden />
}

/** The desktop agent's signalling link: what makes a live view possible at all. */
function ConnectionIndicator({ employee }: { employee: LiveEmployee }) {
  if (employee.availability === 'in_session') {
    return (
      <span className="inline-flex items-center gap-1.5 text-destructive">
        <span className="relative flex size-2">
          <span className="absolute inline-flex size-full animate-ping rounded-full bg-destructive opacity-60 motion-reduce:animate-none" />
          <span className="relative inline-flex size-2 rounded-full bg-destructive" />
        </span>
        Streaming
      </span>
    )
  }
  return employee.online ? (
    <span className="inline-flex items-center gap-1.5 text-success">
      <Wifi className="size-3.5" aria-hidden /> Agent connected
    </span>
  ) : (
    <span className="inline-flex items-center gap-1.5 text-muted-foreground">
      <WifiOff className="size-3.5" aria-hidden /> Agent offline
    </span>
  )
}

function EmployeeCard({ employee, onView }: { employee: LiveEmployee; onView: (e: LiveEmployee) => void }) {
  const now = useNow(1000)
  const status = AVAILABILITY[employee.availability]
  const session = employee.live_session
  const working = employee.presence !== null
  const since = employee.status_since ? formatDuration(now - new Date(employee.status_since).getTime()) : null
  const label = employee.presence === 'idle' ? 'Idle' : employee.presence === 'active' && employee.availability === 'available' ? 'Active' : status.label
  const subtitle = [employee.employee.job_title, employee.department?.name, employee.team?.name].filter(Boolean).join(' · ')
  const heartbeat = employee.device?.last_seen_at ? formatRelative(employee.device.last_seen_at, now) : null

  return (
    <Card
      className={cn(
        'flex w-full flex-col gap-4 p-4 transition',
        employee.availability === 'available' && 'hover:border-primary/40 hover:shadow-card',
        employee.availability === 'in_session' && 'border-destructive/30',
      )}
    >
      <div className="flex items-start gap-3">
        <div className="relative shrink-0">
          <PersonAvatar name={employee.employee.full_name} seed={employee.employee.id} className="size-11" />
          <StatusDot employee={employee} />
        </div>
        <div className="min-w-0 flex-1">
          <Link to={`/people/employees/${employee.employee.id}`} className="block truncate font-semibold hover:underline">
            {employee.employee.full_name}
          </Link>
          <p className="truncate text-[12px] text-muted-foreground">{subtitle || 'No title'}</p>
        </div>
        <span
          className={cn(
            'inline-flex shrink-0 items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium',
            employee.availability === 'in_session'
              ? 'bg-destructive-soft text-destructive'
              : working
                ? 'bg-success-soft text-success'
                : employee.online
                  ? 'bg-info-soft text-info'
                  : 'bg-muted text-muted-foreground',
          )}
        >
          {employee.availability === 'in_session' && <Radio className="size-3" aria-hidden />}
          {label}
        </span>
      </div>

      <dl className="space-y-1.5 text-[12px]">
        <div className="flex items-center gap-2 text-muted-foreground">
          <AppWindow className="size-3.5 shrink-0" aria-hidden />
          <dt className="sr-only">Application</dt>
          <dd className="truncate">{working ? (employee.current_app ?? 'No application reported') : status.hint}</dd>
        </div>
        <div className="flex items-center gap-2 text-muted-foreground">
          <Laptop className="size-3.5 shrink-0" aria-hidden />
          <dt className="sr-only">Device</dt>
          <dd className="truncate">
            {employee.device?.name ?? '—'}
            {since && (
              <span className="tabular">
                {' '}
                · {working ? `${label.toLowerCase()} for` : 'seen'} {since}
                {working ? '' : ' ago'}
              </span>
            )}
          </dd>
        </div>
        <div className="flex items-center gap-2 text-muted-foreground">
          <HeartPulse className="size-3.5 shrink-0" aria-hidden />
          <dt className="sr-only">Last heartbeat</dt>
          <dd className="truncate tabular">{heartbeat ? `Last heartbeat ${heartbeat}` : 'No heartbeat yet'}</dd>
        </div>
        <div className="flex items-center gap-2 font-medium">
          <dt className="sr-only">Connection</dt>
          <dd>
            <ConnectionIndicator employee={employee} />
          </dd>
        </div>
      </dl>

      <div className="mt-auto">
        {session ? (
          session.mine ? (
            <Button asChild size="sm" variant="destructive" className="w-full">
              <Link to={`/live/${session.id}`}>
                <Radio /> Return to live view
              </Link>
            </Button>
          ) : (
            <Button size="sm" variant="outline" className="w-full" disabled>
              Viewed by {session.viewer_name}
            </Button>
          )
        ) : (
          <Button
            size="sm"
            className="w-full"
            variant={employee.availability === 'available' ? 'default' : 'outline'}
            disabled={employee.availability !== 'available'}
            onClick={() => onView(employee)}
            title={employee.availability === 'available' ? undefined : status.hint}
          >
            <MonitorPlay /> View live
          </Button>
        )}
      </div>
    </Card>
  )
}

function Overview({ rows }: { rows: LiveEmployee[] }) {
  const items = [
    {
      label: 'Online employees',
      value: rows.filter((e) => e.online).length,
      dot: 'bg-presence-active',
    },
    {
      label: 'Active sessions',
      value: rows.filter((e) => e.availability === 'in_session').length,
      dot: 'bg-destructive',
    },
    {
      label: 'Idle employees',
      value: rows.filter((e) => e.presence === 'idle').length,
      dot: 'bg-presence-idle',
    },
    {
      label: 'Offline employees',
      value: rows.filter((e) => !e.online).length,
      dot: 'bg-presence-offline',
    },
  ]
  return (
    <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
      {items.map((item) => (
        <StatTile key={item.label} label={item.label} value={item.value} marker={item.dot} />
      ))}
    </div>
  )
}


const STATUS_OPTIONS = [
  { value: 'online', label: 'Online' },
  { value: 'active', label: 'Active' },
  { value: 'idle', label: 'Idle' },
  { value: 'in_session', label: 'In a live session' },
  { value: 'offline', label: 'Offline' },
]

function matchesStatus(e: LiveEmployee, status: string | null): boolean {
  switch (status) {
    case 'online':
      return e.online
    case 'active':
      return e.presence === 'active'
    case 'idle':
      return e.presence === 'idle'
    case 'in_session':
      return e.availability === 'in_session'
    case 'offline':
      return !e.online
    default:
      return true
  }
}

function unique(refs: ({ id: string; name: string } | null)[]): { id: string; name: string }[] {
  const map = new Map<string, string>()
  for (const r of refs) if (r) map.set(r.id, r.name)
  return [...map].map(([id, name]) => ({ id, name })).sort((a, b) => a.name.localeCompare(b.name))
}

function People({ onView }: { onView: (e: LiveEmployee) => void }) {
  const query = useLiveEmployees()
  const { can } = usePermissions()
  const [status, setStatus] = useState<string | null>('online')
  const [search, setSearch] = useState('')
  const [department, setDepartment] = useState<string | null>(null)
  const [team, setTeam] = useState<string | null>(null)
  const data = query.data
  const rows = useMemo(() => data?.employees ?? [], [data])

  const departments = useMemo(() => unique(rows.map((e) => e.department)), [rows])
  const teams = useMemo(() => unique(rows.filter((e) => department === null || e.department?.id === department).map((e) => e.team)), [rows, department])

  // Typing stays responsive: the (large) list re-filters at React's lower priority.
  const deferredSearch = useDeferredValue(search)
  const visible = useMemo(() => {
    const term = deferredSearch.trim().toLowerCase()
    return rows.filter(
      (e) =>
        matchesStatus(e, status) &&
        (department === null || e.department?.id === department) &&
        (team === null || e.team?.id === team) &&
        (!term ||
          e.employee.full_name.toLowerCase().includes(term) ||
          e.employee.job_title?.toLowerCase().includes(term) ||
          e.device?.name.toLowerCase().includes(term)),
    )
  }, [rows, status, department, team, deferredSearch])
  const filtered = search.trim() !== '' || department !== null || team !== null || (status !== null && status !== 'online')

  if (query.isError) {
    return (
      <Card>
        <WidgetError error={query.error} onRetry={() => void query.refetch()} />
      </Card>
    )
  }

  return (
    <div className="space-y-5">
      {data && !data.enabled && (
        <Card className="flex flex-col gap-3 border-warning/40 bg-warning-soft/40 p-4 sm:flex-row sm:items-center">
          <MonitorX className="size-5 shrink-0 text-warning" aria-hidden />
          <p className="flex-1 text-[13px]">
            <span className="font-medium">Live viewing is turned off for this workspace.</span>{' '}
            <span className="text-muted-foreground">You can still see who is online.</span>
          </p>
          {can('POLICY_MANAGE') && (
            <Button asChild size="sm" variant="outline">
              <Link to="/settings/workspace">
                <Settings2 /> Live view settings
              </Link>
            </Button>
          )}
        </Card>
      )}

      {data ? <Overview rows={rows} /> : <Skeleton className="h-[74px]" />}

      <div className="flex flex-wrap items-center gap-3">
        <div className="relative w-full sm:w-60">
          <Search className="pointer-events-none absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2 text-muted-foreground" aria-hidden />
          <Input
            type="search"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search people or devices"
            aria-label="Search people or devices"
            className="h-8 pl-8 text-[13px]"
          />
        </div>
        <FilterSelect
          label="Department"
          value={department}
          onChange={(v) => {
            setDepartment(v)
            setTeam(null)
          }}
          options={toOptions(departments)}
          allLabel="All departments"
        />
        <FilterSelect label="Team" value={team} onChange={setTeam} options={toOptions(teams)} allLabel="All teams" />
        <FilterSelect label="Status" value={status} onChange={setStatus} options={STATUS_OPTIONS} allLabel="Any status" />
        <p className="ml-auto text-[12px] text-muted-foreground" aria-live="polite">
          {data ? `Showing ${visible.length} of ${rows.length} · updates every 10 s` : ''}
        </p>
      </div>

      {!data ? (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
          {Array.from({ length: 6 }, (_, i) => (
            <Skeleton key={i} className="h-52" />
          ))}
        </div>
      ) : visible.length === 0 ? (
        <Card>
          {filtered ? (
            <EmptyState
              icon={Search}
              title="No one matches these filters"
              description="Try another search, department, team or status."
              action={
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => {
                    setSearch('')
                    setDepartment(null)
                    setTeam(null)
                    setStatus('online')
                  }}
                >
                  Clear filters
                </Button>
              }
            />
          ) : (
            <EmptyState
              icon={MonitorPlay}
              title={status === 'online' && rows.length > 0 ? 'Nobody is online right now' : 'No employees with the desktop agent'}
              description={
                status === 'online' && rows.length > 0
                  ? 'People appear here as soon as their WorkPulse desktop agent connects.'
                  : 'Live viewing works for people who have the WorkPulse desktop agent installed and signed in.'
              }
              action={
                status === 'online' && rows.length > 0 ? (
                  <Button size="sm" variant="outline" onClick={() => setStatus(null)}>
                    Show everyone
                  </Button>
                ) : undefined
              }
            />
          )}
        </Card>
      ) : (
        <VirtualGrid
          items={visible}
          label="Employees"
          estimateRowHeight={208}
          gap={16}
          // Same breakpoints as the classes below (sm 640, xl 1280, 2xl 1536).
          columnsFor={(w) => (w >= 1536 ? 4 : w >= 1280 ? 3 : w >= 640 ? 2 : 1)}
          className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4"
          itemClassName="flex"
          getKey={(e) => e.employee.id}
          renderItem={(employee) => <EmployeeCard employee={employee} onView={onView} />}
        />
      )}
    </div>
  )
}

function outcome(session: LiveSession): { label: string; tone: string } {
  if (session.status !== 'ended')
    return {
      label: session.status === 'live' ? 'Live now' : 'In progress',
      tone: 'text-destructive',
    }
  const reason = session.end_reason ?? 'ended'
  const label = LOG_REASONS[reason] ?? reason.replaceAll('_', ' ')
  return {
    label,
    tone: session.connected_at ? 'text-foreground' : 'text-muted-foreground',
  }
}

function SessionLog() {
  const query = useLiveSessionLog(true)
  const items = query.data?.items ?? []
  if (query.isError) {
    return (
      <Card>
        <WidgetError error={query.error} onRetry={() => void query.refetch()} />
      </Card>
    )
  }
  return (
    <Card className="overflow-hidden">
      <div className="flex items-center gap-2 border-b px-5 py-3.5">
        <ScrollText className="size-4 text-muted-foreground" aria-hidden />
        <h2 className="font-semibold">Session log</h2>
        <span className="text-[12px] text-muted-foreground">Every live view of people you manage, newest first. Video is never recorded.</span>
      </div>
      {!query.data ? (
        <div className="space-y-2 p-5">
          {Array.from({ length: 4 }, (_, i) => (
            <Skeleton key={i} className="h-10" />
          ))}
        </div>
      ) : items.length === 0 ? (
        <EmptyState
          icon={ScrollText}
          title="No live sessions yet"
          description="Each live view is listed here with who watched, the device and how long it lasted."
        />
      ) : (
        <div className="relative overflow-x-auto">
          <Table>
            <caption className="sr-only">Live session log</caption>
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                <TableHead className="pl-5">Employee</TableHead>
                <TableHead>Viewer</TableHead>
                <TableHead>Device</TableHead>
                <TableHead>Started</TableHead>
                <TableHead>Ended</TableHead>
                <TableHead className="text-right">Watched</TableHead>
                <TableHead>Outcome</TableHead>
                <TableHead className="pr-5">Session ID</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {items.map((s) => {
                const o = outcome(s)
                return (
                  <TableRow key={s.id}>
                    <TableCell className="pl-5">
                      <span className="flex items-center gap-2">
                        <PersonAvatar name={s.employee.full_name} seed={s.employee.id} className="size-6" />
                        <span className="truncate font-medium whitespace-nowrap">{s.employee.full_name}</span>
                      </span>
                    </TableCell>
                    <TableCell className="whitespace-nowrap">{s.viewer_name}</TableCell>
                    <TableCell className="whitespace-nowrap text-muted-foreground">{s.device?.name ?? '—'}</TableCell>
                    <TableCell className="tabular whitespace-nowrap" title={s.connected_at ? 'Video connected' : 'Requested; video never connected'}>
                      {formatDateTime(s.connected_at ?? s.created_at)}
                    </TableCell>
                    <TableCell className="tabular whitespace-nowrap text-muted-foreground">{s.ended_at ? formatTime(s.ended_at) : '—'}</TableCell>
                    <TableCell className="text-right tabular whitespace-nowrap">{s.duration_seconds !== null ? formatDuration(s.duration_seconds * 1000) : '—'}</TableCell>
                    <TableCell className={cn('max-w-64 truncate', o.tone)} title={o.label}>
                      {o.label}
                      {s.reconnects > 0 && (
                        <span className="text-muted-foreground">
                          {' '}
                          · {s.reconnects} reconnect
                          {s.reconnects === 1 ? '' : 's'}
                        </span>
                      )}
                    </TableCell>
                    <TableCell className="pr-5 font-mono text-[11px] text-muted-foreground">{s.id}</TableCell>
                  </TableRow>
                )
              })}
            </TableBody>
          </Table>
        </div>
      )}
    </Card>
  )
}

function LiveDirectory() {
  const start = useStartLive()
  const navigate = useNavigate()
  const query = useLiveEmployees()
  const [view, setView] = useState<View>('people')
  const [target, setTarget] = useState<LiveEmployee | null>(null)

  return (
    <div className="space-y-5">
      <Tabs value={view} onValueChange={(v) => setView(v as View)}>
        <TabsList>
          <TabsTrigger value="people">
            <Users /> Employees
          </TabsTrigger>
          <TabsTrigger value="log">
            <History /> Session log
          </TabsTrigger>
        </TabsList>
        <TabsContent value="people">
          <People
            onView={(e) => {
              start.reset()
              setTarget(e)
            }}
          />
        </TabsContent>
        <TabsContent value="log">
          <SessionLog />
        </TabsContent>
      </Tabs>
      <StartLiveDialog
        target={target}
        maxMinutes={query.data?.max_session_minutes ?? 30}
        pending={start.isPending}
        error={start.error}
        onCancel={() => setTarget(null)}
        onConfirm={(t) =>
          start.mutate(t.employee.id, {
            onSuccess: (session) => navigate(`/live/${session.id}`),
          })
        }
      />
    </div>
  )
}

export default function LivePage() {
  useDocumentTitle('Live Tracking')
  return (
    <div className="space-y-6">
      <PageHeader
        title="Live Tracking"
        description="Monitor currently active company devices and start authorized live sessions."
        icon={MonitorPlay}
      />
      <RequirePermission permission="LIVE_STREAM_VIEW">
        <LiveDirectory />
      </RequirePermission>
    </div>
  )
}
