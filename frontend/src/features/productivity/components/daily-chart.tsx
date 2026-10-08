import { useState } from 'react'
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'

import { Button } from '@/components/ui/button'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { formatDay, formatSeconds } from '@/features/activity/format'
import { ChartTooltipBox, ViewToggle, type ViewMode } from '@/features/dashboard/components/widget'
import { CATEGORY, CATEGORY_ORDER } from '@/features/productivity/meta'
import { cn } from '@/lib/utils'
import type { DayProductivity } from '@/types/api'

const HATCH_ID = 'unclassified-hatch'

interface Row {
  day: string
  productive: number
  neutral: number
  unproductive: number
  unclassified: number
  item: DayProductivity
}

function DayTooltip({ active, payload }: { active?: boolean; payload?: { payload?: Row }[] }) {
  const row = payload?.[0]?.payload
  if (!active || !row) return null
  const m = row.item.metrics
  return (
    <ChartTooltipBox
      title={formatDay(row.day)}
      rows={[
        ...CATEGORY_ORDER.map((key) => ({ label: CATEGORY[key].label, value: formatSeconds(m[CATEGORY[key].metric] as number), color: CATEGORY[key].color })),
        { label: 'Work time', value: formatSeconds(m.work_seconds) },
        { label: 'Extended idle', value: formatSeconds(m.extended_idle_seconds) },
        { label: 'Activity score', value: row.item.activity_score === null ? '—' : `${row.item.activity_score}%` },
        { label: 'Focus score', value: row.item.focus_score === null ? '—' : `${row.item.focus_score}%` },
      ]}
    />
  )
}

/** Tracked hours per day, stacked by category. One axis (hours); every day also in the table view. */
export function DailyCategoryChart({ days, onSelectDay }: { days: DayProductivity[]; onSelectDay?: (day: string) => void }) {
  const [view, setView] = useState<ViewMode>('chart')
  const rows: Row[] = days.map((d) => ({
    day: d.day,
    productive: d.metrics.productive_seconds / 3600,
    neutral: d.metrics.neutral_seconds / 3600,
    unproductive: d.metrics.unproductive_seconds / 3600,
    unclassified: d.metrics.unclassified_seconds / 3600,
    item: d,
  }))

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <ul className="flex flex-wrap gap-x-4 gap-y-1 text-[12px] text-muted-foreground">
          {CATEGORY_ORDER.map((key) => (
            <li key={key} className="inline-flex items-center gap-1.5">
              <span className={cn('size-2.5 rounded-sm', CATEGORY[key].swatch)} aria-hidden />
              {CATEGORY[key].label}
            </li>
          ))}
        </ul>
        <ViewToggle value={view} onChange={setView} />
      </div>
      {view === 'chart' ? (
        <figure className="h-64">
          <figcaption className="sr-only">Tracked hours per day by category. Switch to the table view for exact values.</figcaption>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart
              data={rows}
              margin={{ top: 8, right: 24, bottom: 0, left: 0 }}
              barCategoryGap="28%"
              onClick={(state) => {
                const raw = (state as { activeTooltipIndex?: number | string } | null)?.activeTooltipIndex
                const i = raw === undefined || raw === null ? NaN : Number(raw)
                if (onSelectDay && Number.isInteger(i) && rows[i]) onSelectDay(rows[i].day)
              }}
              style={onSelectDay ? { cursor: 'pointer' } : undefined}
            >
              <defs>
                <pattern id={HATCH_ID} width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(135)">
                  <rect width="6" height="6" fill="var(--cat-unclassified)" fillOpacity="0.18" />
                  <rect width="2" height="6" fill="var(--cat-unclassified)" />
                </pattern>
              </defs>
              <CartesianGrid vertical={false} stroke="var(--chart-grid)" />
              <XAxis
                dataKey="day"
                tickFormatter={(d: string) => formatDay(d, 'short')}
                tickLine={false}
                axisLine={false}
                minTickGap={16}
                tick={{ fill: 'var(--muted-foreground)', fontSize: 11 }}
              />
              <YAxis
                tickFormatter={(v: number) => `${v}h`}
                tickLine={false}
                axisLine={false}
                width={36}
                allowDecimals={false}
                tick={{ fill: 'var(--muted-foreground)', fontSize: 11 }}
              />
              <Tooltip cursor={{ fill: 'var(--muted)', opacity: 0.5 }} content={<DayTooltip />} />
              {CATEGORY_ORDER.map((key, i) => (
                <Bar
                  key={key}
                  dataKey={key}
                  stackId="time"
                  fill={key === 'unclassified' ? `url(#${HATCH_ID})` : CATEGORY[key].color}
                  stroke="var(--card)"
                  strokeWidth={2}
                  radius={i === CATEGORY_ORDER.length - 1 ? [4, 4, 0, 0] : 0}
                  isAnimationActive={false}
                />
              ))}
            </BarChart>
          </ResponsiveContainer>
        </figure>
      ) : (
        <div className="max-h-80 overflow-y-auto rounded-md border">
          <Table>
            <caption className="sr-only">Time per day by category</caption>
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                <TableHead className="pl-4">Day</TableHead>
                <TableHead className="text-right">Work</TableHead>
                {CATEGORY_ORDER.map((key) => (
                  <TableHead key={key} className="text-right">
                    {CATEGORY[key].label}
                  </TableHead>
                ))}
                <TableHead className={cn('text-right', !onSelectDay && 'pr-4')}>Activity score</TableHead>
                {onSelectDay && <TableHead className="pr-4" />}
              </TableRow>
            </TableHeader>
            <TableBody>
              {[...days].reverse().map((d) => (
                <TableRow key={d.day}>
                  <TableCell className="pl-4 whitespace-nowrap">{formatDay(d.day, 'short')}</TableCell>
                  <TableCell className="text-right tabular whitespace-nowrap">{formatSeconds(d.metrics.work_seconds)}</TableCell>
                  {CATEGORY_ORDER.map((key) => (
                    <TableCell key={key} className="text-right tabular">
                      {formatSeconds(d.metrics[CATEGORY[key].metric] as number)}
                    </TableCell>
                  ))}
                  <TableCell className={cn('text-right tabular', !onSelectDay && 'pr-4')}>{d.activity_score === null ? '—' : `${d.activity_score}%`}</TableCell>
                  {onSelectDay && (
                    <TableCell className="pr-4 text-right">
                      <Button size="sm" variant="ghost" onClick={() => onSelectDay(d.day)}>
                        View data
                      </Button>
                    </TableCell>
                  )}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </div>
  )
}
