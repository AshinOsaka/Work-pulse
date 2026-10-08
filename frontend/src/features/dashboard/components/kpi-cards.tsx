import { useId } from 'react'
import { Activity, ArrowDownRight, ArrowUpRight, Clock, Gauge, Minus, Moon, Users, Wifi, type LucideIcon } from 'lucide-react'
import { Area, AreaChart, ResponsiveContainer } from 'recharts'

import { StatusDot } from '@/components/common/status'
import { Card } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/misc'
import type { Kpi, KpiSnapshot, Period } from '@/features/dashboard/data/types'
import { usePrefersReducedMotion } from '@/hooks/use-now'
import { formatNumber } from '@/lib/format'
import { cn } from '@/lib/utils'

/** 0.08 → "5 min", 4.25 → "4.3 h", 261 → "261 h". */
function formatHours(hours: number): string {
  if (hours > 0 && hours < 1) return `${Math.max(1, Math.round(hours * 60))} min`
  if (hours < 10) return `${Math.round(hours * 10) / 10} h`
  return `${formatNumber(hours)} h`
}

const COMPARE_LABEL: Record<Period, string> = { daily: 'vs yesterday', weekly: 'vs last week', monthly: 'vs last month' }
const PERIOD_LABEL: Record<Period, string> = { daily: 'Today', weekly: 'This week', monthly: 'This month' }

interface TileSpec {
  key: keyof Omit<KpiSnapshot, 'asOf'>
  label: string
  icon: LucideIcon
  format: (value: number) => string
  /** Whether an increase is good (true), bad (false) or neither (null). */
  higherIsBetter: boolean | null
  /** Change shown as percentage points instead of percent. */
  points?: boolean
  live?: boolean
  periodic?: boolean
  unavailableHint: string
}

const TILES: TileSpec[] = [
  { key: 'totalEmployees', label: 'Total employees', icon: Users, format: formatNumber, higherIsBetter: null, unavailableHint: '' },
  { key: 'online', label: 'Online', icon: Wifi, format: formatNumber, higherIsBetter: null, live: true, unavailableHint: 'Needs the desktop agent' },
  { key: 'active', label: 'Active', icon: Activity, format: formatNumber, higherIsBetter: true, live: true, unavailableHint: 'Needs the desktop agent' },
  { key: 'idle', label: 'Idle', icon: Moon, format: formatNumber, higherIsBetter: false, live: true, unavailableHint: 'Needs the desktop agent' },
  { key: 'workHours', label: 'Work hours', icon: Clock, format: formatHours, higherIsBetter: true, periodic: true, unavailableHint: 'Needs the desktop agent' },
  { key: 'productivity', label: 'Productive share', icon: Gauge, format: (v) => `${Math.round(v)}%`, higherIsBetter: true, points: true, periodic: true, unavailableHint: 'Needs productivity rules' },
]

function Delta({ kpi, spec, period }: { kpi: Kpi; spec: TileSpec; period: Period }) {
  if (kpi.value === null || kpi.previous === null) return null
  const diff = kpi.value - kpi.previous
  const relative = spec.points ? diff : kpi.previous === 0 ? 0 : (diff / kpi.previous) * 100
  const flat = Math.abs(relative) < 0.05
  const good = flat || spec.higherIsBetter === null ? null : spec.higherIsBetter === diff > 0
  const Icon = flat ? Minus : diff > 0 ? ArrowUpRight : ArrowDownRight
  const text = flat ? 'No change' : `${diff > 0 ? '+' : '−'}${Math.abs(relative).toFixed(1)}${spec.points ? ' pts' : '%'}`
  return (
    <p className="flex flex-wrap items-center gap-1.5 text-[12px] text-muted-foreground">
      <span
        className={cn(
          'inline-flex items-center gap-0.5 rounded px-1 py-px font-medium',
          good === true && 'bg-success-soft text-success',
          good === false && 'bg-destructive-soft text-destructive',
          good === null && 'bg-muted text-foreground',
        )}
      >
        <Icon className="size-3" aria-hidden />
        {text}
      </span>
      {spec.live ? 'vs this time yesterday' : COMPARE_LABEL[period]}
    </p>
  )
}

function Sparkline({ values }: { values: number[] }) {
  const id = useId()
  const reduced = usePrefersReducedMotion()
  if (values.length < 2) return null
  const data = values.map((v, i) => ({ i, v }))
  return (
    <div className="pointer-events-none absolute right-0 bottom-0 left-0 h-12 opacity-80" aria-hidden>
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ top: 4, right: 0, bottom: 0, left: 0 }} accessibilityLayer={false}>
          <defs>
            <linearGradient id={id} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="var(--chart-1)" stopOpacity={0.14} />
              <stop offset="100%" stopColor="var(--chart-1)" stopOpacity={0} />
            </linearGradient>
          </defs>
          <Area
            type="monotone"
            dataKey="v"
            stroke="var(--chart-1)"
            strokeOpacity={0.55}
            strokeWidth={1.5}
            fill={`url(#${id})`}
            isAnimationActive={!reduced}
            animationDuration={500}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  )
}

function Tile({ spec, kpi, period }: { spec: TileSpec; kpi: Kpi; period: Period }) {
  const Icon = spec.icon
  const available = kpi.value !== null
  return (
    <Card className="relative min-h-[132px] overflow-hidden p-4 transition-shadow hover:shadow-elevated">
      <div className="relative z-10 flex items-center justify-between gap-2">
        <p className="flex items-center gap-1.5 text-[13px] font-medium text-muted-foreground">
          {spec.label}
          {spec.live && available && <StatusDot tone="success" pulse className="size-1.5" />}
        </p>
        <Icon className="size-4 text-muted-foreground" aria-hidden />
      </div>
      <p className="relative z-10 mt-2 text-[26px] leading-none font-semibold tracking-tight">
        {available ? spec.format(kpi.value!) : <span className="text-muted-foreground">—</span>}
      </p>
      <div className="relative z-10 mt-2 min-h-5">
        {available ? (
          <Delta kpi={kpi} spec={spec} period={period} />
        ) : (
          <p className="text-[12px] text-muted-foreground">{spec.unavailableHint}</p>
        )}
      </div>
      {spec.periodic && available && (
        <p className="relative z-10 mt-1 text-[11px] text-muted-foreground">{PERIOD_LABEL[period]}</p>
      )}
      {available && <Sparkline values={kpi.history} />}
    </Card>
  )
}

export function KpiCards({
  data,
  isPending,
  period,
}: {
  data: KpiSnapshot | undefined
  isPending: boolean
  period: Period
}) {
  return (
    <section aria-label="Key metrics" className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
      {TILES.map((spec) =>
        isPending || !data ? (
          <Card key={spec.key} className="min-h-[132px] space-y-3 p-4">
            <Skeleton className="h-3 w-20" />
            <Skeleton className="h-7 w-16" />
            <Skeleton className="h-3 w-28" />
          </Card>
        ) : (
          <Tile key={spec.key} spec={spec} kpi={data[spec.key]} period={period} />
        ),
      )}
    </section>
  )
}
