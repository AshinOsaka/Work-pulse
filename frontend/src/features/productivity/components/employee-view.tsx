import { useMemo, useState } from 'react'
import { AppWindow, Headset, LineChart, Timer } from 'lucide-react'

import { EmptyState } from '@/components/common/empty-state'
import { Button } from '@/components/ui/button'
import { Card, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/misc'
import { SegmentedControl } from '@/components/ui/segmented-control'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { formatClock, formatDay, formatSeconds } from '@/features/activity/format'
import { WidgetError } from '@/features/dashboard/components/widget'
import { useEmployeeProductivity, useProductivityTrend, type TrendPeriod } from '@/features/productivity/api'
import { LetterBadge } from '@/features/productivity/components/app-badge'
import { ClassifyMenu } from '@/features/productivity/components/classify-menu'
import { DataSheet, type DataTarget } from '@/features/productivity/components/data-sheet'
import { ProductivityReport } from '@/features/productivity/components/report'
import { TrendPanels } from '@/features/productivity/components/trend-panels'
import { UsageTitlesDialog } from '@/features/productivity/components/usage-titles-dialog'
import { CATEGORY, RANGES, rangeFor, SCOPE_LABEL, share, type RangeKey } from '@/features/productivity/meta'
import { cn } from '@/lib/utils'
import { useAuthStore, usePermissions } from '@/stores/auth-store'
import type { CustomerSystem, UsageItem } from '@/types/api'

/** Matches the backend CustomerSystems: a website matches a domain or any of its parent domains; an app
 *  matches by executable id or display name. Used to split customer time by which system it came from. */
function matchesSystem(item: UsageItem, system: CustomerSystem): boolean {
  if (system.kind !== item.kind) return false
  const pattern = system.pattern.toLowerCase()
  if (item.kind === 'website') {
    const labels = item.key.toLowerCase().split('.')
    return labels.some((_, i) => labels.slice(i).join('.') === pattern)
  }
  return item.key.toLowerCase() === pattern || item.name.toLowerCase() === pattern
}

function customerBreakdown(usage: UsageItem[], systems: CustomerSystem[]) {
  const totals = new Map<string, number>()
  for (const item of usage) {
    const system = systems.find((s) => matchesSystem(item, s)) // first match; each item counts once
    if (system) totals.set(system.label, (totals.get(system.label) ?? 0) + item.seconds)
  }
  const rows = [...totals.entries()]
    .map(([label, seconds]) => ({ label, seconds }))
    .filter((r) => r.seconds > 0)
    .sort((a, b) => b.seconds - a.seconds)
  return { rows, total: rows.reduce((sum, r) => sum + r.seconds, 0) }
}

/** Per-person customer time, split by which customer-facing system it came from (ranked). */
function CustomerTimeCard({ usage, systems }: { usage: UsageItem[]; systems: CustomerSystem[] }) {
  const { rows, total } = useMemo(() => customerBreakdown(usage, systems), [usage, systems])
  if (rows.length === 0) return null
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Headset className="size-4 text-muted-foreground" aria-hidden /> Customer time
        </CardTitle>
        <CardDescription>Time in your customer-facing systems · {formatSeconds(total)} total</CardDescription>
      </CardHeader>
      <ul className="divide-y px-5 pt-3 pb-5">
        {rows.map((r) => (
          <li key={r.label} className="flex items-center justify-between gap-3 py-2 text-[13px] first:pt-0 last:pb-0">
            <span className="flex min-w-0 items-center gap-2">
              <span className="size-2 shrink-0 rounded-full bg-[var(--presence-active)]" aria-hidden />
              <span className="truncate font-medium">{r.label}</span>
            </span>
            <span className="shrink-0 tabular">
              {formatSeconds(r.seconds)} <span className="text-muted-foreground">· {share(r.seconds, total)}%</span>
            </span>
          </li>
        ))}
      </ul>
    </Card>
  )
}

function UsageTable({
  items,
  canClassify,
  onViewMore,
}: {
  items: UsageItem[]
  canClassify: boolean
  onViewMore: (item: UsageItem) => void
}) {
  if (!items.length) return <EmptyState size="sm" icon={AppWindow} title="No application activity" description="Nothing was recorded in this period." />
  return (
    <Table>
      <caption className="sr-only">Applications and websites by time</caption>
      <TableHeader className="sticky top-0 z-10 shadow-[inset_0_-1px_0_var(--color-border)]">
        <TableRow className="hover:bg-transparent">
          <TableHead className="pl-5">Application or website</TableHead>
          <TableHead>Category</TableHead>
          <TableHead className="text-right">Time</TableHead>
          <TableHead className="pr-5 text-right">Action</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {items.map((item) => (
          <TableRow key={`${item.kind}:${item.key}`}>
            {/* w-full + max-w-0: the name takes the spare width and truncates, so the table never scrolls sideways. */}
            <TableCell className="w-full max-w-0 pl-5" title={item.name}>
              <span className="flex min-w-0 items-center gap-2.5">
                <LetterBadge label={item.name} seed={item.key} />
                <span className="sr-only">{item.kind === 'website' ? 'Website:' : 'Application:'}</span>
                {/* Which rule decided sits under the name, not in its own column, so the table fits its card. */}
                <span className="min-w-0">
                  <span className="block truncate font-medium">{item.name}</span>
                  <span className="block truncate text-[11.5px] text-muted-foreground">
                    {item.rule_scope ? `${SCOPE_LABEL[item.rule_scope]} rule · ${item.rule_pattern}` : 'No rule yet'}
                  </span>
                </span>
              </span>
            </TableCell>
            <TableCell className="whitespace-nowrap">
              <span className="inline-flex items-center gap-1.5 text-[12px]">
                <span className={cn('size-2.5 rounded-sm', CATEGORY[item.category].swatch)} aria-hidden />
                {CATEGORY[item.category].label}
              </span>
            </TableCell>
            <TableCell className="text-right tabular whitespace-nowrap">{formatSeconds(item.seconds)}</TableCell>
            <TableCell className="pr-5">
              <span className="flex items-center justify-end gap-1.5">
                {canClassify && item.category === 'unclassified' && <ClassifyMenu kind={item.kind} pattern={item.key} name={item.name} />}
                <Button size="sm" variant="outline" className="h-7 text-[12px]" onClick={() => onViewMore(item)} aria-label={`View more about ${item.name}`}>
                  View more
                </Button>
              </span>
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )
}

/** One person's productivity: used on the drill-in page and the profile's Productivity tab. */
export function EmployeeProductivityView({ employeeId }: { employeeId: string }) {
  const timeZone = useAuthStore((s) => s.company?.timezone ?? 'UTC')
  const customerSystems = useAuthStore((s) => s.company?.customer_systems ?? [])
  const { can } = usePermissions()
  const [range, setRange] = useState<RangeKey>('7d')
  const dates = rangeFor(range, timeZone)
  const query = useEmployeeProductivity(employeeId, dates)
  const data = query.data
  const [period, setPeriod] = useState<TrendPeriod>('daily')
  const trend = useProductivityTrend(period, { employee_id: employeeId })
  const [target, setTarget] = useState<DataTarget | null>(null)
  const [details, setDetails] = useState<UsageItem | null>(null)
  const name = data?.employee.full_name ?? 'This person'
  const open = (start: string, end: string) => setTarget({ start, end, scope: { employee_id: employeeId }, label: name })

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center gap-3">
        <SegmentedControl label="Period" value={range} onChange={setRange} options={RANGES} />
        {data && (
          <p className="text-[12px] text-muted-foreground">
            {formatDay(data.start, 'short')} – {formatDay(data.end, 'short')}
          </p>
        )}
      </div>
      {query.isError ? (
        <Card>
          <WidgetError error={query.error} onRetry={() => void query.refetch()} />
        </Card>
      ) : !data ? (
        <div className="space-y-4">
          <Skeleton className="h-24" />
          <Skeleton className="h-72" />
        </div>
      ) : (
        <div className={query.isFetching ? 'opacity-80 transition-opacity' : undefined}>
          <ProductivityReport data={data} onSelectDay={(day) => open(day, day)}>
            <div className="grid grid-cols-[minmax(0,1fr)] gap-6 xl:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
              <Card className="overflow-hidden">
                <CardHeader>
                  <CardTitle>Applications and websites</CardTitle>
                  <CardDescription>Which rule decided each category. Unclassified items count in no score.</CardDescription>
                </CardHeader>
                {/* Long lists scroll inside the card (headings stay put) so the sections below stay in reach. On wide
                    screens the list fills the card down to the height of the column beside it, leaving no blank gap. */}
                <div
                  className={cn(
                    'relative mt-3 min-h-0 flex-1 border-t',
                    '[&_[data-slot=table-container]]:max-h-[28rem] [&_[data-slot=table-container]]:overflow-y-auto [&_[data-slot=table-container]]:overflow-x-hidden [&_[data-slot=table-container]]:[scrollbar-width:thin]',
                    'xl:min-h-[28rem] xl:[&_[data-slot=table-container]]:absolute xl:[&_[data-slot=table-container]]:inset-0 xl:[&_[data-slot=table-container]]:max-h-none',
                  )}
                >
                  <UsageTable items={data.usage} canClassify={can('POLICY_MANAGE')} onViewMore={setDetails} />
                </div>
              </Card>
              <div className="space-y-6">
                <CustomerTimeCard usage={data.usage} systems={customerSystems} />
                <Card>
                  <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                      <Timer className="size-4 text-muted-foreground" aria-hidden /> Focus sessions
                    </CardTitle>
                    <CardDescription>25+ minutes of productive work without longer interruptions</CardDescription>
                  </CardHeader>
                  <div className="px-5 pt-3 pb-5">
                    {data.focus_sessions.length === 0 ? (
                      <p className="text-[13px] text-muted-foreground">No focus sessions in this period.</p>
                    ) : (
                      <ul className="-mr-2 max-h-[24rem] divide-y overflow-y-auto pr-2 [scrollbar-width:thin]">
                        {data.focus_sessions.map((f) => (
                          <li key={f.started_at} className="py-2.5 first:pt-0 last:pb-0">
                            <p className="flex justify-between gap-3 text-[13px]">
                              <span className="font-medium">
                                {formatDay(f.started_at.slice(0, 10), 'short')} · {formatClock(f.started_at, data.timezone)}–
                                {formatClock(f.ended_at, data.timezone)}
                              </span>
                              <span className="tabular">{formatSeconds(f.seconds)}</span>
                            </p>
                            <p className="truncate text-[12px] text-muted-foreground">{f.top_apps.join(', ')}</p>
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                </Card>
              </div>
            </div>
            <section aria-labelledby="trend-heading" className="space-y-3">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <h2 id="trend-heading" className="flex items-center gap-2 text-[15px] font-semibold">
                  <LineChart className="size-4 text-muted-foreground" aria-hidden /> Trends
                </h2>
                <SegmentedControl<TrendPeriod>
                  label="Trend period"
                  size="sm"
                  value={period}
                  onChange={setPeriod}
                  options={[
                    { value: 'daily', label: 'Daily' },
                    { value: 'weekly', label: 'Weekly' },
                    { value: 'monthly', label: 'Monthly' },
                  ]}
                />
              </div>
              {trend.data ? <TrendPanels trend={trend.data} onSelect={(p) => open(p.start, p.end)} /> : <Skeleton className="h-64" />}
            </section>
          </ProductivityReport>
        </div>
      )}
      <DataSheet target={target} onClose={() => setTarget(null)} />
      <UsageTitlesDialog employeeId={employeeId} range={dates} item={details} onClose={() => setDetails(null)} />
    </div>
  )
}
