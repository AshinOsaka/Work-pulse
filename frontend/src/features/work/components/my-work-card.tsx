import { AlertTriangle, ArrowRight, Clock, ListTodo } from 'lucide-react'
import { Link } from 'react-router'

import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { formatSeconds } from '@/features/activity/format'
import { useMyWork } from '@/features/work/api'
import { TimerButton, useElapsed } from '@/features/work/components/timer'
import { clock } from '@/features/work/meta'
import { cn } from '@/lib/utils'
import { useAuthStore } from '@/stores/auth-store'

/** Dashboard strip for everyone with an employee record: current task, timer, today, overdue. */
export function MyWorkCard() {
  const hasEmployee = useAuthStore((s) => Boolean(s.user?.employee_id))
  const query = useMyWork()
  const data = query.data
  const elapsed = useElapsed(data?.timer.running ? data.timer.started_at : null)
  if (!hasEmployee || !data?.has_employee_record) return null
  const current = data.current_task
  return (
    <Card className={cn('flex-row flex-wrap items-center gap-x-6 gap-y-3 px-5 py-4', data.timer.running && 'border-primary/40')}>
      <div className="min-w-0 flex-1">
        <p className="text-[11px] font-medium tracking-wide text-muted-foreground uppercase">{data.timer.running ? 'Working on' : 'Current task'}</p>
        {current ? (
          <Link to={`/projects/my-work?task=${current.id}`} className="block truncate text-[14px] font-semibold hover:underline">
            {current.reference} · {current.title}
          </Link>
        ) : (
          <p className="text-[13px] text-muted-foreground">No task in progress</p>
        )}
      </div>
      {data.timer.running && <span className="text-xl font-semibold tabular">{clock(elapsed)}</span>}
      {current && <TimerButton task={current} />}
      <div className="flex items-center gap-4 text-[13px]">
        <span className="inline-flex items-center gap-1.5">
          <ListTodo className="size-4 text-muted-foreground" aria-hidden /> <b className="tabular">{data.today.length}</b> today
        </span>
        <span className={cn('inline-flex items-center gap-1.5', data.overdue.length > 0 && 'text-destructive')}>
          <AlertTriangle className="size-4" aria-hidden /> <b className="tabular">{data.overdue.length}</b> overdue
        </span>
        <span className="inline-flex items-center gap-1.5 text-muted-foreground">
          <Clock className="size-4" aria-hidden /> {formatSeconds(data.timer.today_seconds)} today
        </span>
      </div>
      <Button asChild size="sm" variant="ghost">
        <Link to="/projects/my-work">
          My work <ArrowRight />
        </Link>
      </Button>
    </Card>
  )
}
