import { MonitorSmartphone, SignalHigh, SignalZero, Wifi } from 'lucide-react'

import { Skeleton } from '@/components/ui/misc'
import { WidgetCard, WidgetError } from '@/features/dashboard/components/widget'
import type { PresenceOverview } from '@/types/api'

interface Props {
  data: PresenceOverview | undefined
  isPending: boolean
  isError: boolean
  error: unknown
  isRefreshing: boolean
  onRetry: () => void
}

function Tile({ icon: Icon, value, label, tone }: { icon: typeof Wifi; value: number; label: string; tone: string }) {
  return (
    <div className="flex flex-col gap-3 rounded-xl border bg-card p-4">
      <span className={`flex size-9 items-center justify-center rounded-lg ${tone}`}>
        <Icon className="size-4.5" aria-hidden />
      </span>
      <div>
        <p className="text-2xl font-semibold tabular">{value}</p>
        <p className="text-[12px] text-muted-foreground">{label}</p>
      </div>
    </div>
  )
}

export function ConnectedNowCard({ data, isPending, isError, error, isRefreshing, onRetry }: Props) {
  // "Device" = an employee who has enrolled the agent; signal = whether it checked in recently.
  const withDevice = data ? data.employees.filter((e) => e.device !== null) : []
  const allDevices = withDevice.length
  const activeSignal = withDevice.filter((e) => e.connected).length
  const noSignal = allDevices - activeSignal

  return (
    <WidgetCard
      title={
        <span className="inline-flex items-center gap-2">
          <Wifi className="size-4 text-primary" aria-hidden /> Connected Now
        </span>
      }
      description="Live device and signal counts"
      refreshing={isRefreshing}
    >
      {isError ? (
        <WidgetError error={error} onRetry={onRetry} />
      ) : isPending ? (
        <div className="grid gap-3 p-5 sm:grid-cols-3">
          <Skeleton className="h-28" />
          <Skeleton className="h-28" />
          <Skeleton className="h-28" />
        </div>
      ) : (
        <div className="grid gap-3 p-5 sm:grid-cols-3">
          <Tile icon={MonitorSmartphone} value={allDevices} label="All Devices" tone="bg-muted text-muted-foreground" />
          <Tile icon={SignalHigh} value={activeSignal} label="Active Signal" tone="bg-cat-productive/15 text-cat-productive" />
          <Tile icon={SignalZero} value={noSignal} label="No Signal" tone="bg-cat-unproductive/15 text-cat-unproductive" />
        </div>
      )}
    </WidgetCard>
  )
}
