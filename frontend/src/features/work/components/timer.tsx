import { Pause, Play, Timer as TimerIcon } from 'lucide-react'
import { Link } from 'react-router'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { useStartTimer, useStopTimer, useTimer } from '@/features/work/api'
import { clock } from '@/features/work/meta'
import { useNow } from '@/hooks/use-now'
import { errorMessage } from '@/lib/api-client'
import { formatSeconds } from '@/features/activity/format'
import { cn } from '@/lib/utils'
import { useAuthStore } from '@/stores/auth-store'
import type { Task } from '@/types/api'

/** Seconds on the running timer, ticking locally between server refreshes. */
export function useElapsed(startedAt: string | null | undefined): number {
  const now = useNow(1000)
  return startedAt ? Math.max(0, (now - new Date(startedAt).getTime()) / 1000) : 0
}

export function TimerButton({ task, size = 'sm', className }: { task: Task; size?: 'sm' | 'default'; className?: string }) {
  const start = useStartTimer()
  const stop = useStopTimer()
  const running = task.timer_running
  if (task.status === 'COMPLETED' && !running) return null
  return (
    <Button
      size={size}
      variant={running ? 'destructive' : 'outline'}
      className={className}
      loading={start.isPending || stop.isPending}
      onClick={(e) => {
        e.stopPropagation()
        const onError = (error: unknown) => toast.error(errorMessage(error))
        if (running) stop.mutate(undefined, { onError })
        else start.mutate(task.id, { onError, onSuccess: () => toast.success(`Tracking time on ${task.reference}`) })
      }}
      aria-label={running ? `Stop timer on ${task.reference}` : `Start timer on ${task.reference}`}
    >
      {running ? <Pause className="fill-current" /> : <Play className="fill-current" />}
      {running ? 'Stop' : 'Start timer'}
    </Button>
  )
}

/** Topbar indicator: always visible while a timer runs, so it is never forgotten. */
export function TopbarTimer() {
  const hasEmployee = useAuthStore((s) => Boolean(s.user?.employee_id))
  const { data } = useTimer(hasEmployee)
  const stop = useStopTimer()
  const elapsed = useElapsed(data?.running ? data.started_at : null)
  if (!data?.running || !data.task) return null
  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button variant="ghost" size="sm" className="h-8 gap-1.5 rounded-full bg-primary-soft px-2.5 text-[12px] text-primary-soft-foreground hover:bg-primary-soft/80">
          <TimerIcon className="size-3.5 animate-pulse motion-reduce:animate-none" aria-hidden />
          <span className="font-semibold tabular">{clock(elapsed)}</span>
          <span className="hidden max-w-40 truncate md:inline">{data.task.reference}</span>
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-72 space-y-3">
        <div>
          <p className="text-[12px] text-muted-foreground">Tracking time on</p>
          <p className="text-[13px] font-medium">
            {data.task.reference} · {data.task.title}
          </p>
          <p className="mt-1 text-[12px] text-muted-foreground">
            Today: <span className={cn('font-medium text-foreground tabular')}>{formatSeconds(data.today_seconds)}</span>
          </p>
        </div>
        <div className="flex gap-2">
          <Button size="sm" variant="destructive" className="flex-1" loading={stop.isPending} onClick={() => stop.mutate()}>
            <Pause className="fill-current" /> Stop
          </Button>
          <Button asChild size="sm" variant="outline" className="flex-1">
            <Link to={`/projects/${data.task.project_id}?task=${data.task.id}`}>Open task</Link>
          </Button>
        </div>
      </PopoverContent>
    </Popover>
  )
}
