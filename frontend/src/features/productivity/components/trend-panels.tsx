import { useState } from 'react'
import { MousePointerClick } from 'lucide-react'
import { Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'

import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { formatDay, formatSeconds } from '@/features/activity/format'
import { ChartTooltipBox, ViewToggle, type ViewMode } from '@/features/dashboard/components/widget'
import { SCORE_HINT, SCORE_ORDER } from '@/features/productivity/meta'
import type { ProductivityTrend, ProductivityTrendPoint, ScoreKey } from '@/types/api'

const LABEL: Record<ScoreKey, string> = {
  activity_score: 'Activity score',
  productive_share: 'Productive share',
  focus_score: 'Focus score',
  work_utilization: 'Work utilization',
}

const SERIES = 'var(--chart-1)'
const AXIS_TICK = { fill: 'var(--muted-foreground)', fontSize: 11 }

function bucketLabel(p: ProductivityTrendPoint, period: ProductivityTrend['period'], style: 'short' | 'long' = 'short'): string {
  if (period === 'monthly') return new Date(`${p.start}T00:00:00Z`).toLocaleDateString(undefined, { timeZone: 'UTC', month: style === 'long' ? 'long' : 'short', year: style === 'long' ? 'numeric' : undefined })
  if (period === 'weekly') return style === 'long' ? `Week of ${formatDay(p.start, 'short')}` : formatDay(p.start, 'short').replace(/^\w+,?\s*/, '')
  return formatDay(p.start, style)
}

/** Recharts reports the hovered/clicked column as a number or a numeric string. */
function indexOf(state: unknown): number | null {
  const raw = (state as { activeTooltipIndex?: number | string } | null)?.activeTooltipIndex
  const index = raw === undefined || raw === null ? NaN : Number(raw)
  return Number.isInteger(index) && index >= 0 ? index : null
}

function PointTooltip({ active, payload, period, score }: { active?: boolean; payload?: { payload?: ProductivityTrendPoint }[]; period: ProductivityTrend['period']; score?: ScoreKey }) {
  const p = payload?.[0]?.payload
  if (!active || !p) return null
  const rows = score
    ? [
        { label: LABEL[score], value: p[score] === null ? 'Not enough data' : `${p[score]}%` },
        { label: 'Work time', value: formatSeconds(p.work_seconds) },
        { label: 'People with work', value: String(p.people) },
      ]
    : [
        { label: 'Work time', value: formatSeconds(p.work_seconds) },
        { label: 'Active', value: formatSeconds(p.active_seconds) },
        { label: 'Productive apps & sites', value: formatSeconds(p.productive_seconds) },
        { label: 'Logged on tasks', value: formatSeconds(p.task_seconds) },
        { label: 'People with work', value: String(p.people) },
      ]
  return <ChartTooltipBox title={bucketLabel(p, period, 'long')} rows={[...rows, { label: 'Click', value: 'see the data' }]} />
}

function ScorePanel({ trend, score, onSelect }: { trend: ProductivityTrend; score: ScoreKey; onSelect: (p: ProductivityTrendPoint) => void }) {
  const unavailable = score === 'focus_score' && !trend.focus_available
  const latest = [...trend.points].reverse().find((p) => p[score] !== null)
  return (
    <Card className="p-4">
      <div className="flex items-baseline justify-between gap-3">
        <h3 className="text-[13px] font-semibold">{LABEL[score]}</h3>
        <span className="text-[12px] text-muted-foreground tabular">
          {unavailable ? '' : latest ? `latest ${latest[score]}% · ${bucketLabel(latest, trend.period)}` : 'no data yet'}
        </span>
      </div>
      <p className="text-[11px] text-muted-foreground">{SCORE_HINT[score]}</p>
      {unavailable ? (
        <p className="flex h-36 items-center justify-center px-6 text-center text-[12px] text-muted-foreground">
          Focus sessions are analysed for daily and weekly trends; switch the period to see this score.
        </p>
      ) : (
        <figure className="mt-2 h-36">
          <figcaption className="sr-only">{`${LABEL[score]} per ${trend.period === 'daily' ? 'day' : trend.period === 'weekly' ? 'week' : 'month'}. The table view lists every value.`}</figcaption>
          <ResponsiveContainer width="100%" height="100%">
            <LineChart
              data={trend.points}
              margin={{ top: 6, right: 24, bottom: 0, left: 0 }}
              onClick={(state) => {
                const i = indexOf(state)
                if (i !== null && trend.points[i]) onSelect(trend.points[i])
              }}
              style={{ cursor: 'pointer' }}
            >
              <CartesianGrid vertical={false} stroke="var(--chart-grid)" />
              <XAxis dataKey="start" tickFormatter={(_, i) => (trend.points[i] ? bucketLabel(trend.points[i], trend.period) : '')} tickLine={false} axisLine={false} minTickGap={20} tick={AXIS_TICK} />
              <YAxis domain={[0, 100]} ticks={[0, 50, 100]} tickFormatter={(v: number) => `${v}%`} tickLine={false} axisLine={false} width={40} tick={AXIS_TICK} />
              <Tooltip cursor={{ stroke: 'var(--border)' }} content={<PointTooltip period={trend.period} score={score} />} />
              <Line
                type="monotone"
                dataKey={score}
                stroke={SERIES}
                strokeWidth={2}
                dot={{ r: 4, fill: SERIES, stroke: 'var(--card)', strokeWidth: 2 }}
                activeDot={{ r: 6, stroke: 'var(--card)', strokeWidth: 2 }}
                connectNulls={false}
                isAnimationActive={false}
              />
            </LineChart>
          </ResponsiveContainer>
        </figure>
      )}
    </Card>
  )
}

function WorkTimePanel({ trend, onSelect }: { trend: ProductivityTrend; onSelect: (p: ProductivityTrendPoint) => void }) {
  const rows = trend.points.map((p) => ({ ...p, hours: p.work_seconds / 3600 }))
  return (
    <Card className="p-4">
      <h3 className="text-[13px] font-semibold">Work time</h3>
      <p className="text-[11px] text-muted-foreground">Hours inside work sessions, all people in the selection combined.</p>
      <figure className="mt-2 h-44">
        <figcaption className="sr-only">Work hours per period. The table view lists every value.</figcaption>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart
            data={rows}
            margin={{ top: 6, right: 24, bottom: 0, left: 0 }}
            barCategoryGap="28%"
            onClick={(state) => {
              const i = indexOf(state)
              if (i !== null && trend.points[i]) onSelect(trend.points[i])
            }}
            style={{ cursor: 'pointer' }}
          >
            <CartesianGrid vertical={false} stroke="var(--chart-grid)" />
            <XAxis dataKey="start" tickFormatter={(_, i) => (trend.points[i] ? bucketLabel(trend.points[i], trend.period) : '')} tickLine={false} axisLine={false} minTickGap={20} tick={AXIS_TICK} />
            <YAxis tickFormatter={(v: number) => `${v}h`} tickLine={false} axisLine={false} width={40} allowDecimals={false} tick={AXIS_TICK} />
            <Tooltip cursor={{ fill: 'var(--muted)', opacity: 0.5 }} content={<PointTooltip period={trend.period} />} />
            <Bar dataKey="hours" fill={SERIES} radius={[4, 4, 0, 0]} isAnimationActive={false} />
          </BarChart>
        </ResponsiveContainer>
      </figure>
    </Card>
  )
}

/**
 * Trends as small multiples: one panel per score on the same 0–100% scale (so no colour has to tell series
 * apart), plus work time on its own axis. Clicking any point or bar — or "View data" in the table — opens the
 * measurements behind it.
 */
export function TrendPanels({ trend, onSelect }: { trend: ProductivityTrend; onSelect: (p: ProductivityTrendPoint) => void }) {
  const [view, setView] = useState<ViewMode>('chart')
  const pct = (v: number | null) => (v === null ? '—' : `${v}%`)
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="flex items-center gap-1.5 text-[12px] text-muted-foreground">
          <MousePointerClick className="size-3.5" aria-hidden /> Click a point or bar to see the data behind it.
        </p>
        <ViewToggle value={view} onChange={setView} />
      </div>
      {view === 'chart' ? (
        <>
          <div className="grid gap-4 md:grid-cols-2">
            {SCORE_ORDER.map((score) => (
              <ScorePanel key={score} trend={trend} score={score} onSelect={onSelect} />
            ))}
          </div>
          <WorkTimePanel trend={trend} onSelect={onSelect} />
        </>
      ) : (
        <Card className="overflow-hidden py-0">
          <div className="relative overflow-x-auto">
            <Table>
              <caption className="sr-only">Trend values per period</caption>
              <TableHeader>
                <TableRow className="hover:bg-transparent">
                  <TableHead className="pl-4">Period</TableHead>
                  <TableHead className="text-right">Work</TableHead>
                  {SCORE_ORDER.map((s) => (
                    <TableHead key={s} className="text-right">
                      {LABEL[s]}
                    </TableHead>
                  ))}
                  <TableHead className="text-right">People</TableHead>
                  <TableHead className="pr-4" />
                </TableRow>
              </TableHeader>
              <TableBody>
                {[...trend.points].reverse().map((p) => (
                  <TableRow key={p.start}>
                    <TableCell className="pl-4 whitespace-nowrap">{bucketLabel(p, trend.period, 'long')}</TableCell>
                    <TableCell className="text-right tabular whitespace-nowrap">{formatSeconds(p.work_seconds)}</TableCell>
                    {SCORE_ORDER.map((s) => (
                      <TableCell key={s} className="text-right tabular">
                        {pct(p[s])}
                      </TableCell>
                    ))}
                    <TableCell className="text-right tabular whitespace-nowrap">{p.people}</TableCell>
                    <TableCell className="pr-4 text-right">
                      <Button size="sm" variant="ghost" onClick={() => onSelect(p)}>
                        View data
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </Card>
      )}
    </div>
  )
}
