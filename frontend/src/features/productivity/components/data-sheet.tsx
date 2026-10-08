import { ArrowUpRight } from 'lucide-react'
import { Link } from 'react-router'

import { Spinner } from '@/components/ui/misc'
import { Sheet, SheetContent, SheetDescription, SheetTitle } from '@/components/ui/sheet'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { formatDay, formatSeconds } from '@/features/activity/format'
import { WidgetError } from '@/features/dashboard/components/widget'
import { useEmployeeProductivity, useTeamProductivity, type RangeParams, type ScopeParams } from '@/features/productivity/api'
import { CategoryBar } from '@/features/productivity/components/category-bar'
import { CATEGORY, SCORE_ORDER } from '@/features/productivity/meta'
import type { EmployeeProductivity, ProductivityMetrics, ProductivityScores, TeamProductivity } from '@/types/api'

export interface DataTarget extends RangeParams {
  scope: ScopeParams
  /** e.g. "Engineering" or a person's name; shown in the title. */
  label: string
}

const MEASUREMENTS: { key: keyof ProductivityMetrics; label: string }[] = [
  { key: 'work_seconds', label: 'Work time' },
  { key: 'active_seconds', label: 'Active time' },
  { key: 'idle_seconds', label: 'Idle time' },
  { key: 'extended_idle_seconds', label: 'Extended idle (15+ min stretches)' },
  { key: 'away_seconds', label: 'Away (between sessions)' },
  { key: 'productive_seconds', label: 'Productive apps & sites' },
  { key: 'neutral_seconds', label: 'Neutral' },
  { key: 'unproductive_seconds', label: 'Unproductive' },
  { key: 'unclassified_seconds', label: 'Unclassified' },
  { key: 'focus_seconds', label: 'In focus sessions' },
  { key: 'task_seconds', label: 'Logged on tasks' },
]

function rangeLabel({ start, end }: RangeParams) {
  return start === end ? formatDay(start) : `${formatDay(start, 'short')} – ${formatDay(end, 'short')}`
}

function Scores({ scores }: { scores: ProductivityScores }) {
  return (
    <ul className="grid gap-2 sm:grid-cols-2">
      {SCORE_ORDER.map((key) => {
        const s = scores[key]
        return (
          <li key={key} className="rounded-lg border bg-card px-3 py-2.5">
            <p className="flex items-baseline justify-between gap-2">
              <span className="text-[12px] font-medium text-muted-foreground">{s.label}</span>
              <span className="text-lg font-semibold tabular">{s.value === null ? '—' : `${s.value}%`}</span>
            </p>
            <p className="mt-0.5 font-mono text-[11px] text-muted-foreground">{s.formula}</p>
            <p className="mt-1 text-[11px] text-muted-foreground tabular">
              {s.components.map((c) => `${c.label} ${formatSeconds(c.seconds)}`).join(' · ')}
            </p>
            {s.value === null && s.reason && <p className="mt-1 text-[11px] text-muted-foreground">{s.reason}</p>}
          </li>
        )
      })}
    </ul>
  )
}

function Measurements({ metrics }: { metrics: ProductivityMetrics }) {
  return (
    <dl className="divide-y rounded-lg border bg-card text-[12px]">
      {MEASUREMENTS.map((m) => (
        <div key={m.key} className="flex justify-between gap-3 px-3 py-1.5">
          <dt className="text-muted-foreground">{m.label}</dt>
          <dd className="font-medium tabular">{formatSeconds(metrics[m.key] as number)}</dd>
        </div>
      ))}
      <div className="flex justify-between gap-3 px-3 py-1.5">
        <dt className="text-muted-foreground">Tasks completed · due and still open</dt>
        <dd className="font-medium tabular">
          {metrics.tasks_completed} · {metrics.tasks_due_open}
        </dd>
      </div>
    </dl>
  )
}

function TeamBody({ data }: { data: TeamProductivity }) {
  return (
    <section className="space-y-2">
      <h3 className="text-[13px] font-semibold">People ({data.rows.length})</h3>
      <p className="text-[11px] text-muted-foreground">Sorted by name. Each person&apos;s figures, not a ranking.</p>
      <div className="relative overflow-x-auto rounded-lg border bg-card">
        <Table>
          <caption className="sr-only">Figures per person for this period</caption>
          <TableHeader>
            <TableRow className="hover:bg-transparent">
              <TableHead className="pl-3">Person</TableHead>
              <TableHead className="text-right">Work</TableHead>
              <TableHead className="text-right">Active</TableHead>
              <TableHead className="text-right">Productive</TableHead>
              <TableHead className="pr-3 text-right">On tasks</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {data.rows.map((r) => (
              <TableRow key={r.employee.id}>
                <TableCell className="max-w-40 truncate pl-3">
                  <Link to={`/productivity/employees/${r.employee.id}`} className="hover:underline">
                    {r.employee.full_name}
                  </Link>
                </TableCell>
                <TableCell className="text-right tabular whitespace-nowrap">{formatSeconds(r.metrics.work_seconds)}</TableCell>
                <TableCell className="text-right tabular whitespace-nowrap">{formatSeconds(r.metrics.active_seconds)}</TableCell>
                <TableCell className="text-right tabular whitespace-nowrap">{formatSeconds(r.metrics.productive_seconds)}</TableCell>
                <TableCell className="pr-3 text-right tabular whitespace-nowrap">{formatSeconds(r.metrics.task_seconds)}</TableCell>
              </TableRow>
            ))}
            {data.rows.length === 0 && (
              <TableRow>
                <TableCell colSpan={5} className="py-6 text-center text-muted-foreground">
                  Nobody recorded work in this period.
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>
    </section>
  )
}

function EmployeeBody({ data }: { data: EmployeeProductivity }) {
  const top = data.usage.slice(0, 12)
  return (
    <section className="space-y-2">
      <h3 className="text-[13px] font-semibold">Applications and websites</h3>
      {top.length === 0 ? (
        <p className="text-[12px] text-muted-foreground">No application activity recorded.</p>
      ) : (
        <ul className="divide-y rounded-lg border bg-card text-[12px]">
          {top.map((u) => (
            <li key={`${u.kind}:${u.key}`} className="flex items-center gap-2 px-3 py-1.5">
              <span className="size-2 shrink-0 rounded-sm" style={{ background: CATEGORY[u.category].color }} aria-hidden />
              <span className="min-w-0 flex-1 truncate">{u.name}</span>
              <span className="text-muted-foreground">{CATEGORY[u.category].label}</span>
              <span className="w-14 text-right font-medium tabular">{formatSeconds(u.seconds)}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}

/**
 * "What is behind this point?" — opened from any chart point or bar. Shows the raw measurements, every
 * score with its formula and inputs, and the people (or applications) the numbers come from.
 */
export function DataSheet({ target, onClose }: { target: DataTarget | null; onClose: () => void }) {
  const range = target ? { start: target.start, end: target.end } : { start: '', end: '' }
  const employeeId = target?.scope.employee_id
  const team = useTeamProductivity({ ...range, team_id: target?.scope.team_id, department_id: target?.scope.department_id }, Boolean(target) && !employeeId)
  const person = useEmployeeProductivity(employeeId ?? '', range, Boolean(target) && Boolean(employeeId))
  const query = employeeId ? person : team
  const data = query.data as TeamProductivity | EmployeeProductivity | undefined
  const fresh = data && data.start === range.start && data.end === range.end

  return (
    <Sheet open={target !== null} onOpenChange={(open) => !open && onClose()}>
      <SheetContent side="right" className="w-full gap-0 overflow-y-auto bg-background sm:max-w-xl">
        <div className="border-b px-5 py-4 pr-12">
          <SheetTitle className="text-[15px] font-semibold">{target ? rangeLabel(target) : ''}</SheetTitle>
          <SheetDescription className="text-[12px] text-muted-foreground">{target?.label} · the data behind this point</SheetDescription>
        </div>
        <div className="space-y-5 px-5 py-5">
          {query.isError ? (
            <WidgetError error={query.error} onRetry={() => void query.refetch()} />
          ) : !fresh ? (
            <p className="flex items-center gap-2 text-[13px] text-muted-foreground">
              <Spinner /> Loading…
            </p>
          ) : (
            <>
              <section className="space-y-2">
                <h3 className="text-[13px] font-semibold">Measurements</h3>
                <Measurements metrics={data.totals} />
                <CategoryBar metrics={data.totals} />
              </section>
              <section className="space-y-2">
                <h3 className="text-[13px] font-semibold">Scores and how they are calculated</h3>
                <Scores scores={data.scores} />
              </section>
              {'rows' in data ? <TeamBody data={data} /> : <EmployeeBody data={data} />}
              {employeeId && (
                <Link to={`/productivity/employees/${employeeId}`} className="inline-flex items-center gap-1 text-[13px] font-medium text-primary hover:underline">
                  Open the full report <ArrowUpRight className="size-3.5" />
                </Link>
              )}
            </>
          )}
        </div>
      </SheetContent>
    </Sheet>
  )
}
