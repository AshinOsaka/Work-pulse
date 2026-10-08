import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { formatSeconds, percent } from '@/features/activity/format'
import type { AppUsage } from '@/types/api'

interface AppUsageTableProps {
  applications: AppUsage[]
  totalSeconds: number
  /** Show how many people used each application (team views). */
  showPeople?: boolean
  caption: string
  limit?: number
}

/** Ranked application usage; the inline bar is each application's share of tracked time. */
export function AppUsageTable({ applications, totalSeconds, showPeople = false, caption, limit }: AppUsageTableProps) {
  const rows = limit ? applications.slice(0, limit) : applications
  const top = rows[0]?.seconds ?? 0
  return (
    <Table>
      <caption className="sr-only">{caption}</caption>
      <TableHeader>
        <TableRow className="hover:bg-transparent">
          <TableHead className="pl-5">Application</TableHead>
          <TableHead className="hidden w-[32%] sm:table-cell">
            <span className="sr-only">Share of tracked time</span>
          </TableHead>
          <TableHead className="text-right">Time</TableHead>
          <TableHead className="text-right">Share</TableHead>
          <TableHead className="text-right" title="Share of the time with keyboard or mouse input">
            Active
          </TableHead>
          {showPeople && <TableHead className="pr-5 text-right">People</TableHead>}
        </TableRow>
      </TableHeader>
      <TableBody>
        {rows.map((app) => (
          <TableRow key={app.app_id}>
            <TableCell className="max-w-64 pl-5">
              <p className="truncate font-medium" title={app.app_name}>
                {app.app_name}
              </p>
              <p className="truncate text-[11px] text-muted-foreground">{app.app_id}</p>
            </TableCell>
            <TableCell className="hidden sm:table-cell">
              <div className="h-2 rounded-full bg-muted" aria-hidden>
                <div className="h-2 rounded-full bg-chart-1" style={{ width: `${Math.max(2, percent(app.seconds, top))}%` }} />
              </div>
            </TableCell>
            <TableCell className="text-right whitespace-nowrap tabular">{formatSeconds(app.seconds)}</TableCell>
            <TableCell className="text-right tabular whitespace-nowrap text-muted-foreground">{percent(app.seconds, totalSeconds)}%</TableCell>
            <TableCell className="text-right tabular whitespace-nowrap text-muted-foreground">{percent(app.active_seconds, app.seconds)}%</TableCell>
            {showPeople && <TableCell className="pr-5 text-right tabular whitespace-nowrap">{app.employees}</TableCell>}
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )
}
