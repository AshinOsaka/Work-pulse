import { useMemo, useState } from 'react'
import { AlertTriangle, Ban, Columns3, List } from 'lucide-react'
import { Link } from 'react-router'

import { FilterSelect, toOptions } from '@/components/common/filter-select'
import { Person } from '@/components/common/person'
import { StatTile } from '@/components/common/stat-tile'
import { Card, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Progress, Skeleton } from '@/components/ui/misc'
import { SegmentedControl } from '@/components/ui/segmented-control'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { formatSeconds } from '@/features/activity/format'
import { WidgetError } from '@/features/dashboard/components/widget'
import { useTeams } from '@/features/people/api'
import { RANGES, rangeFor, type RangeKey } from '@/features/productivity/meta'
import { useTasks, useWorkSummary } from '@/features/work/api'
import { TaskBoard } from '@/features/work/components/board'
import { TaskDrawer } from '@/features/work/components/task-drawer'
import { TaskList } from '@/features/work/components/task-list'
import { TaskSection } from '@/features/work/components/task-section'
import { PROJECT_COLOR } from '@/features/work/meta'
import { useTaskParam } from '@/features/work/pages/project-page'
import { useDocumentTitle } from '@/hooks/use-document-title'
import { cn } from '@/lib/utils'
import { useAuthStore } from '@/stores/auth-store'

/** Managers: completion, time and workload across projects, plus a cross-project board. */
export default function TeamWorkPage() {
  useDocumentTitle('Team tasks')
  const timeZone = useAuthStore((s) => s.company?.timezone ?? 'UTC')
  const [range, setRange] = useState<RangeKey>('7d')
  const [teamId, setTeamId] = useState<string | null>(null)
  const [view, setView] = useState<'board' | 'list'>('board')
  const [openTask, setOpenTask] = useTaskParam()
  const teams = useTeams()
  const params = useMemo(() => ({ ...rangeFor(range, timeZone), team_id: teamId ?? undefined }), [range, timeZone, teamId])
  const summary = useWorkSummary(params)
  const tasks = useTasks({ team_id: teamId ?? undefined })
  const s = summary.data

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center gap-3">
        <SegmentedControl label="Period" value={range} onChange={setRange} options={RANGES} />
        <FilterSelect label="Team" value={teamId} onChange={setTeamId} options={toOptions(teams.data)} allLabel="All teams" />
      </div>

      {summary.isError ? (
        <Card>
          <WidgetError error={summary.error} onRetry={() => void summary.refetch()} />
        </Card>
      ) : !s ? (
        <Skeleton className="h-28" />
      ) : (
        <>
          <div className="grid gap-4 sm:grid-cols-3 xl:grid-cols-6">
            <StatTile label="Completed" value={String(s.completed)} hint={`${s.created} created in this period`} />
            <StatTile label="On time" value={s.on_time_rate === null ? '—' : `${s.on_time_rate}%`} hint={`${s.on_time_completed} of completed tasks with a due date`} />
            <StatTile label="Open" value={String(s.open)} hint="Across visible projects" />
            <StatTile label="Overdue" value={String(s.overdue)} hint="Open and past their due date" />
            <StatTile label="Blocked" value={String(s.blocked)} hint="Waiting on something" />
            <StatTile label="Time logged" value={formatSeconds(s.time_spent_seconds)} hint="Timers and manual entries" />
          </div>
          <div className="grid grid-cols-[minmax(0,1fr)] gap-5 xl:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
            <Card>
              <CardHeader>
                <CardTitle>Project progress</CardTitle>
                <CardDescription>Share of top-level tasks completed</CardDescription>
              </CardHeader>
              <ul className="space-y-3 px-5 pt-3 pb-5">
                {s.projects.map((p) => (
                  <li key={p.id}>
                    <div className="flex items-center gap-2 text-[13px]">
                      <span className={cn('size-2 rounded-full', PROJECT_COLOR[p.color])} aria-hidden />
                      <Link to={`/projects/${p.id}`} className="min-w-0 flex-1 truncate font-medium hover:underline">
                        {p.name}
                      </Link>
                      <span className="text-[12px] text-muted-foreground tabular">
                        {p.stats.completed}/{p.stats.total}
                        {p.stats.overdue > 0 && <span className="text-destructive"> · {p.stats.overdue} overdue</span>}
                      </span>
                      <span className="w-10 text-right font-medium tabular">{p.stats.progress}%</span>
                    </div>
                    <Progress value={p.stats.progress} className="mt-1.5" aria-label={`${p.name}: ${p.stats.progress}%`} />
                  </li>
                ))}
                {s.projects.length === 0 && <li className="text-[13px] text-muted-foreground">No active projects.</li>}
              </ul>
            </Card>
            <Card className="overflow-hidden">
              <CardHeader>
                <CardTitle>Workload</CardTitle>
                <CardDescription>Assigned tasks and logged time per person · not a ranking</CardDescription>
              </CardHeader>
              <div className="relative mt-3 overflow-x-auto border-t">
                <Table>
                  <caption className="sr-only">Workload per person</caption>
                  <TableHeader>
                    <TableRow className="hover:bg-transparent">
                      <TableHead className="pl-5">Person</TableHead>
                      <TableHead className="text-right">Open</TableHead>
                      <TableHead className="text-right">In progress</TableHead>
                      <TableHead className="text-right">Blocked</TableHead>
                      <TableHead className="text-right">Overdue</TableHead>
                      <TableHead className="text-right">Done</TableHead>
                      <TableHead className="pr-5 text-right">Time</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {s.members.map((m) => (
                      <TableRow key={m.employee.id}>
                        <TableCell className="pl-5">
                          <Person id={m.employee.id} name={m.employee.full_name} size="sm" />
                        </TableCell>
                        <TableCell className="text-right tabular whitespace-nowrap">{m.open_tasks}</TableCell>
                        <TableCell className="text-right tabular whitespace-nowrap">{m.in_progress}</TableCell>
                        <TableCell className={cn('text-right tabular', m.blocked > 0 && 'font-medium text-destructive')}>{m.blocked}</TableCell>
                        <TableCell className={cn('text-right tabular', m.overdue > 0 && 'font-medium text-destructive')}>{m.overdue}</TableCell>
                        <TableCell className="text-right tabular whitespace-nowrap">{m.completed_in_period}</TableCell>
                        <TableCell className="pr-5 text-right tabular whitespace-nowrap">{formatSeconds(m.time_spent_seconds)}</TableCell>
                      </TableRow>
                    ))}
                    {s.members.length === 0 && (
                      <TableRow>
                        <TableCell colSpan={7} className="py-8 text-center text-[13px] text-muted-foreground">
                          Nobody in this selection has tasks yet.
                        </TableCell>
                      </TableRow>
                    )}
                  </TableBody>
                </Table>
              </div>
            </Card>
          </div>
          <div className="grid gap-5 xl:grid-cols-2">
            <TaskSection
              title="Blocked tasks"
              description="Open tasks marked blocked, most urgent first"
              icon={Ban}
              tasks={s.blocked_tasks}
              empty="Nothing is blocked."
              onOpen={setOpenTask}
              tone="danger"
              options={{ assignees: true }}
            />
            <TaskSection
              title="Overdue tasks"
              description="Open and past their due date"
              icon={AlertTriangle}
              tasks={s.overdue_tasks}
              empty="Nothing is overdue."
              onOpen={setOpenTask}
              tone="danger"
              options={{ assignees: true }}
            />
          </div>
        </>
      )}

      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-[15px] font-semibold">Team task board</h2>
        <SegmentedControl
          label="View"
          value={view}
          onChange={setView}
          options={[
            { value: 'board', label: 'Board', icon: Columns3 },
            { value: 'list', label: 'List', icon: List },
          ]}
        />
      </div>
      {!tasks.data ? (
        <Skeleton className="h-64" />
      ) : view === 'board' ? (
        <TaskBoard tasks={tasks.data} onOpen={setOpenTask} showProject />
      ) : (
        <Card className="overflow-hidden py-0">
          <TaskList tasks={tasks.data} onOpen={setOpenTask} showProject />
        </Card>
      )}
      <TaskDrawer taskId={openTask} onClose={() => setOpenTask(null)} />
    </div>
  )
}
