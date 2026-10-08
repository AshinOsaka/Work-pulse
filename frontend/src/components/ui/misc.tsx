import * as React from 'react'
import { LoaderCircle } from 'lucide-react'
import { Progress as ProgressPrimitive, Separator as SeparatorPrimitive } from 'radix-ui'

import { cn } from '@/lib/utils'

function Separator({
  className,
  orientation = 'horizontal',
  decorative = true,
  ...props
}: React.ComponentProps<typeof SeparatorPrimitive.Root>) {
  return (
    <SeparatorPrimitive.Root
      data-slot="separator"
      decorative={decorative}
      orientation={orientation}
      className={cn(
        'shrink-0 bg-border data-[orientation=horizontal]:h-px data-[orientation=horizontal]:w-full data-[orientation=vertical]:h-full data-[orientation=vertical]:w-px',
        className,
      )}
      {...props}
    />
  )
}

/** Shimmering placeholder used while content loads. */
function Skeleton({ className, ...props }: React.ComponentProps<'div'>) {
  return (
    <div
      data-slot="skeleton"
      aria-hidden
      className={cn(
        'animate-shimmer rounded-md bg-muted bg-[linear-gradient(90deg,transparent,color-mix(in_oklch,var(--card)_70%,transparent),transparent)] bg-[length:400px_100%] bg-no-repeat',
        className,
      )}
      {...props}
    />
  )
}

function Kbd({ className, ...props }: React.ComponentProps<'kbd'>) {
  return (
    <kbd
      className={cn(
        'pointer-events-none inline-flex h-5 min-w-5 items-center justify-center gap-0.5 rounded border bg-subtle px-1 font-sans text-[10px] font-medium text-muted-foreground select-none',
        className,
      )}
      {...props}
    />
  )
}

function Progress({
  value,
  className,
  indicatorClassName,
  'aria-label': label,
}: {
  value: number
  className?: string
  indicatorClassName?: string
  /** What the bar measures; required so screen readers can announce it. */
  'aria-label': string
}) {
  const clamped = Math.min(100, Math.max(0, value))
  return (
    <ProgressPrimitive.Root
      value={clamped}
      aria-label={label}
      className={cn('relative h-1.5 w-full overflow-hidden rounded-full bg-muted', className)}
    >
      <ProgressPrimitive.Indicator
        className={cn('h-full rounded-full bg-primary transition-[width] duration-500', indicatorClassName)}
        style={{ width: `${clamped}%` }}
      />
    </ProgressPrimitive.Root>
  )
}

/** The one loading spinner (buttons use their own `loading` prop). Decorative: pair it with text or aria-busy. */
function Spinner({ className }: { className?: string }) {
  return <LoaderCircle className={cn('size-4 shrink-0 animate-spin text-muted-foreground', className)} aria-hidden />
}

export { Separator, Skeleton, Kbd, Progress, Spinner }
