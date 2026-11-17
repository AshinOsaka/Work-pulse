import { Button } from '@/components/ui/button'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { formatSeconds, percent } from '@/features/activity/format'
import { LetterBadge } from '@/features/productivity/components/app-badge'
import type { WebsiteUsage } from '@/types/api'

interface WebsiteUsageTableProps {
  websites: WebsiteUsage[]
  totalSeconds: number
  /** Show how many people visited each site (team views). */
  showPeople?: boolean
  caption: string
  limit?: number
  /** Opens the window titles for one website (one person selected). */
  onViewMore?: (site: WebsiteUsage) => void
}

/** Ranked website usage by domain; the inline bar is each site's share of browser time. */
export function WebsiteUsageTable({ websites, totalSeconds, showPeople = false, caption, limit, onViewMore }: WebsiteUsageTableProps) {
  const rows = limit ? websites.slice(0, limit) : websites
  const top = rows[0]?.seconds ?? 0
  return (
    <Table>
      <caption className="sr-only">{caption}</caption>
      <TableHeader>
        <TableRow className="hover:bg-transparent">
          <TableHead className="pl-5">Website</TableHead>
          <TableHead className="hidden w-[32%] sm:table-cell">
            <span className="sr-only">Share of browser time</span>
          </TableHead>
          <TableHead className="text-right">Time</TableHead>
          <TableHead className="text-right">Share</TableHead>
          <TableHead className="text-right" title="Share of the time with keyboard or mouse input">
            Active
          </TableHead>
          {showPeople && <TableHead className="pr-5 text-right">People</TableHead>}
          {onViewMore && (
            <TableHead className="w-28 pr-5 text-right">
              <span className="sr-only">Details</span>
            </TableHead>
          )}
        </TableRow>
      </TableHeader>
      <TableBody>
        {rows.map((site) => (
          <TableRow key={site.domain}>
            <TableCell className="max-w-72 pl-5">
              <div className="flex min-w-0 items-center gap-3">
                <LetterBadge label={site.domain} seed={site.domain} />
                <p className="truncate font-medium" title={site.domain}>
                  {site.domain}
                </p>
              </div>
            </TableCell>
            <TableCell className="hidden sm:table-cell">
              <div className="h-2 rounded-full bg-muted" aria-hidden>
                <div className="h-2 rounded-full bg-chart-1" style={{ width: `${Math.max(2, percent(site.seconds, top))}%` }} />
              </div>
            </TableCell>
            <TableCell className="text-right whitespace-nowrap tabular">{formatSeconds(site.seconds)}</TableCell>
            <TableCell className="text-right tabular whitespace-nowrap text-muted-foreground">{percent(site.seconds, totalSeconds)}%</TableCell>
            <TableCell className="text-right tabular whitespace-nowrap text-muted-foreground">{percent(site.active_seconds, site.seconds)}%</TableCell>
            {showPeople && <TableCell className="pr-5 text-right tabular whitespace-nowrap">{site.employees}</TableCell>}
            {onViewMore && (
              <TableCell className="pr-5 text-right">
                <Button size="sm" variant="outline" className="h-7 text-[12px]" onClick={() => onViewMore(site)} aria-label={`View more about ${site.domain}`}>
                  View more
                </Button>
              </TableCell>
            )}
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )
}
