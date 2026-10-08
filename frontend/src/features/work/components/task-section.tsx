import type { ReactNode } from 'react'
import type { LucideIcon } from 'lucide-react'

import { Card, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { LabelChips } from '@/features/work/components/labels'
import { Assignees, DueChip } from '@/features/work/components/task-card'
import { TimerButton } from '@/features/work/components/timer'
import { PRIORITY, STATUS } from '@/features/work/meta'
import { formatRelative } from '@/lib/format'
import { cn } from '@/lib/utils'
import type { Task } from '@/types/api'

export interface TaskRowOptions {
  /** Offer start/stop timer (my own work). */
  timer?: boolean
  /** Show who it's assigned to (team views). */
  assignees?: boolean
  /** Show when it was completed instead of the due date. */
  completed?: boolean
}

export function TaskRow({ task, onOpen, options = {} }: { task: Task; onOpen: (id: string) => void; options?: TaskRowOptions }) {
  const priority = PRIORITY[task.priority]
  return (
    <li className="flex items-center gap-3 px-5 py-2.5 hover:bg-muted/50">
      <button type="button" onClick={() => onOpen(task.id)} className="flex min-w-0 flex-1 items-center gap-3 text-left">
        <priority.icon className={cn('size-3.5 shrink-0', priority.className)} aria-label={`${priority.label} priority`} />
        <span className="min-w-0 flex-1">
          <span className={cn('block truncate text-[13px] font-medium', options.completed && 'text-muted-foreground line-through decoration-muted-foreground/40')}>
            {task.title}
          </span>
          <span className="flex flex-wrap items-center gap-x-2 gap-y-1 text-[11px] text-muted-foreground">
            <span className="tabular">{task.reference}</span>
            <span className="inline-flex items-center gap-1">
              <span className={cn('size-1.5 rounded-full', STATUS[task.status].dot)} aria-hidden />
              {STATUS[task.status].label}
            </span>
            <LabelChips labels={task.labels} max={2} />
          </span>
        </span>
        {options.assignees && <Assignees task={task} />}
        {options.completed ? (
          task.completed_at && <span className="shrink-0 text-[11px] text-muted-foreground">{formatRelative(task.completed_at)}</span>
        ) : (
          <DueChip task={task} />
        )}
      </button>
      {options.timer && <TimerButton task={task} />}
    </li>
  )
}

export function TaskSection({
  title,
  description,
  icon: Icon,
  tasks,
  empty,
  onOpen,
  tone,
  options,
  action,
  className,
}: {
  title: string
  description?: string
  icon: LucideIcon
  tasks: Task[]
  empty: string
  onOpen: (id: string) => void
  tone?: 'danger'
  options?: TaskRowOptions
  action?: ReactNode
  className?: string
}) {
  return (
    <Card className={cn('overflow-hidden', className)}>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Icon className={cn('size-4', tone === 'danger' ? 'text-destructive' : 'text-muted-foreground')} aria-hidden /> {title}
          <span className="rounded-full bg-muted px-1.5 text-[11px] font-normal text-muted-foreground tabular">{tasks.length}</span>
          {action && <span className="ml-auto font-normal">{action}</span>}
        </CardTitle>
        {description && <CardDescription>{description}</CardDescription>}
      </CardHeader>
      {tasks.length === 0 ? (
        <p className="px-5 pt-2 pb-5 text-[13px] text-muted-foreground">{empty}</p>
      ) : (
        <ul className="mt-2 max-h-[420px] divide-y overflow-y-auto border-t">
          {tasks.map((t) => (
            <TaskRow key={t.id} task={t} onOpen={onOpen} options={options} />
          ))}
        </ul>
      )}
    </Card>
  )
}
