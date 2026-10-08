import { useState } from 'react'
import { Activity, Moon, PowerOff, Radio } from 'lucide-react'
import { Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'

import { Skeleton } from '@/components/ui/misc'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import {
  ChartTooltipBox,
  LegendItem,
  ViewToggle,
  WidgetCard,
  WidgetError,
  WidgetUnavailable,
  type ViewMode,
} from '@/features/dashboard/components/widget'
import type { PresencePoint, TeamActivity } from '@/features/dashboard/data/types'
import { usePrefersReducedMotion } from '@/hooks/use-now'
import { formatTime } from '@/lib/format'

const COLORS = {
  active: 'var(--presence-active)',
  idle: 'var(--presence-idle)',
  offline: 'var(--presence-offline)',
}

function PresenceTooltip({ active, payload }: { active?: boolean; payload?: { payload?: PresencePoint }[] }) {
  const point = payload?.[0]?.payload
  if (!active || !point) return null
  return (
    <ChartTooltipBox
      title={formatTime(point.time)}
      rows={[
        { label: 'Active', value: String(point.active), color: COLORS.active },
        { label: 'Idle', value: String(point.idle), color: COLORS.idle },
      ]}
    />
  )
}

function TeamTooltip({
  active,
  payload,
}: {
  active?: boolean
  payload?: { payload?: { teamName: string; active: number; idle: number; offline: number } }[]
}) {
  const row = payload?.[0]?.payload
  if (!active || !row) return null
  return (
    <ChartTooltipBox
      title={row.teamName}
      rows={[
        { label: 'Active', value: String(row.active), color: COLORS.active },
        { label: 'Idle', value: String(row.idle), color: COLORS.idle },
        { label: 'Offline', value: String(row.offline), color: COLORS.offline },
      ]}
    />
  )
}

function Charts({ data }: { data: TeamActivity }) {
  const reduced = usePrefersReducedMotion()
  const latest = data.timeline.at(-1)
  const teamHeight = Math.max(150, data.teams.length * 34 + 28)
  const totals = data.teams.reduce((acc, t) => ({ active: acc.active + t.active, idle: acc.idle + t.idle }), { active: 0, idle: 0 })
  const hasHistory = data.timeline.length > 1

  return (
    <div className="grid gap-6 px-5 pt-3 pb-5 lg:grid-cols-[minmax(0,1.25fr)_minmax(0,1fr)]">
      <div className="min-w-0">
        <div className="flex items-baseline gap-2">
          <p className="text-[26px] leading-none font-semibold tracking-tight">{latest?.active ?? totals.active}</p>
          <p className="text-[13px] text-muted-foreground">active now · {latest?.idle ?? totals.idle} idle</p>
        </div>
        <p className="mt-1 text-[12px] text-muted-foreground">
          {hasHistory ? 'Last 60 minutes, updated live' : 'Current presence by team. For activity over time, see Reports.'}
        </p>
        {hasHistory && (
        <figure className="mt-3 h-44">
          <figcaption className="sr-only">{`Presence over the last hour; currently ${latest?.active ?? 0} active and ${latest?.idle ?? 0} idle`}</figcaption>
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={data.timeline} margin={{ top: 8, right: 24, bottom: 0, left: -20 }}>
              <CartesianGrid vertical={false} stroke="var(--chart-grid)" />
              <XAxis
                dataKey="time"
                tickFormatter={formatTime}
                tickLine={false}
                axisLine={false}
                minTickGap={48}
                tick={{ fill: 'var(--muted-foreground)', fontSize: 11 }}
              />
              <YAxis allowDecimals={false} tickLine={false} axisLine={false} width={44} tick={{ fill: 'var(--muted-foreground)', fontSize: 11 }} />
              <Tooltip content={<PresenceTooltip />} cursor={{ stroke: 'var(--muted-foreground)', strokeOpacity: 0.4 }} />
              <Line type="monotone" dataKey="active" stroke={COLORS.active} strokeWidth={2} dot={false} activeDot={{ r: 4, stroke: 'var(--card)', strokeWidth: 2 }} isAnimationActive={!reduced} animationDuration={400} />
              <Line type="monotone" dataKey="idle" stroke={COLORS.idle} strokeWidth={2} dot={false} activeDot={{ r: 4, stroke: 'var(--card)', strokeWidth: 2 }} isAnimationActive={!reduced} animationDuration={400} />
            </LineChart>
          </ResponsiveContainer>
        </figure>
        )}
      </div>

      <div className="min-w-0">
        <p className="text-[13px] font-medium">By team</p>
        <p className="text-[12px] text-muted-foreground">Current presence per team</p>
        <figure className="mt-3" style={{ height: teamHeight }}>
          <figcaption className="sr-only">Current presence by team</figcaption>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={data.teams} layout="vertical" margin={{ top: 0, right: 8, bottom: 0, left: 0 }} barCategoryGap={10}>
              <XAxis type="number" hide allowDecimals={false} />
              <YAxis
                type="category"
                dataKey="teamName"
                width={118}
                tickLine={false}
                axisLine={false}
                tick={{ fill: 'var(--foreground)', fontSize: 12 }}
              />
              <Tooltip content={<TeamTooltip />} cursor={{ fill: 'var(--accent)' }} />
              {/* 2px surface-coloured stroke = the gap between stacked segments. */}
              <Bar dataKey="active" stackId="presence" fill={COLORS.active} stroke="var(--card)" strokeWidth={2} maxBarSize={20} isAnimationActive={!reduced} />
              <Bar dataKey="idle" stackId="presence" fill={COLORS.idle} stroke="var(--card)" strokeWidth={2} maxBarSize={20} isAnimationActive={!reduced} />
              <Bar dataKey="offline" stackId="presence" fill={COLORS.offline} stroke="var(--card)" strokeWidth={2} radius={[0, 4, 4, 0]} maxBarSize={20} isAnimationActive={!reduced} />
            </BarChart>
          </ResponsiveContainer>
        </figure>
      </div>
    </div>
  )
}

function TableView({ data }: { data: TeamActivity }) {
  return (
    <Table>
      <caption className="sr-only">Current presence by team</caption>
      <TableHeader>
        <TableRow className="hover:bg-transparent">
          <TableHead className="pl-5">Team</TableHead>
          <TableHead className="text-right">Active</TableHead>
          <TableHead className="text-right">Idle</TableHead>
          <TableHead className="text-right">Offline</TableHead>
          <TableHead className="pr-5 text-right">Total</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {data.teams.map((t) => (
          <TableRow key={t.teamId}>
            <TableCell className="pl-5 font-medium">{t.teamName}</TableCell>
            <TableCell className="text-right tabular whitespace-nowrap">{t.active}</TableCell>
            <TableCell className="text-right tabular whitespace-nowrap">{t.idle}</TableCell>
            <TableCell className="text-right tabular whitespace-nowrap">{t.offline}</TableCell>
            <TableCell className="pr-5 text-right tabular whitespace-nowrap">{t.active + t.idle + t.offline}</TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )
}

interface TeamActivityCardProps {
  data: TeamActivity | null | undefined
  isPending: boolean
  isError: boolean
  error: unknown
  isRefreshing: boolean
  onRetry: () => void
  available: boolean
  sample: boolean
}

export function TeamActivityCard({ data, isPending, isError, error, isRefreshing, onRetry, available, sample }: TeamActivityCardProps) {
  const [view, setView] = useState<ViewMode>('chart')
  const hasData = available && data && data.teams.length > 0

  return (
    <WidgetCard
      title="Team activity"
      description="Who is working right now, across teams"
      sample={sample}
      refreshing={isRefreshing}
      actions={hasData ? <ViewToggle value={view} onChange={setView} /> : null}
      className="xl:col-span-2"
    >
      {hasData && (
        <div className="flex flex-wrap gap-x-4 gap-y-1 px-5 pt-2">
          <LegendItem color={COLORS.active} label="Active" icon={Activity} />
          <LegendItem color={COLORS.idle} label="Idle" icon={Moon} />
          <LegendItem color={COLORS.offline} label="Offline" icon={PowerOff} />
        </div>
      )}
      {isError ? (
        <WidgetError error={error} onRetry={onRetry} />
      ) : isPending ? (
        <div className="grid gap-6 p-5 lg:grid-cols-2">
          <Skeleton className="h-52" />
          <Skeleton className="h-52" />
        </div>
      ) : !hasData ? (
        <WidgetUnavailable
          icon={Radio}
          title="No live presence yet"
          description="Active, idle and offline status appears here once employees sign in to the WorkPulse desktop agent."
          phase={4}
        />
      ) : view === 'chart' ? (
        <Charts data={data} />
      ) : (
        <TableView data={data} />
      )}
    </WidgetCard>
  )
}
