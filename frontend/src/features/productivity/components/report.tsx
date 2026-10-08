import type { ReactNode } from 'react'
import { CircleAlert, CircleCheck, Crosshair, Info, ListChecks, MousePointerClick, ShieldQuestion, Sparkles, Target } from 'lucide-react'

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
  { key: 'work_seconds', label: 'Work time', hint: 'Time inside work sessions started on the desktop agent.' },
  { key: 'active_seconds', label: 'Active time', hint: 'Work time with recent keyboard or mouse input.' },
  { key: 'idle_seconds', label: 'Idle time', hint: 'Work time without input, e.g. calls, reading or a short break.' },
  { key: 'extended_idle_seconds', label: 'Extended idle', hint: 'Idle in uninterrupted stretches of 15+ minutes (breaks, meetings away from the desk).' },
  { key: 'away_seconds', label: 'Away time', hint: 'Gaps between work sessions within a day, such as lunch.' },
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
      <div className="flex gap-3 rounded-lg border border-info/30 bg-info-soft/40 px-4 py-3 text-[13px]">
        <ShieldQuestion className="mt-0.5 size-4 shrink-0 text-info" aria-hidden />
        <p>{data.disclaimer}</p>
      </div>

      <SummaryStrip lines={data.summary} />

      <section aria-labelledby="time-heading" className="space-y-3">
        <h2 id="time-heading" className="text-[15px] font-semibold">
          Time
        </h2>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
          {TIME_TILES.map((tile) => (
            <StatTile key={tile.key} label={tile.label} value={formatSeconds(t[tile.key] as number)} hint={tile.hint} />
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
          />
        </div>
      </section>

      <div className="grid grid-cols-[minmax(0,1fr)] gap-6 xl:grid-cols-[minmax(0,1fr)_minmax(0,2fr)]">
        <section aria-labelledby="activity-heading" className="space-y-3">
          <h2 id="activity-heading" className="flex items-center gap-2 text-[15px] font-semibold">
            <MousePointerClick className="size-4 text-muted-foreground" aria-hidden /> Activity
          </h2>
          <p className="text-[12px] text-muted-foreground">Input-based. Says nothing about the value of the work.</p>
          <ScoreCard score={data.scores.activity_score} />
        </section>

        <section aria-labelledby="insights-heading" className="space-y-3">
          <h2 id="insights-heading" className="flex items-center gap-2 text-[15px] font-semibold">
            <Sparkles className="size-4 text-muted-foreground" aria-hidden /> Productivity insights
          </h2>
          <p className="text-[12px] text-muted-foreground">
            Based on what applications and websites were used, under your workspace's rules — not on input.
          </p>
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
                  hint="25+ minutes of productive work without longer interruptions."
                />
                <StatTile
                  label="App switches"
                  value={String(t.context_switches)}
                  hint="Changes of application or website less than 2 minutes apart."
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
        <p className="text-[12px] text-muted-foreground">
          How productive time was spent in uninterrupted stretches, and how much of the work time was logged on tasks.
        </p>
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
          <CardDescription>
            Tracked hours per day by category · {data.timezone.replaceAll('_', ' ')}
            {onSelectDay && ' · click a day to see the data behind it'}
          </CardDescription>
        </CardHeader>
        <div className="px-5 pt-3 pb-5">
          <DailyCategoryChart days={data.days} onSelectDay={onSelectDay} />
        </div>
      </Card>

      {children}
    </div>
  )
}
