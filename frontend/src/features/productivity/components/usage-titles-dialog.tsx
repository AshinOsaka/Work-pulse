import { useState } from 'react'
import { ChevronLeft, ChevronRight, TextSearch } from 'lucide-react'
import { Link } from 'react-router'

import { EmptyState } from '@/components/common/empty-state'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Skeleton } from '@/components/ui/misc'
import { formatSeconds } from '@/features/activity/format'
import { WidgetError } from '@/features/dashboard/components/widget'
import { useUsageTitles, type RangeParams } from '@/features/productivity/api'
import { LetterBadge } from '@/features/productivity/components/app-badge'
import { CATEGORY, share } from '@/features/productivity/meta'
import { cn } from '@/lib/utils'
import { usePermissions } from '@/stores/auth-store'
import type { UsageItem } from '@/types/api'

const PAGE_SIZE = 10
/** Untitled time shorter than this isn't worth a row of its own. */
const MIN_UNTITLED_SECONDS = 60

interface Row {
  title: string
  seconds: number
  untitled?: boolean
}

/** Page numbers to show: all of them when few, otherwise the current one with its neighbours and the ends. */
function pageList(page: number, pages: number): (number | '…')[] {
  if (pages <= 7) return Array.from({ length: pages }, (_, i) => i + 1)
  const near = [1, page - 1, page, page + 1, pages].filter((p) => p >= 1 && p <= pages)
  const list: (number | '…')[] = []
  for (const p of [...new Set(near)].sort((a, b) => a - b)) {
    const prev = list[list.length - 1]
    if (typeof prev === 'number' && p - prev > 1) list.push('…')
    list.push(p)
  }
  return list
}

function TitleList({ item, rows, total }: { item: UsageItem; rows: Row[]; total: number }) {
  const [page, setPage] = useState(1)
  const pages = Math.max(1, Math.ceil(rows.length / PAGE_SIZE))
  const current = Math.min(page, pages)
  const shown = rows.slice((current - 1) * PAGE_SIZE, current * PAGE_SIZE)
  const first = (current - 1) * PAGE_SIZE + 1
  return (
    <>
      <div className="min-h-0 flex-1 overflow-y-auto border-t [scrollbar-width:thin]">
        <table className="w-full table-fixed text-[13px]">
          <caption className="sr-only">Window titles in {item.name} by time</caption>
          <thead className="sticky top-0 z-10 bg-muted/60 backdrop-blur shadow-[inset_0_-1px_0_var(--color-border)]">
            <tr className="text-left text-[11.5px] font-medium tracking-wide text-muted-foreground uppercase">
              <th className="px-6 py-2.5 font-medium">Window title</th>
              <th className="hidden w-48 px-3 py-2.5 font-medium sm:table-cell">Share</th>
              <th className="w-24 py-2.5 pr-6 text-right font-medium">Time</th>
            </tr>
          </thead>
          <tbody className="divide-y">
            {shown.map((row) => {
              const pct = share(row.seconds, total)
              return (
                <tr key={row.untitled ? '\u0000untitled' : row.title}>
                  <td className="px-6 py-2.5" title={row.title}>
                    <span className="flex min-w-0 items-center gap-2.5">
                      {row.untitled ? (
                        <span className="flex size-6 shrink-0 items-center justify-center rounded-md bg-muted text-[11px] text-muted-foreground" aria-hidden>
                          –
                        </span>
                      ) : (
                        <LetterBadge label={row.title} size="sm" />
                      )}
                      <span className={cn('truncate', row.untitled ? 'text-muted-foreground italic' : 'font-medium')}>{row.title}</span>
                    </span>
                  </td>
                  <td className="hidden px-3 py-2.5 sm:table-cell" aria-label={`${pct}% of the time`}>
                    <span className="flex items-center gap-2.5">
                      <span className="h-1.5 flex-1 overflow-hidden rounded-full bg-muted" aria-hidden>
                        <span
                          className={cn('block h-full rounded-full', row.untitled ? 'bg-muted-foreground/40' : CATEGORY[item.category].swatch)}
                          style={{ width: `${Math.max(pct, row.seconds > 0 ? 2 : 0)}%` }}
                        />
                      </span>
                      <span className="w-9 text-right tabular text-[12px] font-medium">{pct}%</span>
                    </span>
                  </td>
                  <td className="py-2.5 pr-6 text-right tabular whitespace-nowrap text-muted-foreground">{formatSeconds(row.seconds)}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
      <div className="flex items-center justify-between gap-3 border-t px-6 py-3 text-[12.5px] text-muted-foreground">
        <span className="tabular">
          Showing {first}–{first + shown.length - 1} of {rows.length}
        </span>
        {pages > 1 && (
          <nav className="flex items-center gap-1" aria-label="Pages">
            <Button variant="outline" size="icon-sm" disabled={current <= 1} onClick={() => setPage(current - 1)} aria-label="Previous page">
              <ChevronLeft />
            </Button>
            {pageList(current, pages).map((p, i) =>
              p === '…' ? (
                <span key={`gap-${i}`} className="px-1" aria-hidden>
                  …
                </span>
              ) : (
                <Button
                  key={p}
                  variant={p === current ? 'default' : 'outline'}
                  size="icon-sm"
                  className="tabular"
                  onClick={() => setPage(p)}
                  aria-label={`Page ${p}`}
                  aria-current={p === current ? 'page' : undefined}
                >
                  {p}
                </Button>
              ),
            )}
            <Button variant="outline" size="icon-sm" disabled={current >= pages} onClick={() => setPage(current + 1)} aria-label="Next page">
              <ChevronRight />
            </Button>
          </nav>
        )}
      </div>
    </>
  )
}

/** "View more" for one application or website: the window titles its time was spent in, most used first. */
export function UsageTitlesDialog({
  employeeId,
  range,
  item,
  onClose,
}: {
  employeeId: string
  range: RangeParams
  item: UsageItem | null
  onClose: () => void
}) {
  const { can } = usePermissions()
  const query = useUsageTitles(employeeId, range, item)
  const data = query.data

  let body = null
  if (item) {
    if (query.isError) body = <WidgetError error={query.error} onRetry={() => void query.refetch()} />
    else if (!data) {
      body = (
        <div className="space-y-2 border-t px-6 py-4">
          {Array.from({ length: 6 }, (_, i) => (
            <Skeleton key={i} className="h-8 w-full" />
          ))}
        </div>
      )
    } else if (data.titles.length === 0) {
      body = (
        <div className="border-t px-6 py-8">
          {data.capture_enabled ? (
            <EmptyState
              size="sm"
              icon={TextSearch}
              title="No window titles in this period"
              description="Titles are recorded from when window-title capture was switched on. Password managers, e-mail, chat apps and private windows are never recorded."
            />
          ) : (
            <EmptyState
              size="sm"
              icon={TextSearch}
              title="Window titles are switched off"
              description="Turn on “Capture window titles” in the activity policy to see which pages and documents this time was spent in. Employees are told in their monitoring policy."
              action={
                can('POLICY_MANAGE') ? (
                  <Button asChild size="sm" variant="outline">
                    <Link to="/settings/workspace">Open workspace settings</Link>
                  </Button>
                ) : undefined
              }
            />
          )}
        </div>
      )
    } else {
      const untitled = item.seconds - data.titled_seconds
      const rows: Row[] = [...data.titles]
      if (untitled >= MIN_UNTITLED_SECONDS) rows.push({ title: 'No title recorded', seconds: untitled, untitled: true })
      const total = Math.max(item.seconds, data.titled_seconds)
      body = <TitleList key={`${item.kind}:${item.key}`} item={item} rows={rows} total={total} />
    }
  }

  return (
    <Dialog open={item !== null} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="flex max-h-[85vh] flex-col gap-0 overflow-hidden p-0 sm:max-w-2xl">
        {item && (
          <DialogHeader className="flex-row items-center gap-3.5 space-y-0 px-6 py-5 pr-12 text-left">
            <LetterBadge label={item.name} seed={item.key} size="lg" />
            <div className="min-w-0">
              <DialogTitle className="truncate">{item.name}</DialogTitle>
              <DialogDescription className="mt-0.5 flex items-center gap-1.5">
                <span className="tabular">{formatSeconds(item.seconds)} total</span>
                <span aria-hidden>·</span>
                <span className={cn('size-2 rounded-sm', CATEGORY[item.category].swatch)} aria-hidden />
                {CATEGORY[item.category].label}
              </DialogDescription>
            </div>
          </DialogHeader>
        )}
        {body}
      </DialogContent>
    </Dialog>
  )
}
