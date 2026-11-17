import { Check } from 'lucide-react'

import { cn } from '@/lib/utils'
import type { ReportSection } from '@/types/api'

/** Everything a report can show, in the order it appears. */
export const SECTION_OPTIONS: { value: ReportSection; label: string }[] = [
  { value: 'summary', label: 'Summary' },
  { value: 'start_time', label: 'Start time & sign-ins' },
  { value: 'active_idle', label: 'Active & idle' },
  { value: 'categories', label: 'Productive / Neutral / Unproductive' },
  { value: 'productive_share', label: 'Productive %' },
  { value: 'customer_time', label: 'Customer time' },
  { value: 'top_apps', label: 'Top apps & websites' },
  { value: 'focus', label: 'Focus sessions' },
  { value: 'required_hours', label: 'Required hours' },
  { value: 'average', label: '7-day comparison' },
  { value: 'last_sign_out', label: 'Last sign-out' },
  { value: 'late_start', label: 'Late start' },
  { value: 'meetings', label: 'Meetings' },
  { value: 'tasks', label: 'Task time' },
  { value: 'screenshots', label: 'Screenshots' },
  { value: 'highlights', label: 'At a glance' },
  { value: 'action_items', label: 'Needs your action' },
  { value: 'overtime', label: 'Extra time' },
  { value: 'week', label: 'Week so far' },
  { value: 'week_compare', label: 'vs last week' },
  { value: 'long_breaks', label: 'Long breaks' },
  { value: 'team_totals', label: 'Team total' },
]

/** Manager-only items: they make no sense in an employee's own report. */
export const MANAGER_ONLY: ReportSection[] = ['highlights', 'action_items', 'team_totals']

/** Toggle one item, keeping the canonical order. */
export function toggleSection(list: ReportSection[], value: ReportSection): ReportSection[] {
  return SECTION_OPTIONS.map((o) => o.value).filter((v) => (v === value ? !list.includes(v) : list.includes(v)))
}

/** Tap-to-toggle content tags. */
export function ContentChips({
  value,
  onChange,
  disabled = false,
  exclude = [],
}: {
  value: ReportSection[]
  onChange: (next: ReportSection[]) => void
  disabled?: boolean
  exclude?: ReportSection[]
}) {
  return (
    <div className="flex flex-wrap gap-2">
      {SECTION_OPTIONS.filter((o) => !exclude.includes(o.value)).map((o) => {
        const on = value.includes(o.value)
        return (
          <button
            key={o.value}
            type="button"
            aria-pressed={on}
            disabled={disabled}
            onClick={() => onChange(toggleSection(value, o.value))}
            className={cn(
              'inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-[12.5px] transition',
              on ? 'border-primary/40 bg-primary-soft/60 font-medium text-foreground' : 'text-muted-foreground hover:bg-muted',
              disabled && 'cursor-not-allowed opacity-60',
            )}
          >
            {on && <Check className="size-3.5 text-primary" aria-hidden />}
            {o.label}
          </button>
        )
      })}
    </div>
  )
}
