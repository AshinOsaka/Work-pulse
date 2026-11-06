import { useState } from 'react'
import { CircleOff, Keyboard } from 'lucide-react'
import { Area, AreaChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'

import { EmptyState } from '@/components/common/empty-state'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Skeleton } from '@/components/ui/misc'
import { formatClock } from '@/features/dashboard/components/org/shared'
import { useEmployeeActivity } from '@/features/activity/api'
import { useEmployeeProductivity } from '@/features/productivity/api'
import { CATEGORY } from '@/features/productivity/meta'
import { usePrefersReducedMotion } from '@/hooks/use-now'
import { formatDay, todayIn } from '@/features/activity/format'
import { formatTime } from '@/lib/format'
import { cn } from '@/lib/utils'
import type { ActivitySegment, UsageCategory } from '@/types/api'

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

export function ActivityDetailsDialog({ employeeId, employeeName, day: initialDay, open, onOpenChange }: Props) {
  const [tab, setTab] = useState<Tab>('productive')
  // Opens on the day that was clicked; the date box lets the viewer look at any other day.
  const [day, setDay] = useState(initialDay)
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
  const inputSeries = bucketInput(segments)
  const today = act.data ? todayIn(act.data.timezone) : undefined

  const loading = prod.isPending || act.isPending

  const tabs: { key: Tab; label: string; count: number }[] = [
    { key: 'productive', label: 'Productive', count: productive.length },
    { key: 'unproductive', label: 'Unproductive', count: unproductive.length },
    { key: 'neutral', label: 'Neutral', count: neutral.length },
    { key: 'idle', label: 'Idle', count: idle.length },
    { key: 'activity', label: 'Keyboard & Mouse', count: -1 },
  ]

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex max-h-[85vh] flex-col gap-0 overflow-hidden p-0 sm:max-w-3xl">
        <div className="flex flex-wrap items-end justify-between gap-3 px-6 pt-6 pr-14">
          <DialogHeader className="space-y-1">
            <DialogTitle>{employeeName}</DialogTitle>
            <DialogDescription>Activity details for {formatDay(day)}</DialogDescription>
          </DialogHeader>
          <label className="flex items-center gap-2 text-[12px] text-muted-foreground">
            Date
            <input
              type="date"
              value={day}
              max={today}
              onChange={(e) => e.target.value && setDay(e.target.value)}
              className="h-8 rounded-md border border-input bg-card px-2.5 text-[13px] text-foreground shadow-xs outline-none focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/25"
            />
          </label>
        </div>

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
            inputSeries ? (
              <div>
                <p className="mb-1 text-[13px] font-semibold">Keyboard &amp; mouse activity</p>
                <p className="mb-4 text-[12px] text-muted-foreground">
                  Key presses and mouse actions in every 10 minutes. WorkPulse only counts them and never records what is typed.
                </p>
                <div className="mb-4 grid grid-cols-2 gap-3">
                  <div className="rounded-lg border bg-card p-3">
                    <p className="text-lg font-semibold tabular">{inputSeries.keys.toLocaleString()}</p>
                    <p className="text-[12px] text-muted-foreground">Keyboard strokes</p>
                  </div>
                  <div className="rounded-lg border bg-card p-3">
                    <p className="text-lg font-semibold tabular">{inputSeries.mouse.toLocaleString()}</p>
                    <p className="text-[12px] text-muted-foreground">Mouse strokes</p>
                  </div>
                </div>
                <InputGraph data={inputSeries.points} />
              </div>
            ) : (
              <EmptyState
                size="sm"
                icon={Keyboard}
                title="No keyboard or mouse counts for this day"
                description="Counts appear when keyboard & mouse tracking is on in Settings → Monitoring & privacy and the agent records activity."
              />
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

const BUCKET_MS = 10 * 60 * 1000
const MOUSE_COLOR = '#0ea5e9'

interface InputPoint {
  start: number
  keys: number
  mouse: number
}

/** Sum the per-span keyboard/mouse counts into 10-minute slots (a span crossing slots is shared by overlap).
 *  Returns null when no span carries counts (input metrics off, or no activity). Display only. */
function bucketInput(segments: ActivitySegment[]): { points: InputPoint[]; keys: number; mouse: number } | null {
  const counted = segments.filter((s) => s.key_events != null || s.mouse_events != null)
  if (!counted.length) return null
  const slots = new Map<number, InputPoint>()
  let first = Infinity
  let last = -Infinity
  for (const s of counted) {
    const a = Date.parse(s.started_at)
    const b = Math.max(a + 1, Date.parse(s.ended_at))
    first = Math.min(first, a)
    last = Math.max(last, b)
    for (let slot = Math.floor(a / BUCKET_MS) * BUCKET_MS; slot < b; slot += BUCKET_MS) {
      const share = (Math.min(b, slot + BUCKET_MS) - Math.max(a, slot)) / (b - a)
      const p = slots.get(slot) ?? { start: slot, keys: 0, mouse: 0 }
      p.keys += (s.key_events ?? 0) * share
      p.mouse += (s.mouse_events ?? 0) * share
      slots.set(slot, p)
    }
  }
  const points: InputPoint[] = []
  for (let slot = Math.floor(first / BUCKET_MS) * BUCKET_MS; slot < last; slot += BUCKET_MS) {
    const p = slots.get(slot)
    points.push({ start: slot, keys: Math.round(p?.keys ?? 0), mouse: Math.round(p?.mouse ?? 0) })
  }
  const keys = counted.reduce((n, s) => n + (s.key_events ?? 0), 0)
  const mouse = counted.reduce((n, s) => n + (s.mouse_events ?? 0), 0)
  return { points, keys, mouse }
}

function InputGraph({ data }: { data: InputPoint[] }) {
  const reduced = usePrefersReducedMotion()
  return (
    <figure className="h-72">
      <figcaption className="sr-only">Keyboard and mouse strokes per 10 minutes over the day</figcaption>
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ top: 8, right: 16, bottom: 0, left: 0 }}>
          <defs>
            <linearGradient id="input-keys" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="var(--cat-productive)" stopOpacity={0.3} />
              <stop offset="100%" stopColor="var(--cat-productive)" stopOpacity={0} />
            </linearGradient>
            <linearGradient id="input-mouse" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={MOUSE_COLOR} stopOpacity={0.25} />
              <stop offset="100%" stopColor={MOUSE_COLOR} stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid vertical={false} stroke="var(--chart-grid)" />
          <XAxis
            dataKey="start"
            tickFormatter={(t: number) => formatTime(t)}
            tickLine={false}
            axisLine={false}
            minTickGap={40}
            tick={{ fill: 'var(--muted-foreground)', fontSize: 11 }}
          />
          <YAxis allowDecimals={false} tickLine={false} axisLine={false} width={44} tick={{ fill: 'var(--muted-foreground)', fontSize: 11 }} />
          <Tooltip
            cursor={{ stroke: 'var(--muted-foreground)', strokeOpacity: 0.4 }}
            formatter={(v, name) => [`${(v as number).toLocaleString()} strokes`, name]}
            labelFormatter={(t) => `${formatTime(t as number)} – ${formatTime((t as number) + BUCKET_MS)}`}
            contentStyle={{ fontSize: 12, borderRadius: 8 }}
          />
          <Legend verticalAlign="top" align="left" iconType="circle" iconSize={8} wrapperStyle={{ fontSize: 12, paddingBottom: 8 }} />
          <Area
            name="Keyboard strokes"
            type="monotone"
            dataKey="keys"
            stroke="var(--cat-productive)"
            strokeWidth={2}
            fill="url(#input-keys)"
            dot={false}
            isAnimationActive={!reduced}
            animationDuration={500}
          />
          <Area
            name="Mouse strokes"
            type="monotone"
            dataKey="mouse"
            stroke={MOUSE_COLOR}
            strokeWidth={2}
            fill="url(#input-mouse)"
            dot={false}
            isAnimationActive={!reduced}
            animationDuration={500}
          />
        </AreaChart>
      </ResponsiveContainer>
    </figure>
  )
}
