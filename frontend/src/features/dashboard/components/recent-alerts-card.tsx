import { ArrowRight, BellRing, CircleAlert, CircleCheck, Eye, Info, OctagonAlert, TriangleAlert, type LucideIcon } from 'lucide-react'
import { Link } from 'react-router'

import { Person } from '@/components/common/person'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/misc'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { WidgetCard, WidgetError, WidgetUnavailable } from '@/features/dashboard/components/widget'
import { NO_PERSON, type AlertSeverity, type AlertStatus, type AlertType, type DashboardAlert } from '@/features/dashboard/data/types'
import { useNow } from '@/hooks/use-now'
import { formatDateTime, formatRelative } from '@/lib/format'

const TYPE_LABEL: Record<AlertType, string> = {
  idle_time: 'Extended idle time',
  unproductive_app: 'Unproductive application',
  overtime: 'Overtime',
  agent_offline: 'Agent offline',
  blocked_site: 'Blocked website',
  employee_offline: 'Employee offline',
  device_offline: 'Device offline',
  extended_idle: 'Extended idle',
  shift_started: 'Shift started',
  shift_ended: 'Shift ended',
  task_overdue: 'Task overdue',
  project_deadline: 'Project deadline',
  live_session_started: 'Live session started',
  live_session_ended: 'Live session ended',
  screenshot_policy: 'Screenshot policy',
}

/** Severity is status: fixed colours, always with an icon and a label. */
const SEVERITY: Record<AlertSeverity, { label: string; icon: LucideIcon; variant: 'info' | 'warning' | 'destructive' }> = {
  low: { label: 'Low', icon: Info, variant: 'info' },
  medium: { label: 'Medium', icon: CircleAlert, variant: 'warning' },
  high: { label: 'High', icon: TriangleAlert, variant: 'destructive' },
  critical: { label: 'Critical', icon: OctagonAlert, variant: 'destructive' },
  info: { label: 'Info', icon: Info, variant: 'info' },
  warning: { label: 'Warning', icon: TriangleAlert, variant: 'warning' },
}

const STATUS: Record<AlertStatus, { label: string; icon: LucideIcon; variant: 'outline' | 'secondary' | 'success' }> = {
  open: { label: 'Open', icon: BellRing, variant: 'outline' },
  acknowledged: { label: 'Acknowledged', icon: Eye, variant: 'secondary' },
  resolved: { label: 'Resolved', icon: CircleCheck, variant: 'success' },
}

interface RecentAlertsCardProps {
  data: DashboardAlert[] | undefined
  isPending: boolean
  isError: boolean
  error: unknown
  isRefreshing: boolean
  onRetry: () => void
  available: boolean
  sample: boolean
}

export function RecentAlertsCard({ data, isPending, isError, error, isRefreshing, onRetry, available, sample }: RecentAlertsCardProps) {
  const now = useNow(30_000)
  const rows = (data ?? []).slice(0, 6)
  const open = (data ?? []).filter((a) => a.status === 'open').length

  return (
    <WidgetCard
      title="Recent alerts"
      description={available && data?.length ? `${open} open · latest policy and activity alerts` : 'Policy and activity alerts'}
      sample={sample}
      refreshing={isRefreshing}
      className="xl:col-span-3"
      actions={
        <Button variant="ghost" size="sm" asChild>
          <Link to="/alerts">
            All alerts <ArrowRight />
          </Link>
        </Button>
      }
    >
      {isError ? (
        <WidgetError error={error} onRetry={onRetry} />
      ) : isPending ? (
        <div className="space-y-2 p-5">
          {Array.from({ length: 4 }, (_, i) => (
            <Skeleton key={i} className="h-10" />
          ))}
        </div>
      ) : !available ? (
        <WidgetUnavailable
          icon={BellRing}
          title="No alerts yet"
          description="Choose which alerts you receive under Alerts → Preferences."
        />
      ) : rows.length === 0 ? (
        <WidgetUnavailable icon={CircleCheck} title="All clear" description="No alerts have been raised recently." />
      ) : (
        <Table className="mt-2">
          <caption className="sr-only">Recent alerts</caption>
          <TableHeader>
            <TableRow className="hover:bg-transparent">
              <TableHead className="pl-5">Time</TableHead>
              <TableHead>Employee</TableHead>
              <TableHead>Alert</TableHead>
              <TableHead>Severity</TableHead>
              <TableHead className="pr-5">Status</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((alert) => {
              const severity = SEVERITY[alert.severity]
              const status = STATUS[alert.status]
              return (
                <TableRow key={alert.id} className="animate-in duration-300 fade-in-0">
                  <TableCell className="pl-5 whitespace-nowrap text-muted-foreground">
                    <time dateTime={alert.timestamp} title={formatDateTime(alert.timestamp)}>
                      {formatRelative(alert.timestamp, now)}
                    </time>
                  </TableCell>
                  <TableCell className="max-w-48">
                    {alert.person.id === NO_PERSON ? (
                      <span className="text-muted-foreground" aria-label="Not about a specific person">
                        —
                      </span>
                    ) : (
                      <Person id={alert.person.employeeId ?? alert.person.id} name={alert.person.name} size="sm" link={Boolean(alert.person.employeeId)} />
                    )}
                  </TableCell>
                  <TableCell className="max-w-80">
                    <p className="font-medium">{TYPE_LABEL[alert.type]}</p>
                    <p className="truncate text-[12px] text-muted-foreground">{alert.detail}</p>
                  </TableCell>
                  <TableCell>
                    <Badge variant={severity.variant}>
                      <severity.icon /> {severity.label}
                    </Badge>
                  </TableCell>
                  <TableCell className="pr-5">
                    <Badge variant={status.variant}>
                      <status.icon /> {status.label}
                    </Badge>
                  </TableCell>
                </TableRow>
              )
            })}
          </TableBody>
        </Table>
      )}
    </WidgetCard>
  )
}
