import { useState, type ReactNode } from 'react'
import type { LucideIcon } from 'lucide-react'

import { Card } from '@/components/ui/card'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { cn } from '@/lib/utils'

/** A headline number on a page (above tables and charts). The dashboard's KPI cards add trends and sparklines. */
export function StatTile({
  label,
  value,
  hint,
  hintOnHover = false,
  icon: Icon,
  marker,
  muted = false,
}: {
  label: string
  value: ReactNode
  hint?: ReactNode
  /** Show the hint only when the tile is hovered, focused or clicked, instead of under the value. */
  hintOnHover?: boolean
  icon?: LucideIcon
  /** Background class of a small status dot before the label (e.g. "bg-presence-active"). */
  marker?: string
  /** The value is a status ("No tasks due") rather than a number. */
  muted?: boolean
}) {
  const [open, setOpen] = useState(false)
  const popup = Boolean(hint) && hintOnHover

  const body = (
    <Card
      className={cn('p-5', popup && 'cursor-help outline-none focus-visible:ring-2 focus-visible:ring-ring/50')}
      tabIndex={popup ? 0 : undefined}
      onClick={popup ? () => setOpen(true) : undefined}
    >
      <div className="flex items-center justify-between gap-2">
        <p className="flex items-center gap-2 text-[13px] font-medium text-muted-foreground">
          {marker && <span className={cn('size-2 rounded-full', marker)} aria-hidden />}
          {label}
        </p>
        {Icon && <Icon className="size-4 shrink-0 text-muted-foreground" aria-hidden />}
      </div>
      <p className={cn('mt-2 text-2xl font-semibold tracking-tight tabular', muted && 'text-base text-muted-foreground')}>{value}</p>
      {hint && !popup && <p className="mt-0.5 text-[12px] leading-snug text-muted-foreground">{hint}</p>}
    </Card>
  )

  if (!popup) return body
  return (
    <Tooltip open={open} onOpenChange={setOpen}>
      <TooltipTrigger asChild>{body}</TooltipTrigger>
      <TooltipContent side="bottom" className="max-w-sm text-[12px] leading-relaxed">
        {hint}
      </TooltipContent>
    </Tooltip>
  )
}
