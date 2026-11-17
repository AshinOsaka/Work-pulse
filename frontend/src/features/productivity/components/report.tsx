import type { ReactNode } from 'react'
import { CircleAlert, CircleCheck, Crosshair, Info, ListChecks, MousePointerClick, Sparkles, Target } from 'lucide-react'

import { StatTile } from '@/components/common/stat-tile'
import { Card, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { formatSeconds } from '@/features/activity/format'
import { CategoryBar } from '@/features/productivity/components/category-bar'
import { DailyCategoryChart } from '@/features/productivity/components/daily-chart'
import { ProjectSignals } from '@/features/productivity/components/project-signals'
import { ScoreCard } from '@/features/productivity/components/score-card'
import { SummaryStrip } from '@/features/productivity/components/summary-strip'
import { METRIC_LABEL } from '@/features/productivity/meta'
import { cn } from '@/lib/utils'
import type { EmployeeProductivity, ProductivityInsight, ProductivityMetrics, TeamProductivity } from '@/types/api'

const TIME_TILES: { key: keyof ProductivityMetrics; label: string; hint: string }[] = [
  {
    key: 'work_seconds',
    label: 'Work time',
    hint: 'Total time the desktop agent was running a work session — from the moment work starts on the computer until it stops (sign-out, shutdown or sleep). Work time = Active time + Idle time.',
  },
  {
    key: 'active_seconds',
    label: 'Active time',
    hint: 'Part of work time with keyboard or mouse use. Time counts as active until there has been no input for a few minutes. For customer-facing work profiles, quiet time with a productive app or website open (reading, calls) also counts as active.',
  },
  {
    key: 'idle_seconds',
    label: 'Idle time',
    hint: 'Part of work time with no keyboard or mouse input for a few minutes — for example reading, a phone call, or a short break while the computer stays on.',
  },
  {
    key: 'extended_idle_seconds',
    label: 'Extended idle',
    hint: 'The part of idle time that came in single stretches of 15 minutes or more without any input — usually breaks, lunch or meetings away from the desk. Short pauses are not counted here.',
  },
  {
    key: 'away_seconds',
    label: 'Away time',
    hint: 'Gaps inside a day when no work session was running — between the first start and the last stop of the day (agent signed out, computer off or asleep). Time before the first start or after the last stop is not counted.',
  },
]


const TONE = {
  positive: { icon: CircleCheck, className: 'text-success' },
  info: { icon: Info, className: 'text-info' },
  attention: { icon: CircleAlert, className: 'text-warning' },
} as const

export function InsightList({ insights }: { insights: ProductivityInsight[] }) {
  if (!insights.length) return <p className="text-[13px] text-muted-foreground">No observations for this period.</p>
  return (
    <ul className="divide-y">
      {insights.map((insight) => {
        const tone = TONE[insight.tone]
        return (
          <li key={insight.title} className="flex gap-3 py-3 first:pt-0 last:pb-0">
            <tone.icon className={cn('mt-0.5 size-4 shrink-0', tone.className)} aria-hidden />
            <div className="min-w-0">
              <p className="text-[13px] font-medium">{insight.title}</p>
              <p className="text-[12px] text-muted-foreground">{insight.detail}</p>
              <p className="mt-1 text-[11px] text-muted-foreground">
                Based on: {insight.metrics.map((m) => METRIC_LABEL[m] ?? m).join(', ')}
              </p>
            </div>
          </li>
        )
      })}
    </ul>
  )
}

/** The common body of the team and employee views. */
export function ProductivityReport({
  data,
  children,
  onSelectDay,
}: {
  data: TeamProductivity | EmployeeProductivity
  children?: ReactNode
  /** Open the data behind one day of the daily chart. */
  onSelectDay?: (day: string) => void
}) {
  const t = data.totals
  return (
    <div className="space-y-6">
      <SummaryStrip lines={data.summary} />

      <section aria-labelledby="time-heading" className="space-y-3">
        <h2 id="time-heading" className="text-[15px] font-semibold">
          Time
        </h2>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
          {TIME_TILES.map((tile) => (
            <StatTile key={tile.key} label={tile.label} value={formatSeconds(t[tile.key] as number)} hint={tile.hint} hintOnHover />
          ))}
          <StatTile
            label="Task completion"
            value={
              data.task_completion.value === null
                ? 'No tasks due'
                : `${data.task_completion.value}% · ${data.task_completion.completed ?? 0} done`
            }
            hint={
              data.task_completion.value === null
                ? data.task_completion.reason
                : `${data.task_completion.completed} completed, ${data.task_completion.due_open} due and still open. ${formatSeconds(t.task_seconds)} logged on tasks.`
            }
            muted={data.task_completion.value === null}
            hintOnHover
          />
        </div>
      </section>

      <div className="grid grid-cols-[minmax(0,1fr)] gap-6 xl:grid-cols-[minmax(0,1fr)_minmax(0,2fr)]">
        <section aria-labelledby="activity-heading" className="space-y-3">
          <h2 id="activity-heading" className="flex items-center gap-2 text-[15px] font-semibold">
            <MousePointerClick className="size-4 text-muted-foreground" aria-hidden /> Activity
          </h2>
          <ScoreCard score={data.scores.activity_score} />
        </section>

        <section aria-labelledby="insights-heading" className="space-y-3">
          <h2 id="insights-heading" className="flex items-center gap-2 text-[15px] font-semibold">
            <Sparkles className="size-4 text-muted-foreground" aria-hidden /> Productivity insights
          </h2>
          <div className="grid gap-4 lg:grid-cols-2">
            <ScoreCard score={data.scores.productive_share} />
            <div className="space-y-4">
              <Card className="p-5">
                <p className="text-[13px] font-medium text-muted-foreground">Tracked time by category</p>
                <p className="mt-1 text-xl font-semibold tabular">{formatSeconds(t.tracked_seconds)}</p>
                <CategoryBar metrics={t} className="mt-3" />
              </Card>
              <div className="grid grid-cols-2 gap-4">
                <StatTile
                  label="Focus sessions"
                  value={`${t.focus_sessions} · ${formatSeconds(t.focus_seconds)}`}
                  hint="Number of focus sessions · their total time. A focus session is at least 25 minutes of work in Productive apps or websites without a real break: no pause or non-productive activity longer than 2 minutes, and no Unproductive app or website for more than 1 minute. A longer interruption ends the session."
                  hintOnHover
                />
                <StatTile
                  label="App switches"
                  value={String(t.context_switches)}
                  hint="How many times the person moved from one application or website to a different one within 2 minutes (for example Chrome → Excel, or one website → another). A high number can mean frequent multitasking or interruptions; changes after a longer pause are not counted."
                  hintOnHover
                />
              </div>
            </div>
          </div>
        </section>
      </div>

      <section aria-labelledby="focus-heading" className="space-y-3">
        <h2 id="focus-heading" className="flex items-center gap-2 text-[15px] font-semibold">
          <Crosshair className="size-4 text-muted-foreground" aria-hidden /> Focus and task time
        </h2>
        <div className="grid gap-4 lg:grid-cols-2">
          <ScoreCard score={data.scores.focus_score} />
          <ScoreCard score={data.scores.work_utilization} />
        </div>
      </section>

      <ProjectSignals projects={data.projects} />

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Target className="size-4 text-muted-foreground" aria-hidden /> Observations
          </CardTitle>
          <CardDescription>Each one names the figures it is based on.</CardDescription>
        </CardHeader>
        <div className="px-5 pt-3 pb-5">
          <InsightList insights={data.insights} />
        </div>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <ListChecks className="size-4 text-muted-foreground" aria-hidden /> By day
          </CardTitle>
        </CardHeader>
        <div className="px-5 pt-3 pb-5">
          <DailyCategoryChart days={data.days} onSelectDay={onSelectDay} />
        </div>
      </Card>

      {children}
    </div>
  )
}
