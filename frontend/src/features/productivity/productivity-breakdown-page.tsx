import { useMemo, useState } from 'react'
import { BarChart3, Download, Gauge, List, UserRound, Users } from 'lucide-react'
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'

import { PageHeader } from '@/components/common/page-header'
import { PersonAvatar } from '@/components/common/person'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/misc'
import { SegmentedControl } from '@/components/ui/segmented-control'
import { formatClock } from '@/features/dashboard/components/org/shared'
import { ChartTooltipBox, WidgetError } from '@/features/dashboard/components/widget'
import { formatDay } from '@/features/activity/format'
import { ActivityDetailsDialog } from '@/features/productivity/components/activity-details-dialog'
import { useEmployeeProductivity, useTeamProductivity } from '@/features/productivity/api'
import { CATEGORY, RANGES, rangeFor, share, type RangeKey } from '@/features/productivity/meta'
import { EmployeePicker } from '@/features/people/components/employee-picker'
import { useDocumentTitle } from '@/hooks/use-document-title'
import { useAuthStore } from '@/stores/auth-store'
import type { ProductivityMetrics } from '@/types/api'

type View = 'team' | 'individual'
type Display = 'graph' | 'list'

interface Row {
  id: string
  employeeId: string
  name: string
  subtitle: string
  day?: string
  metrics: ProductivityMetrics
}

const SERIES = [
  { key: 'productive', color: CATEGORY.productive.color, metric: 'productive_seconds' as const },
  { key: 'unproductive', color: CATEGORY.unproductive.color, metric: 'unproductive_seconds' as const },
  { key: 'neutral', color: CATEGORY.neutral.color, metric: 'neutral_seconds' as const },
  { key: 'idle', color: 'var(--muted-foreground)', metric: 'idle_seconds' as const },
]

/** The three classified shares (of tracked time), like the reference's 68% / 13% / 13%. */
function shares(m: ProductivityMetrics) {
  return {
    productive: share(m.productive_seconds, m.tracked_seconds),
    neutral: share(m.neutral_seconds, m.tracked_seconds),
    unproductive: share(m.unproductive_seconds, m.tracked_seconds),
  }
}

function ProductivityBar({ metrics }: { metrics: ProductivityMetrics }) {
  const total = metrics.tracked_seconds || 1
  const s = shares(metrics)
  const seg = (sec: number, color: string) => <span className="h-full first:rounded-l-full last:rounded-r-full" style={{ width: `${(100 * sec) / total}%`, background: color }} aria-hidden />
  return (
    <div className="flex items-center gap-3">
      <div className="flex h-2.5 w-36 gap-[2px] overflow-hidden rounded-full bg-muted">
        {seg(metrics.productive_seconds, CATEGORY.productive.color)}
        {seg(metrics.neutral_seconds, CATEGORY.neutral.color)}
        {seg(metrics.unproductive_seconds, CATEGORY.unproductive.color)}
      </div>
      <span className="text-[12px] tabular whitespace-nowrap">
        <span className="font-medium text-cat-productive">{s.productive}%</span>{' '}
        <span className="text-cat-neutral">{s.neutral}%</span>{' '}
        <span className="text-cat-unproductive">{s.unproductive}%</span>
      </span>
    </div>
  )
}

function GraphTooltip({ active, payload, label }: { active?: boolean; payload?: { payload?: Row }[]; label?: string }) {
  const row = payload?.[0]?.payload
  if (!active || !row) return null
  return (
    <ChartTooltipBox
      title={label ?? row.name}
      rows={SERIES.map((ser) => ({ label: ser.key[0].toUpperCase() + ser.key.slice(1), value: formatClock(row.metrics[ser.metric]), color: ser.color }))}
    />
  )
}

export default function ProductivityBreakdownPage() {
  useDocumentTitle('Productivity Breakdown')
  const company = useAuthStore((s) => s.company)
  const timeZone = company?.timezone ?? 'UTC'
  const [view, setView] = useState<View>('individual')
  const [display, setDisplay] = useState<Display>('list')
  const [rangeKey, setRangeKey] = useState<RangeKey>('7d')
  const [employeeId, setEmployeeId] = useState<string | null>(null)
  const [details, setDetails] = useState<{ employeeId: string; name: string; day: string } | null>(null)
  const range = rangeFor(rangeKey, timeZone)

  const team = useTeamProductivity(range, view === 'team')
  const individual = useEmployeeProductivity(employeeId ?? '', range, view === 'individual' && Boolean(employeeId))
  const active = view === 'team' ? team : individual

  const rows: Row[] = useMemo(() => {
    if (view === 'team') {
      return (team.data?.rows ?? [])
        .map((r) => ({ id: r.employee.id, employeeId: r.employee.id, name: r.employee.full_name, subtitle: r.work_profile?.name ?? r.team?.name ?? r.employee.job_title ?? '—', metrics: r.metrics }))
        .sort((a, b) => b.metrics.productive_seconds - a.metrics.productive_seconds)
    }
    const name = individual.data?.employee.full_name ?? ''
    return (individual.data?.days ?? [])
      .filter((d) => !d.holiday)
      .map((d) => ({ id: d.day, employeeId: employeeId ?? '', name, subtitle: formatDay(d.day, 'short'), day: d.day, metrics: d.metrics }))
      .reverse()
  }, [view, team.data, individual.data, employeeId])

  const exportCsv = () => {
    const header = ['Name', 'Date/Scope', 'Productive', 'Productive%', 'Neutral%', 'Unproductive%', 'Idle', 'Active']
    const lines = rows.map((r) => {
      const s = shares(r.metrics)
      return [r.name, r.subtitle, formatClock(r.metrics.productive_seconds), s.productive, s.neutral, s.unproductive, formatClock(r.metrics.idle_seconds), formatClock(r.metrics.active_seconds)].join(',')
    })
    const blob = new Blob([[header.join(','), ...lines].join('\n')], { type: 'text/csv' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `productivity-breakdown-${range.start}_${range.end}.csv`
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="space-y-5">
      <PageHeader
        title="Productivity Breakdown"
        description="Active working hours compared to idle time, to measure efficiency and productivity."
        icon={Gauge}
      />

      <div className="flex flex-wrap items-center gap-3">
        <SegmentedControl<View>
          label="View"
          value={view}
          onChange={setView}
          options={[
            { value: 'individual', label: 'Individual View', icon: UserRound },
            { value: 'team', label: 'Team View', icon: Users },
          ]}
        />
        <div className="sm:ml-auto flex flex-wrap items-center gap-3">
          <SegmentedControl<RangeKey> label="Range" value={rangeKey} onChange={setRangeKey} options={RANGES} />
          <Button variant="outline" size="sm" onClick={exportCsv} disabled={!rows.length}>
            <Download /> Export
          </Button>
        </div>
      </div>

      <Card className="p-5">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <SegmentedControl<Display>
            size="sm"
            label="Display"
            value={display}
            onChange={setDisplay}
            options={[
              { value: 'graph', label: 'View by graph', icon: BarChart3 },
              { value: 'list', label: 'View by list', icon: List },
            ]}
          />
          {view === 'individual' && (
            <div className="w-60">
              <EmployeePicker value={employeeId} onChange={setEmployeeId} placeholder="Select a member" />
            </div>
          )}
        </div>

        {view === 'individual' && !employeeId ? (
          <div className="flex flex-col items-center gap-2 p-10 text-center">
            <UserRound className="size-7 text-muted-foreground" aria-hidden />
            <p className="font-semibold">Select a member</p>
            <p className="max-w-sm text-[13px] text-muted-foreground">Choose a person to see their day-by-day productivity breakdown.</p>
          </div>
        ) : active.isError ? (
          <WidgetError error={active.error} onRetry={() => void active.refetch()} />
        ) : active.isPending ? (
          <Skeleton className="h-72" />
        ) : !rows.length ? (
          <div className="p-10 text-center text-[13px] text-muted-foreground">No productivity data in this range.</div>
        ) : display === 'graph' ? (
          <figure className="h-80">
            <figcaption className="sr-only">Productivity breakdown by {view === 'team' ? 'member' : 'day'}</figcaption>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={rows} margin={{ top: 12, right: 16, bottom: 0, left: 0 }}>
                <CartesianGrid vertical={false} stroke="var(--chart-grid)" />
                <XAxis dataKey={view === 'team' ? 'name' : 'subtitle'} tickLine={false} axisLine={false} tickMargin={8} tick={{ fill: 'var(--muted-foreground)', fontSize: 11 }} minTickGap={8} />
                <YAxis tickFormatter={(v: number) => `${Math.round(v / 3600)}`} tickLine={false} axisLine={false} width={32} tick={{ fill: 'var(--muted-foreground)', fontSize: 11 }} label={{ value: 'Hours', angle: -90, position: 'insideLeft', fill: 'var(--muted-foreground)', fontSize: 11 }} />
                <Tooltip cursor={{ fill: 'var(--muted-foreground)', fillOpacity: 0.08 }} content={<GraphTooltip />} />
                {SERIES.map((ser) => (
                  <Bar key={ser.key} dataKey={(r: Row) => r.metrics[ser.metric]} name={ser.key} stackId="a" fill={ser.color} maxBarSize={48} radius={ser.key === 'idle' ? [3, 3, 0, 0] : undefined} />
                ))}
              </BarChart>
            </ResponsiveContainer>
          </figure>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full border-collapse text-[13px]">
              <thead>
                <tr className="border-b text-left text-[11px] font-medium tracking-wide text-muted-foreground uppercase">
                  <th className="py-2.5 font-medium">Name</th>
                  <th className="py-2.5 font-medium">Productive</th>
                  <th className="py-2.5 font-medium">Productivity %</th>
                  <th className="py-2.5 text-right font-medium">Action</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.id} className="border-b last:border-0 hover:bg-muted/40">
                    <td className="py-3">
                      <span className="flex items-center gap-3">
                        <PersonAvatar name={r.name} seed={r.employeeId} className="size-8" aria-hidden />
                        <span className="min-w-0">
                          <span className="block truncate font-medium">{r.name}</span>
                          <span className="block truncate text-[12px] text-muted-foreground">{r.subtitle}</span>
                        </span>
                      </span>
                    </td>
                    <td className="py-3 font-semibold tabular text-cat-productive">{formatClock(r.metrics.productive_seconds)}</td>
                    <td className="py-3"><ProductivityBar metrics={r.metrics} /></td>
                    <td className="py-3 text-right">
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => {
                          if (r.day) setDetails({ employeeId: r.employeeId, name: r.name, day: r.day })
                          else {
                            setEmployeeId(r.employeeId)
                            setView('individual')
                          }
                        }}
                      >
                        Details
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {details && (
        <ActivityDetailsDialog
          employeeId={details.employeeId}
          employeeName={details.name}
          day={details.day}
          open
          onOpenChange={(o) => !o && setDetails(null)}
        />
      )}
    </div>
  )
}
