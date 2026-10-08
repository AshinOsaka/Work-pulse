import type { HTMLAttributes } from 'react'
import { CalendarClock, CheckSquare, MessageSquare, Paperclip, Timer } from 'lucide-react'

import { AvatarGroup } from '@/components/common/person'
import { LabelChips } from '@/features/work/components/labels'
import { formatDue, PRIORITY } from '@/features/work/meta'
import { cn } from '@/lib/utils'
import type { Task } from '@/types/api'

export function Assignees({ task, max = 3 }: { task: Task; max?: number }) {
  if (!task.assignees.length) return <span className="text-[11px] text-muted-foreground">Unassigned</span>
  return <AvatarGroup people={task.assignees} max={max} size="xs" />
}

export function DueChip({ task }: { task: Task }) {
  if (!task.due_date) return null
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[11px] tabular',
        task.overdue ? 'bg-destructive-soft font-medium text-destructive' : 'bg-muted text-muted-foreground',
      )}
      title={task.overdue ? 'Overdue' : 'Due date'}
    >
      <CalendarClock className="size-3" aria-hidden />
      {formatDue(task.due_date)}
      {task.overdue && <span className="sr-only">(overdue)</span>}
    </span>
  )
}

interface TaskCardProps extends HTMLAttributes<HTMLSpanElement> {
  task: Task
  dragging?: boolean
  showProject?: boolean
}

/** A board card. The whole card opens the task; drag handling is attached by the board. */
export function TaskCard({ task, dragging, showProject, className, ...props }: TaskCardProps) {
  const priority = PRIORITY[task.priority]
  return (
    <span
      className={cn(
        'group block rounded-lg border bg-card p-3 text-left shadow-xs transition',
        'hover:border-primary/40 hover:shadow-card',
        dragging && 'border-primary/50 shadow-elevated',
        task.status === 'COMPLETED' && 'bg-subtle',
        className,
      )}
      {...props}
    >
      <span className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
        <priority.icon className={cn('size-3.5', priority.className)} aria-label={`${priority.label} priority`} />
        <span className="font-medium tabular">{task.reference}</span>
        {task.timer_running && (
          <span className="ml-auto inline-flex items-center gap-1 rounded bg-primary-soft px-1.5 py-0.5 text-[10px] font-medium text-primary-soft-foreground">
            <Timer className="size-3 animate-pulse motion-reduce:animate-none" aria-hidden /> Tracking
          </span>
        )}
        {showProject && !task.timer_running && <span className="ml-auto truncate">{task.project_key}</span>}
      </span>
      <span className={cn('mt-1 block line-clamp-3 text-[13px] font-medium', task.status === 'COMPLETED' && 'line-through decoration-muted-foreground/50')}>
        {task.title}
      </span>
      <LabelChips labels={task.labels} className="mt-2" />
      <span className="mt-2.5 flex flex-wrap items-center gap-x-2.5 gap-y-1.5 text-[11px] text-muted-foreground">
        <DueChip task={task} />
        {task.subtask_total > 0 && (
          <span className="inline-flex items-center gap-1 tabular" title="Subtasks done">
            <CheckSquare className="size-3" aria-hidden /> {task.subtask_done}/{task.subtask_total}
          </span>
        )}
        {task.comment_count > 0 && (
          <span className="inline-flex items-center gap-1 tabular" title="Comments">
            <MessageSquare className="size-3" aria-hidden /> {task.comment_count}
          </span>
        )}
        {task.attachment_count > 0 && (
          <span className="inline-flex items-center gap-1 tabular" title="Attachments">
            <Paperclip className="size-3" aria-hidden /> {task.attachment_count}
          </span>
        )}
        <span className="ml-auto">
          <Assignees task={task} />
        </span>
      </span>
    </span>
  )
}
