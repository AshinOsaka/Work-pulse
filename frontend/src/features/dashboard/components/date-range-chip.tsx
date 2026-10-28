import { CalendarDays } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'

/**
 * The date-range chip: shows the current range as a small boxed label, and opens a popover with two
 * calendar date inputs to pick a custom start/end. Native date inputs give the OS calendar with no
 * extra dependency. Picking a date sets a custom range; "Reset" returns to the selected preset.
 */
export function DateRangeChip({
  start,
  end,
  max,
  isCustom,
  onChange,
  onReset,
}: {
  start: string
  end: string
  /** Latest selectable day (today, in the company timezone). */
  max: string
  isCustom: boolean
  onChange: (start: string, end: string) => void
  onReset: () => void
}) {
  const field =
    'h-8 w-full rounded-md border bg-card px-2 text-[13px] text-foreground outline-none focus-visible:ring-[3px] focus-visible:ring-ring/40 [color-scheme:light] dark:[color-scheme:dark]'
  return (
    <Popover>
      <PopoverTrigger asChild>
        <button
          type="button"
          className="hidden h-7 items-center gap-1.5 rounded-lg border bg-muted/60 px-3 text-[12px] text-muted-foreground tabular transition hover:text-foreground sm:inline-flex"
          aria-label="Choose a date range"
        >
          <CalendarDays className="size-3.5" aria-hidden />
          {start} → {end}
        </button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-60 space-y-3">
        <p className="text-[13px] font-medium">Custom date range</p>
        <div className="space-y-1">
          <label htmlFor="range-start" className="text-[12px] text-muted-foreground">
            Start date
          </label>
          <input
            id="range-start"
            type="date"
            value={start}
            max={end}
            onChange={(e) => e.target.value && onChange(e.target.value, end)}
            className={field}
          />
        </div>
        <div className="space-y-1">
          <label htmlFor="range-end" className="text-[12px] text-muted-foreground">
            End date
          </label>
          <input
            id="range-end"
            type="date"
            value={end}
            min={start}
            max={max}
            onChange={(e) => e.target.value && onChange(start, e.target.value)}
            className={field}
          />
        </div>
        {isCustom && (
          <Button variant="ghost" size="sm" className="w-full" onClick={onReset}>
            Reset to preset
          </Button>
        )}
      </PopoverContent>
    </Popover>
  )
}
