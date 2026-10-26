import { useState } from 'react'
import { Activity, CircleOff } from 'lucide-react'
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'

import { EmptyState } from '@/components/common/empty-state'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Skeleton } from '@/components/ui/misc'
import { formatClock } from '@/features/dashboard/components/org/shared'
import { useEmployeeActivity } from '@/features/activity/api'
import { useEmployeeProductivity } from '@/features/productivity/api'
import { CATEGORY } from '@/features/productivity/meta'
import { usePrefersReducedMotion } from '@/hooks/use-now'
import { formatDay } from '@/features/activity/format'
import { formatTime } from '@/lib/format'
import { cn } from '@/lib/utils'
import type { UsageCategory } from '@/types/api'

type Tab = 'productive' | 'unproductive' | 'neutral' | 'idle' | 'activity'

interface Props {
  employeeId: string
  employeeName: string
  day: string
  open: boolean
  onOpenChange: (open: boolean) => void
}

const CAT_STYLE: Record<'productive' | 'unproductive' | 'neutral', { dot: string; text: string }> = {
  productive: { dot: 'bg-cat-productive', text: 'text-cat-productive' },
  unproductive: { dot: 'bg-cat-unproductive', text: 'text-cat-unproductive' },
  neutral: { dot: 'bg-cat-neutral', text: 'text-cat-neutral' },
}

export function ActivityDetailsDialog({ employeeId, employeeName, day, open, onOpenChange }: Props) {
  const [tab, setTab] = useState<Tab>('productive')
  const prod = useEmployeeProductivity(employeeId, { start: day, end: day }, open)
  const act = useEmployeeActivity(employeeId, day)

  const usage = prod.data?.usage ?? []
  const byCat = (c: UsageCategory) => usage.filter((u) => u.category === c).sort((a, b) => b.seconds - a.seconds)
  const productive = byCat('productive')
  const unproductive = byCat('unproductive')
  const neutral = byCat('neutral')
  // "Idle" = foreground segments with no recorded input (activity level 0): the app stayed open while away.
  const segments = act.data?.segments ?? []
  const idle = segments.filter((s) => s.active_seconds === 0 && s.duration_seconds > 0).sort((a, b) => a.started_at.localeCompare(b.started_at))
  const activitySeries = segments.map((s) => ({ time: s.started_at, level: s.activity_level }))

  const loading = prod.isPending || act.isPending

  const tabs: { key: Tab; label: string; count: number }[] = [
    { key: 'productive', label: 'Productive', count: productive.length },
    { key: 'unproductive', label: 'Unproductive', count: unproductive.length },
    { key: 'neutral', label: 'Neutral', count: neutral.length },
    { key: 'idle', label: 'Idle', count: idle.length },
    { key: 'activity', label: 'Activity Level', count: -1 },
  ]

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[85vh] gap-0 overflow-hidden p-0 sm:max-w-3xl">
        <DialogHeader className="space-y-1 px-6 pt-6">
          <DialogTitle>{employeeName}</DialogTitle>
          <DialogDescription>Activity details for {formatDay(day)}</DialogDescription>
        </DialogHeader>

        <div className="flex gap-1 overflow-x-auto border-b px-4 pt-3">
          {tabs.map((t) => (
            <button
              key={t.key}
              type="button"
              onClick={() => setTab(t.key)}
              className={cn(
                'flex items-center gap-1.5 border-b-2 px-3 pb-2.5 text-[13px] font-medium whitespace-nowrap transition-colors',
                tab === t.key ? 'border-primary text-foreground' : 'border-transparent text-muted-foreground hover:text-foreground',
              )}
            >
              {t.label}
              {t.count >= 0 && (
                <span className={cn('rounded-full px-1.5 text-[11px]', tab === t.key ? 'bg-primary/10 text-primary' : 'bg-muted text-muted-foreground')}>
                  {t.count}
                </span>
              )}
            </button>
          ))}
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto p-6">
          {loading ? (
            <div className="space-y-2">
              {[0, 1, 2, 3].map((i) => (
                <Skeleton key={i} className="h-10" />
              ))}
            </div>
          ) : tab === 'activity' ? (
            activitySeries.length ? (
              <div>
                <p className="mb-1 text-[13px] font-semibold">Activity intensity</p>
                <p className="mb-4 text-[12px] text-muted-foreground">
                  Share of each span with keyboard or mouse input (0–100). WorkPulse never records what is typed or counts keystrokes.
                </p>
                <ActivityGraph data={activitySeries} />
              </div>
            ) : (
              <EmptyState size="sm" icon={Activity} title="No activity recorded" description="No application activity for this day." />
            )
          ) : tab === 'idle' ? (
            idle.length ? (
              <table className="w-full border-collapse text-[13px]">
                <thead>
                  <tr className="border-b text-left text-[11px] font-medium tracking-wide text-muted-foreground uppercase">
                    <th className="pb-2 font-medium">Application/Website</th>
                    <th className="pb-2 font-medium">Idle start</th>
                    <th className="pb-2 font-medium">Idle end</th>
                    <th className="pb-2 text-right font-medium">Duration</th>
                  </tr>
                </thead>
                <tbody>
                  {idle.map((s, i) => (
                    <tr key={`${s.app_id}-${i}`} className="border-b last:border-0">
                      <td className="py-2.5 font-medium">{s.app_name}</td>
                      <td className="py-2.5 text-muted-foreground">{formatTime(s.started_at)}</td>
                      <td className="py-2.5 text-muted-foreground">{formatTime(s.ended_at)}</td>
                      <td className="py-2.5 text-right tabular text-cat-neutral">{formatClock(s.duration_seconds)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <EmptyState size="sm" icon={CircleOff} title="No idle time found" description="No idle periods recorded for this day." />
            )
          ) : (
            <UsageList
              items={tab === 'productive' ? productive : tab === 'unproductive' ? unproductive : neutral}
              category={tab}
            />
          )}
        </div>
      </DialogContent>
    </Dialog>
  )
}

function UsageList({ items, category }: { items: { key: string; name: string; seconds: number }[]; category: 'productive' | 'unproductive' | 'neutral' }) {
  const style = CAT_STYLE[category]
  if (!items.length) {
    return <EmptyState size="sm" icon={CircleOff} title={`No ${CATEGORY[category].label.toLowerCase()} activities found`} description="No entries to show." />
  }
  return (
    <div>
      <p className="mb-3 text-[13px] font-semibold">{CATEGORY[category].label} activities · {items.length} total</p>
      <ul className="divide-y">
        {items.map((u) => (
          <li key={u.key} className="flex items-center justify-between gap-4 py-2.5">
            <span className="flex min-w-0 items-center gap-2.5">
              <span className={cn('size-2 shrink-0 rounded-full', style.dot)} aria-hidden />
              <span className="truncate text-[13px]">{u.name}</span>
            </span>
            <span className={cn('shrink-0 rounded px-2 py-0.5 text-[12px] font-medium tabular', style.text)}>{formatClock(u.seconds)}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}

function ActivityGraph({ data }: { data: { time: string; level: number }[] }) {
  const reduced = usePrefersReducedMotion()
  return (
    <figure className="h-64">
      <figcaption className="sr-only">Activity intensity over the day</figcaption>
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ top: 8, right: 16, bottom: 0, left: 0 }}>
          <defs>
            <linearGradient id="act-grad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="var(--cat-productive)" stopOpacity={0.3} />
              <stop offset="100%" stopColor="var(--cat-productive)" stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid vertical={false} stroke="var(--chart-grid)" />
          <XAxis
            dataKey="time"
            tickFormatter={(t: string) => formatTime(t)}
            tickLine={false}
            axisLine={false}
            minTickGap={40}
            tick={{ fill: 'var(--muted-foreground)', fontSize: 11 }}
          />
          <YAxis domain={[0, 100]} ticks={[0, 25, 50, 75, 100]} tickLine={false} axisLine={false} width={32} tick={{ fill: 'var(--muted-foreground)', fontSize: 11 }} />
          <Tooltip
            cursor={{ stroke: 'var(--muted-foreground)', strokeOpacity: 0.4 }}
            formatter={(v) => [`${v as number}%`, 'Intensity']}
            labelFormatter={(t) => formatTime(t as string)}
            contentStyle={{ fontSize: 12, borderRadius: 8 }}
          />
          <Area type="monotone" dataKey="level" stroke="var(--cat-productive)" strokeWidth={2} fill="url(#act-grad)" dot={false} isAnimationActive={!reduced} animationDuration={500} />
        </AreaChart>
      </ResponsiveContainer>
    </figure>
  )
}
