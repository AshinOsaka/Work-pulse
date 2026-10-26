import { useState } from 'react'
import { Link } from 'react-router'
import { Users } from 'lucide-react'

import { PersonAvatar } from '@/components/common/person'
import { Skeleton } from '@/components/ui/misc'
import { SegmentedControl } from '@/components/ui/segmented-control'
import { WidgetCard, WidgetError, WidgetUnavailable } from '@/features/dashboard/components/widget'
import { formatClock } from '@/features/dashboard/components/org/shared'
import type { TeamProductivityRow } from '@/types/api'

interface Props {
  rows: TeamProductivityRow[] | undefined
  isPending: boolean
  isError: boolean
  error: unknown
  isRefreshing: boolean
  onRetry: () => void
}

type Mode = 'top' | 'less'

/** Rank by productive share, breaking ties with productive seconds; people with no data sort last. */
function rank(a: TeamProductivityRow, b: TeamProductivityRow): number {
  const sa = a.productive_share ?? -1
  const sb = b.productive_share ?? -1
  if (sa !== sb) return sb - sa
  return b.metrics.productive_seconds - a.metrics.productive_seconds
}

export function MemberProductivityCard({ rows, isPending, isError, error, isRefreshing, onRetry }: Props) {
  const [mode, setMode] = useState<Mode>('top')
  const withData = (rows ?? []).filter((r) => r.metrics.work_seconds > 0 || r.metrics.productive_seconds > 0)
  const ranked = [...withData].sort(rank)
  const list = (mode === 'top' ? ranked : [...ranked].reverse()).slice(0, 5)
  const max = Math.max(1, ...withData.map((r) => r.metrics.productive_seconds))

  return (
    <WidgetCard
      title={
        <span className="inline-flex items-center gap-2">
          <Users className="size-4 text-primary" aria-hidden /> Member Productivity
        </span>
      }
      description="Top and less productive members"
      refreshing={isRefreshing}
    >
      {withData.length > 0 && (
        <div className="px-5 pt-1 pb-3">
          <SegmentedControl<Mode>
            size="sm"
            label="Ranking"
            value={mode}
            onChange={setMode}
            className="grid w-full grid-cols-2 [&>*]:justify-center"
            options={[
              { value: 'top', label: 'Top Productive' },
              { value: 'less', label: 'Less Productive' },
            ]}
          />
        </div>
      )}
      {isError ? (
        <WidgetError error={error} onRetry={onRetry} />
      ) : isPending ? (
        <div className="space-y-3 p-5">
          {[0, 1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-11" />
          ))}
        </div>
      ) : !list.length ? (
        <WidgetUnavailable
          icon={Users}
          title="No member activity yet"
          description="Productivity per person appears once the desktop agent has recorded classified work in this range."
        />
      ) : (
        <ul className="divide-y">
          {list.map((row) => (
            <li key={row.employee.id}>
              <Link
                to={`/people/employees/${row.employee.id}`}
                className="flex items-center gap-3 px-5 py-3 transition-colors hover:bg-muted/50"
              >
                <PersonAvatar name={row.employee.full_name} seed={row.employee.id} className="size-9" aria-hidden />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-[13px] font-medium">{row.employee.full_name}</p>
                  <p className="truncate text-[12px] text-muted-foreground">{row.work_profile?.name ?? row.team?.name ?? row.employee.job_title ?? '—'}</p>
                  <div className="mt-1.5 h-1.5 w-full overflow-hidden rounded-full bg-muted">
                    <span
                      className="block h-full rounded-full bg-cat-productive"
                      style={{ width: `${Math.round((100 * row.metrics.productive_seconds) / max)}%` }}
                    />
                  </div>
                </div>
                <div className="shrink-0 text-right">
                  <p className="text-[13px] font-semibold tabular">{formatClock(row.metrics.productive_seconds)}</p>
                  <p className="text-[11px] text-muted-foreground">{row.productive_share === null ? 'productive' : `${row.productive_share}% productive`}</p>
                </div>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </WidgetCard>
  )
}
