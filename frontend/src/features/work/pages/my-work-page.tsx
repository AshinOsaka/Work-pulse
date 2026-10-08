import { AlertTriangle, CalendarDays, CheckCircle2, Clock, History, Hourglass, ListChecks, ListTodo, Pause, Play } from 'lucide-react'
import { Link } from 'react-router'

import { EmptyState } from '@/components/common/empty-state'
import { StatTile } from '@/components/common/stat-tile'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/misc'
import { formatSeconds } from '@/features/activity/format'
import { WidgetError } from '@/features/dashboard/components/widget'
import { useMyWork, useStopTimer } from '@/features/work/api'
import { TaskDrawer } from '@/features/work/components/task-drawer'
import { TaskSection } from '@/features/work/components/task-section'
import { TimerButton, useElapsed } from '@/features/work/components/timer'
import { clock, STATUS } from '@/features/work/meta'
import { useTaskParam } from '@/features/work/pages/project-page'
import { useDocumentTitle } from '@/hooks/use-document-title'
import { cn } from '@/lib/utils'

export default function MyWorkPage() {
  useDocumentTitle('My work')
  const query = useMyWork()
  const stop = useStopTimer()
  const [openTask, setOpenTask] = useTaskParam()
  const data = query.data
  const elapsed = useElapsed(data?.timer.running ? data.timer.started_at : null)

  if (query.isError) return <Card><WidgetError error={query.error} onRetry={() => void query.refetch()} /></Card>
  if (!data) return <div className="space-y-4"><Skeleton className="h-36" /><Skeleton className="h-64" /></div>
  if (!data.has_employee_record) {
    return <Card><EmptyState icon={ListTodo} title="No employee record" description="Your account isn't linked to an employee, so no tasks can be assigned to you." /></Card>
  }
  const current = data.current_task
  return (
    <div className="space-y-5">
      <Card className={cn('relative overflow-hidden p-5', data.timer.running && 'border-primary/40')}>
        {data.timer.running && <span className="absolute inset-x-0 top-0 h-0.5 animate-pulse bg-primary motion-reduce:animate-none" aria-hidden />}
        <div className="flex flex-wrap items-center gap-5">
          <div className="min-w-0 flex-1">
            <p className="text-[12px] font-medium tracking-wide text-muted-foreground uppercase">{data.timer.running ? 'Working on' : 'Current task'}</p>
            {current ? (
              <button type="button" onClick={() => setOpenTask(current.id)} className="mt-1 block max-w-full text-left">
                <span className="block truncate text-lg font-semibold">{current.title}</span>
                <span className="text-[12px] text-muted-foreground tabular">{current.reference} · {STATUS[current.status].label}</span>
              </button>
            ) : (
              <p className="mt-1 text-[14px] text-muted-foreground">Nothing in progress. Start a timer on one of your tasks below.</p>
            )}
          </div>
          <div className="text-right">
            <p className="text-3xl font-semibold tracking-tight tabular" aria-live="off">{data.timer.running ? clock(elapsed) : '0:00:00'}</p>
            <p className="text-[12px] text-muted-foreground">Today {formatSeconds(data.timer.today_seconds - (data.timer.running ? data.timer.elapsed_seconds : 0) + (data.timer.running ? elapsed : 0))}</p>
          </div>
          {data.timer.running ? (
            <Button variant="destructive" onClick={() => stop.mutate()} loading={stop.isPending}>
              <Pause className="fill-current" /> Stop
            </Button>
          ) : current ? (
            <TimerButton task={current} size="default" />
          ) : (
            <Button disabled>
              <Play /> Start
            </Button>
          )}
        </div>
      </Card>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatTile label="Open tasks" value={data.counts.open ?? 0} icon={ListTodo} />
        <StatTile label="In progress" value={data.counts.in_progress ?? 0} icon={Hourglass} />
        <StatTile label="Overdue" value={<span className={cn(data.counts.overdue && 'text-destructive')}>{data.counts.overdue ?? 0}</span>} icon={AlertTriangle} />
        <StatTile label="Completed today" value={data.counts.completed_today ?? 0} icon={CheckCircle2} />
      </div>

      <div className="grid gap-5 xl:grid-cols-2">
        <TaskSection title="Overdue" icon={AlertTriangle} tasks={data.overdue} empty="Nothing overdue." onOpen={setOpenTask} tone="danger" options={{ timer: true }} />
        <TaskSection title="Today" icon={Clock} tasks={data.today} empty="Nothing due today or in progress." onOpen={setOpenTask} options={{ timer: true }} />
      </div>
      <div className="grid gap-5 xl:grid-cols-2">
        <TaskSection
          title="My tasks"
          description="Everything open assigned to you, most urgent first"
          icon={ListChecks}
          tasks={data.assigned}
          empty="No open tasks assigned to you."
          onOpen={setOpenTask}
          options={{ timer: true }}
        />
        <div className="space-y-5">
          <TaskSection title="Next 7 days" icon={CalendarDays} tasks={data.upcoming} empty="Nothing due in the next week." onOpen={setOpenTask} options={{ timer: true }} />
          <TaskSection
            title="Recently completed"
            description="Last 7 days"
            icon={History}
            tasks={data.recently_completed}
            empty="Nothing completed in the last week."
            onOpen={setOpenTask}
            options={{ completed: true }}
          />
        </div>
      </div>
      <p className="text-[12px] text-muted-foreground">
        All your tasks are on each project's board. <Link to="/projects" className="font-medium text-primary hover:underline">Browse projects</Link>
      </p>
      <TaskDrawer taskId={openTask} onClose={() => setOpenTask(null)} />
    </div>
  )
}
