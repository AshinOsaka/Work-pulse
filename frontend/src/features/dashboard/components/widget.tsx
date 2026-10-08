import type { ReactNode } from 'react'
import { BarChart3, FlaskConical, Table2, TriangleAlert, type LucideIcon } from 'lucide-react'

import { EmptyState } from '@/components/common/empty-state'
import { ComingSoonBadge } from '@/components/common/status'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardDescription, CardTitle } from '@/components/ui/card'
import { SegmentedControl } from '@/components/ui/segmented-control'
import { errorMessage } from '@/lib/api-client'
import { cn } from '@/lib/utils'

export function SampleBadge() {
  return (
    <Badge variant="outline" className="border-dashed" title="Sample data — not from your workspace">
      <FlaskConical /> Sample
    </Badge>
  )
}

interface WidgetCardProps {
  title: string
  description?: ReactNode
  sample?: boolean
  actions?: ReactNode
  className?: string
  /** Dims content while a background refetch is in flight (no skeleton flash). */
  refreshing?: boolean
  children: ReactNode
}

export function WidgetCard({ title, description, sample, actions, className, refreshing, children }: WidgetCardProps) {
  return (
    <Card className={cn('min-w-0 overflow-hidden', className)}>
      {/* Actions wrap under the title on narrow screens instead of squeezing it. */}
      <div className="flex flex-col gap-2 px-5 pt-5 pb-1 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <CardTitle>{title}</CardTitle>
          {description && <CardDescription className="mt-1">{description}</CardDescription>}
        </div>
        {(actions || sample) && (
          <div className="flex shrink-0 flex-wrap items-center gap-2">
            {actions}
            {sample && <SampleBadge />}
          </div>
        )}
      </div>
      <div className={cn('flex min-h-0 flex-1 flex-col transition-opacity duration-300', refreshing && 'opacity-70')}>
        {children}
      </div>
    </Card>
  )
}

export function WidgetError({ error, onRetry }: { error: unknown; onRetry: () => void }) {
  return (
    <EmptyState
      size="sm"
      icon={TriangleAlert}
      title="Couldn't load this widget"
      description={errorMessage(error)}
      action={
        <Button size="sm" variant="outline" onClick={onRetry}>
          Try again
        </Button>
      }
    />
  )
}

export function WidgetUnavailable({
  icon,
  title,
  description,
  phase,
}: {
  icon: LucideIcon
  title: string
  description: string
  /** The phase that brings it, when it is not available yet. */
  phase?: number
}) {
  return <EmptyState size="sm" icon={icon} title={title} description={description} action={phase ? <ComingSoonBadge long /> : undefined} />
}

export type ViewMode = 'chart' | 'table'

/** Every chart has a table twin (accessible, and readable without hovering). */
export function ViewToggle({ value, onChange }: { value: ViewMode; onChange: (v: ViewMode) => void }) {
  return (
    <SegmentedControl
      size="sm"
      label="Display as"
      value={value}
      onChange={onChange}
      options={[
        { value: 'chart', label: 'Chart', icon: BarChart3 },
        { value: 'table', label: 'Table', icon: Table2 },
      ]}
    />
  )
}

export function LegendItem({ color, label, icon: Icon }: { color: string; label: string; icon?: LucideIcon }) {
  return (
    <span className="inline-flex items-center gap-1.5 text-[12px] text-muted-foreground">
      <span className="size-2.5 rounded-sm" style={{ background: color }} aria-hidden />
      {Icon && <Icon className="size-3.5" aria-hidden />}
      {label}
    </span>
  )
}

export function ChartTooltipBox({ title, rows }: { title: string; rows: { label: string; value: string; color?: string }[] }) {
  return (
    <div className="min-w-36 rounded-lg border bg-popover px-3 py-2 text-[12px] shadow-elevated">
      <p className="mb-1 font-medium text-foreground">{title}</p>
      {rows.map((row) => (
        <p key={row.label} className="flex items-center justify-between gap-4 text-muted-foreground">
          <span className="inline-flex items-center gap-1.5">
            {row.color && <span className="size-2 rounded-full" style={{ background: row.color }} aria-hidden />}
            {row.label}
          </span>
          <span className="font-medium text-foreground tabular">{row.value}</span>
        </p>
      ))}
    </div>
  )
}
