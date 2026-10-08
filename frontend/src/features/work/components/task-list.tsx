import { useMemo, useState } from 'react'
import { ArrowUpDown } from 'lucide-react'
import { toast } from 'sonner'

import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { formatSeconds } from '@/features/activity/format'
import { useUpdateTask } from '@/features/work/api'
import { LabelChips } from '@/features/work/components/labels'
import { Assignees, DueChip } from '@/features/work/components/task-card'
import { PRIORITIES, PRIORITY, STATUS, STATUSES } from '@/features/work/meta'
import { errorMessage } from '@/lib/api-client'
import { cn } from '@/lib/utils'
import type { Task, TaskStatus } from '@/types/api'

type SortKey = 'status' | 'priority' | 'due' | 'updated'

const SORTERS: Record<SortKey, (a: Task, b: Task) => number> = {
  status: (a, b) => STATUSES.indexOf(a.status) - STATUSES.indexOf(b.status) || a.rank - b.rank,
  priority: (a, b) => PRIORITIES.indexOf(a.priority) - PRIORITIES.indexOf(b.priority),
  due: (a, b) => (a.due_date ?? '9999').localeCompare(b.due_date ?? '9999'),
  updated: (a, b) => b.updated_at.localeCompare(a.updated_at),
}

export function StatusSelect({ task, compact }: { task: Task; compact?: boolean }) {
  const update = useUpdateTask()
  return (
    <Select
      value={task.status}
      disabled={!task.can_edit}
      onValueChange={(v) => update.mutate({ id: task.id, status: v as TaskStatus }, { onError: (e) => toast.error(errorMessage(e)) })}
    >
      <SelectTrigger size="sm" className={cn(compact ? 'w-36' : 'w-40')} aria-label={`Status of ${task.reference}`} onClick={(e) => e.stopPropagation()}>
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {STATUSES.map((s) => (
          <SelectItem key={s} value={s}>
            <span className="inline-flex items-center gap-2">
              <span className={cn('size-2 rounded-full', STATUS[s].dot)} aria-hidden />
              {STATUS[s].label}
            </span>
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}

/** Sortable table of tasks with inline status changes. */
export function TaskList({ tasks, onOpen }: { tasks: Task[]; onOpen: (id: string) => void; showProject?: boolean }) {
  const [sort, setSort] = useState<SortKey>('status')
  const rows = useMemo(() => [...tasks].sort(SORTERS[sort]), [tasks, sort])
  const header = (key: SortKey, label: string, className?: string) => (
    <TableHead className={className} aria-sort={sort === key ? 'ascending' : undefined}>
      <button type="button" onClick={() => setSort(key)} className="inline-flex items-center gap-1 hover:text-foreground">
        {label}
        <ArrowUpDown className={cn('size-3', sort === key ? 'opacity-100' : 'opacity-40')} aria-hidden />
      </button>
    </TableHead>
  )
  return (
    <div className="relative overflow-x-auto">
      <Table>
        <caption className="sr-only">Tasks</caption>
        <TableHeader>
          <TableRow className="hover:bg-transparent">
            <TableHead className="pl-5">Task</TableHead>
            {header('status', 'Status')}
            {header('priority', 'Priority')}
            <TableHead>Assignees</TableHead>
            {header('due', 'Due')}
            <TableHead className="pr-5 text-right">Time</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((task) => {
            const priority = PRIORITY[task.priority]
            return (
              <TableRow key={task.id} className="cursor-pointer" onClick={() => onOpen(task.id)}>
                <TableCell className="max-w-96 pl-5">
                  <button type="button" className="block w-full min-w-0 text-left" onClick={() => onOpen(task.id)}>
                    <span className="text-[11px] text-muted-foreground tabular">{task.reference}</span>
                    <span className={cn('block truncate font-medium', task.status === 'COMPLETED' && 'text-muted-foreground line-through')}>{task.title}</span>
                    <LabelChips labels={task.labels} className="mt-1" />
                  </button>
                </TableCell>
                <TableCell onClick={(e) => e.stopPropagation()}>
                  <StatusSelect task={task} compact />
                </TableCell>
                <TableCell>
                  <span className="inline-flex items-center gap-1.5 text-[13px]">
                    <priority.icon className={cn('size-3.5', priority.className)} aria-hidden />
                    {priority.label}
                  </span>
                </TableCell>
                <TableCell>
                  <Assignees task={task} />
                </TableCell>
                <TableCell>{task.due_date ? <DueChip task={task} /> : <span className="text-muted-foreground">—</span>}</TableCell>
                <TableCell className="pr-5 text-right tabular whitespace-nowrap text-muted-foreground">
                  {task.time_spent_seconds ? formatSeconds(task.time_spent_seconds) : '—'}
                </TableCell>
              </TableRow>
            )
          })}
          {rows.length === 0 && (
            <TableRow>
              <TableCell colSpan={6} className="py-10 text-center text-[13px] text-muted-foreground">
                No tasks match.
              </TableCell>
            </TableRow>
          )}
        </TableBody>
      </Table>
    </div>
  )
}
