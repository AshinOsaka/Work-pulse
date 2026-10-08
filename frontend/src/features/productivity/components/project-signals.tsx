import { FolderKanban } from 'lucide-react'
import { Link } from 'react-router'

import { Card, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Progress } from '@/components/ui/misc'
import { formatSeconds } from '@/features/activity/format'
import { PROJECT_COLOR } from '@/features/work/meta'
import { cn } from '@/lib/utils'
import type { ProjectSignal } from '@/types/api'

/** Project progress as a signal: work done on each project in the period, next to where the project stands. */
export function ProjectSignals({ projects }: { projects: ProjectSignal[] }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <FolderKanban className="size-4 text-muted-foreground" aria-hidden /> Project progress
        </CardTitle>
        <CardDescription>Time logged and tasks completed in this period, and each project&apos;s overall progress.</CardDescription>
      </CardHeader>
      {projects.length === 0 ? (
        <p className="px-5 pt-3 pb-5 text-[13px] text-muted-foreground">No time logged on project tasks and no tasks completed in this period.</p>
      ) : (
        <ul className="mt-3 divide-y border-t">
          {projects.map((p) => (
            <li key={p.id} className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-4 gap-y-1.5 px-5 py-3 sm:grid-cols-[minmax(0,1fr)_6rem_6rem_minmax(8rem,12rem)]">
              <Link to={`/projects/${p.id}`} className="flex min-w-0 items-center gap-2 text-[13px] font-medium hover:underline">
                <span className={cn('size-2 shrink-0 rounded-full', PROJECT_COLOR[p.color])} aria-hidden />
                <span className="truncate">{p.name}</span>
                <span className="text-[11px] font-normal text-muted-foreground">{p.key}</span>
              </Link>
              <span className="text-right text-[12px] tabular">
                {formatSeconds(p.task_seconds)} <span className="text-muted-foreground">logged</span>
              </span>
              <span className="text-right text-[12px] tabular sm:text-left">
                {p.tasks_completed} <span className="text-muted-foreground">completed</span>
              </span>
              <span className="col-span-2 flex items-center gap-2 sm:col-span-1">
                <Progress value={p.progress} className="h-1.5 flex-1" aria-label={`${p.name}: ${p.progress}% of tasks completed`} />
                <span className="w-16 text-right text-[11px] text-muted-foreground tabular">
                  {p.progress}% of {p.total_tasks}
                </span>
              </span>
            </li>
          ))}
        </ul>
      )}
    </Card>
  )
}
