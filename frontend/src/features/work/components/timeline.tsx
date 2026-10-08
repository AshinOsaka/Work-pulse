import { useEffect, useMemo, useRef, useState } from 'react'
import { CalendarRange, Flag } from 'lucide-react'

import { EmptyState } from '@/components/common/empty-state'
import { Button } from '@/components/ui/button'
import { SegmentedControl } from '@/components/ui/segmented-control'
import { Assignees } from '@/features/work/components/task-card'
import { formatDue, STATUS, STATUSES } from '@/features/work/meta'
import { cn } from '@/lib/utils'
import type { Milestone, Task, TaskStatus } from '@/types/api'

type Zoom = 'weeks' | 'months'
const DAY_WIDTH: Record<Zoom, number> = { weeks: 34, months: 11 }
const DAY_MS = 86_400_000
const LABEL_WIDTH = 'w-[200px] sm:w-[260px]'

/** Bar fill per status. Status is also written next to every bar's task, so colour is never the only cue. */
const BAR: Record<TaskStatus, string> = {
  TODO: 'bg-muted-foreground/20 border-muted-foreground/45',
  IN_PROGRESS: 'bg-info/25 border-info/70',
  BLOCKED: 'bg-destructive/20 border-destructive/70',
  IN_REVIEW: 'bg-warning/25 border-warning/70',
  COMPLETED: 'bg-success/25 border-success/70',
}

const dayNumber = (iso: string) => Math.floor(Date.parse(`${iso}T00:00:00Z`) / DAY_MS)
const dateOf = (day: number) => new Date(day * DAY_MS)
const localToday = () => {
  const d = new Date()
  return Math.floor(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()) / DAY_MS)
}
const label = (day: number, opts: Intl.DateTimeFormatOptions) => dateOf(day).toLocaleDateString(undefined, { timeZone: 'UTC', ...opts })

interface Span {
  task: Task
  start: number
  end: number
  /** Only one of start/due is set: drawn as a single-day marker. */
  point: boolean
}

function spanOf(task: Task): Span | null {
  const start = task.start_date ? dayNumber(task.start_date) : null
  const end = task.due_date ? dayNumber(task.due_date) : null
  if (start === null && end === null) return null
  return { task, start: start ?? end!, end: end ?? start!, point: start === null || end === null }
}

function Scale({ from, days, width, zoom, today, milestones }: { from: number; days: number; width: number; zoom: Zoom; today: number; milestones: Milestone[] }) {
  const months: { day: number; text: string }[] = []
  const ticks: { day: number; text: string; weekend?: boolean }[] = []
  for (let d = from; d < from + days; d++) {
    const date = dateOf(d)
    if (d === from || date.getUTCDate() === 1) months.push({ day: d, text: label(d, { month: 'long', year: 'numeric' }) })
    if (zoom === 'weeks') ticks.push({ day: d, text: String(date.getUTCDate()), weekend: date.getUTCDay() === 0 || date.getUTCDay() === 6 })
    else if (date.getUTCDay() === 1) ticks.push({ day: d, text: label(d, { day: 'numeric', month: 'short' }) })
  }
  return (
    <div className="relative h-12 border-b" style={{ width: days * width }} aria-hidden>
      {months.map((m) => (
        <span key={m.day} className="absolute top-1 pl-1.5 text-[11px] font-semibold whitespace-nowrap" style={{ left: (m.day - from) * width }}>
          {m.text}
        </span>
      ))}
      {ticks.map((t) => (
        <span
          key={t.day}
          className={cn('absolute bottom-1 text-center text-[10px] tabular', t.weekend ? 'text-muted-foreground italic' : 'text-muted-foreground', t.day === today && 'font-bold text-primary')}
          style={{ left: (t.day - from) * width, width: zoom === 'weeks' ? width : undefined }}
        >
          {t.text}
        </span>
      ))}
      {milestones.map((m) =>
        m.due_date ? (
          <Flag
            key={m.id}
            className={cn('absolute top-5 size-3 -translate-x-1/2', m.closed ? 'text-success' : m.overdue ? 'text-destructive' : 'text-primary')}
            style={{ left: (dayNumber(m.due_date) - from) * width + width / 2 }}
          />
        ) : null,
      )}
    </div>
  )
}

/** Gridlines, today and milestone dates, repeated per row so rows stay independent. */
function Guides({ from, width, today, milestones, zoom }: { from: number; width: number; today: number; milestones: Milestone[]; zoom: Zoom }) {
  // Week lines on Mondays: offset of the first Monday from the range start.
  const firstMonday = (8 - dateOf(from).getUTCDay()) % 7
  return (
    <>
      <span
        className="pointer-events-none absolute inset-0"
        style={{
          backgroundImage: `linear-gradient(to right, var(--border) 1px, transparent 1px)${zoom === 'weeks' ? `, linear-gradient(to right, color-mix(in oklab, var(--border) 45%, transparent) 1px, transparent 1px)` : ''}`,
          backgroundSize: `${width * 7}px 100%${zoom === 'weeks' ? `, ${width}px 100%` : ''}`,
          backgroundPosition: `${firstMonday * width}px 0${zoom === 'weeks' ? ', 0 0' : ''}`,
        }}
        aria-hidden
      />
      {milestones.map((m) =>
        m.due_date ? (
          <span
            key={m.id}
            className="pointer-events-none absolute inset-y-0 border-l border-dashed border-primary/40"
            style={{ left: (dayNumber(m.due_date) - from) * width + width / 2 }}
            aria-hidden
          />
        ) : null,
      )}
      <span className="pointer-events-none absolute inset-y-0 w-0.5 bg-primary/70" style={{ left: (today - from) * width + width / 2 - 1 }} aria-hidden />
    </>
  )
}

function Bar({ span, from, width, onOpen }: { span: Span; from: number; width: number; onOpen: (id: string) => void }) {
  const { task } = span
  const left = (span.start - from) * width
  const barWidth = (span.end - span.start + 1) * width
  const dates = span.point
    ? task.due_date
      ? `due ${formatDue(task.due_date)}`
      : `starts ${formatDue(task.start_date!)}`
    : `${formatDue(task.start_date!)} to ${formatDue(task.due_date!)}`
  const name = `${task.reference} ${task.title}, ${STATUS[task.status].label}, ${dates}${task.overdue ? ', overdue' : ''}`
  if (span.point) {
    return (
      <button
        type="button"
        onClick={() => onOpen(task.id)}
        aria-label={name}
        title={name}
        className="group absolute top-1/2 flex -translate-y-1/2 items-center gap-1.5 outline-none"
        style={{ left: left + width / 2 - 6 }}
      >
        <span
          className={cn(
            'size-3 shrink-0 rotate-45 rounded-[2px] border-2 group-focus-visible:ring-[3px] group-focus-visible:ring-ring/40',
            BAR[task.status],
            task.overdue && 'border-destructive',
          )}
        />
        <span className="max-w-48 truncate text-[11px] text-muted-foreground group-hover:text-foreground">{task.title}</span>
      </button>
    )
  }
  const inside = barWidth >= 96
  return (
    <>
      <button
        type="button"
        onClick={() => onOpen(task.id)}
        aria-label={name}
        title={name}
        className={cn(
          'absolute top-1/2 flex h-6 -translate-y-1/2 items-center overflow-hidden rounded-md border px-2 text-left text-[11px] font-medium outline-none hover:brightness-95 focus-visible:ring-[3px] focus-visible:ring-ring/40',
          BAR[task.status],
          task.overdue && 'ring-1 ring-destructive',
          task.status === 'COMPLETED' && 'text-muted-foreground line-through',
        )}
        style={{ left: left + 2, width: Math.max(barWidth - 4, 8) }}
      >
        {inside && <span className="truncate">{task.title}</span>}
      </button>
      {!inside && (
        <span className="pointer-events-none absolute top-1/2 max-w-48 -translate-y-1/2 truncate text-[11px] text-muted-foreground" style={{ left: left + barWidth + 4 }} aria-hidden>
          {task.title}
        </span>
      )}
    </>
  )
}

/**
 * Timeline (Gantt-style): each task is a bar from its start date to its due date, grouped by milestone, with
 * milestone dates and today marked. Tasks with only one date show as a single-day marker; undated tasks are
 * listed below. Read-only by design: dates are edited in the task panel, so a stray drag can't reschedule work.
 */
export function Timeline({ tasks, milestones, onOpen }: { tasks: Task[]; milestones: Milestone[]; onOpen: (id: string) => void }) {
  const [zoom, setZoom] = useState<Zoom>('weeks')
  const scroller = useRef<HTMLDivElement>(null)
  const width = DAY_WIDTH[zoom]
  const today = useMemo(() => localToday(), [])

  const spans = useMemo(() => tasks.map(spanOf).filter((s): s is Span => s !== null), [tasks])
  const undated = useMemo(() => tasks.filter((t) => !t.start_date && !t.due_date), [tasks])
  const dated = milestones.filter((m) => m.due_date)

  const [from, days] = useMemo(() => {
    const points = [today, ...spans.flatMap((s) => [s.start, s.end]), ...dated.map((m) => dayNumber(m.due_date!))]
    let lo = Math.min(...points) - 3
    lo -= (dateOf(lo).getUTCDay() + 6) % 7 // start on a Monday
    const hi = Math.max(...points) + 7
    return [lo, Math.max(hi - lo + 1, zoom === 'weeks' ? 42 : 120)]
  }, [spans, dated, today, zoom])

  const groups = useMemo(() => {
    const ordered = [...milestones].sort((a, b) => (a.due_date ?? '9999').localeCompare(b.due_date ?? '9999'))
    const out = ordered.map((m) => ({ milestone: m as Milestone | null, spans: spans.filter((s) => s.task.milestone_id === m.id) }))
    out.push({ milestone: null, spans: spans.filter((s) => !s.task.milestone_id || !milestones.some((m) => m.id === s.task.milestone_id)) })
    for (const g of out) g.spans.sort((a, b) => a.start - b.start || a.end - b.end)
    return out.filter((g) => g.spans.length > 0 || (g.milestone && g.milestone.due_date))
  }, [milestones, spans])

  // Open on today rather than the start of the range.
  useEffect(() => {
    const el = scroller.current
    if (el) el.scrollLeft = Math.max(0, (today - from) * width - el.clientWidth / 3)
  }, [today, from, width])

  const scrollToToday = () => {
    const el = scroller.current
    if (el) el.scrollTo({ left: Math.max(0, (today - from) * width - el.clientWidth / 3), behavior: 'smooth' })
  }

  if (spans.length === 0 && dated.length === 0) {
    return (
      <EmptyState
        icon={CalendarRange}
        title="Nothing scheduled yet"
        description="Give tasks a start and due date (in the task panel) and they appear here as bars. Milestone dates show as flags."
      />
    )
  }

  return (
    <div>
      <div className="flex flex-wrap items-center gap-3 border-b px-4 py-2.5">
        <SegmentedControl<Zoom>
          label="Zoom"
          size="sm"
          value={zoom}
          onChange={setZoom}
          options={[
            { value: 'weeks', label: 'Weeks' },
            { value: 'months', label: 'Months' },
          ]}
        />
        <Button size="sm" variant="outline" onClick={scrollToToday}>
          Today
        </Button>
        <ul className="ml-auto flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-muted-foreground" aria-label="Legend">
          {STATUSES.map((s) => (
            <li key={s} className="inline-flex items-center gap-1">
              <span className={cn('h-2.5 w-4 rounded-sm border', BAR[s])} aria-hidden />
              {STATUS[s].label}
            </li>
          ))}
          <li className="inline-flex items-center gap-1">
            <span className="size-2.5 rotate-45 rounded-[1px] border-2 border-muted-foreground/50" aria-hidden /> One date
          </li>
          <li className="inline-flex items-center gap-1">
            <Flag className="size-3 text-primary" aria-hidden /> Milestone
          </li>
        </ul>
      </div>

      <div ref={scroller} className="relative overflow-x-auto">
        <div style={{ width: `max-content` }}>
          <div className="flex">
            <div className={cn('sticky left-0 z-10 flex shrink-0 items-end border-r border-b bg-card px-4 pb-1.5 text-[11px] font-medium text-muted-foreground', LABEL_WIDTH)}>Task</div>
            <Scale from={from} days={days} width={width} zoom={zoom} today={today} milestones={dated} />
          </div>
          <ul aria-label="Timeline">
            {groups.map((g) => (
              <li key={g.milestone?.id ?? 'none'}>
                <div className="flex bg-muted/40">
                  <div className={cn('sticky left-0 z-10 flex shrink-0 items-center gap-2 border-r bg-muted px-4 py-1.5', LABEL_WIDTH)}>
                    {g.milestone ? (
                      <Flag className={cn('size-3.5 shrink-0', g.milestone.closed ? 'text-success' : g.milestone.overdue ? 'text-destructive' : 'text-primary')} aria-hidden />
                    ) : null}
                    <h3 className="min-w-0 flex-1 truncate text-[12px] font-semibold">{g.milestone?.name ?? 'No milestone'}</h3>
                    {g.milestone && (
                      <span className="shrink-0 text-[11px] text-muted-foreground tabular">
                        {g.milestone.due_date ? formatDue(g.milestone.due_date) : 'No date'} · {g.milestone.progress}%
                      </span>
                    )}
                  </div>
                  <div className="relative h-8" style={{ width: days * width }}>
                    <Guides from={from} width={width} today={today} milestones={dated} zoom={zoom} />
                  </div>
                </div>
                <ul>
                  {g.spans.map((span) => (
                    <li key={span.task.id} className="flex border-b border-border/60">
                      <button
                        type="button"
                        onClick={() => onOpen(span.task.id)}
                        className={cn('sticky left-0 z-10 flex shrink-0 items-center gap-2 border-r bg-card px-4 py-1.5 text-left hover:bg-muted/60', LABEL_WIDTH)}
                        tabIndex={-1}
                        aria-hidden
                      >
                        <span className="min-w-0 flex-1">
                          <span className="block truncate text-[12px] font-medium">{span.task.title}</span>
                          <span className="flex items-center gap-1.5 text-[10px] text-muted-foreground">
                            <span className="tabular">{span.task.reference}</span>
                            <span className={cn('size-1.5 rounded-full', STATUS[span.task.status].dot)} />
                            {STATUS[span.task.status].label}
                          </span>
                        </span>
                        <Assignees task={span.task} max={2} />
                      </button>
                      <div className="relative h-11" style={{ width: days * width }}>
                        <Guides from={from} width={width} today={today} milestones={dated} zoom={zoom} />
                        <Bar span={span} from={from} width={width} onOpen={onOpen} />
                      </div>
                    </li>
                  ))}
                </ul>
              </li>
            ))}
          </ul>
        </div>
      </div>

      {undated.length > 0 && (
        <div className="border-t px-4 py-3">
          <p className="mb-2 text-[12px] font-medium text-muted-foreground">Unscheduled · {undated.length}</p>
          <ul className="flex flex-wrap gap-1.5">
            {undated.map((t) => (
              <li key={t.id}>
                <button type="button" onClick={() => onOpen(t.id)} className="inline-flex items-center gap-1.5 rounded-md border bg-card px-2 py-1 text-[12px] hover:border-primary/40">
                  <span className={cn('size-1.5 rounded-full', STATUS[t.status].dot)} aria-hidden />
                  <span className="text-muted-foreground tabular">{t.reference}</span>
                  <span className="max-w-56 truncate">{t.title}</span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}
