import { Hourglass } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'

export type StatusTone = 'success' | 'warning' | 'danger' | 'neutral' | 'info'

const toneClasses: Record<StatusTone, string> = {
  success: 'bg-success',
  warning: 'bg-warning',
  danger: 'bg-destructive',
  neutral: 'bg-muted-foreground/50',
  info: 'bg-info',
}

export function StatusDot({ tone, pulse = false, className }: { tone: StatusTone; pulse?: boolean; className?: string }) {
  return (
    <span className={cn('relative inline-flex size-2 shrink-0', className)} aria-hidden>
      {pulse && <span className={cn('absolute inset-0 animate-ping rounded-full opacity-60', toneClasses[tone])} />}
      <span className={cn('relative inline-flex size-2 rounded-full', toneClasses[tone])} />
    </span>
  )
}

/** Marks a capability that is on the roadmap but not available yet. */
export function ComingSoonBadge({ long = false, className }: { long?: boolean; className?: string }) {
  return (
    <Badge variant="soft" className={className}>
      <Hourglass />
      {long ? 'Coming soon' : 'Soon'}
    </Badge>
  )
}
