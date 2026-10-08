import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { cn } from '@/lib/utils'

export interface FilterOption {
  value: string
  label: string
}

const ALL = '__all__'

/**
 * The one filter dropdown used across WorkPulse toolbars: an "all" choice plus options, full width on phones,
 * and highlighted while a filter is applied so people can see why a list is narrowed.
 */
export function FilterSelect({
  label,
  value,
  onChange,
  options,
  allLabel,
  id,
  className,
}: {
  /** Accessible name ("Team"). Ignored when `id` is set and a visible <Label htmlFor> names it. */
  label: string
  value: string | null | undefined
  onChange: (value: string | null) => void
  options: FilterOption[]
  /** The unfiltered choice, e.g. "All teams" or "Anyone". */
  allLabel: string
  id?: string
  className?: string
}) {
  const active = value != null
  return (
    <Select value={value ?? ALL} onValueChange={(v) => onChange(v === ALL ? null : v)}>
      <SelectTrigger
        id={id}
        size="sm"
        aria-label={id ? undefined : label}
        className={cn('w-full sm:w-44', active && 'border-primary/50 bg-primary-soft/40', className)}
      >
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value={ALL}>{allLabel}</SelectItem>
        {options.map((o) => (
          <SelectItem key={o.value} value={o.value}>
            {o.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}

/** `{ id, name }` records (teams, departments, people) as filter options. */
export function toOptions(items: { id: string; name: string }[] | undefined): FilterOption[] {
  return (items ?? []).map((i) => ({ value: i.id, label: i.name }))
}
