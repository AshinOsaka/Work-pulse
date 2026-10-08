/** Local hour (0-23) of an instant in a timezone. */
export function hourIn(value: string, timeZone: string): number {
  try {
    return Number(new Intl.DateTimeFormat('en-GB', { timeZone, hour: '2-digit', hourCycle: 'h23' }).format(new Date(value)))
  } catch {
    return new Date(value).getUTCHours()
  }
}

/** Minutes since local midnight (handles half-hour offsets such as India or Newfoundland). */
export function minuteOfDay(value: string, timeZone: string): number {
  try {
    const parts = new Intl.DateTimeFormat('en-GB', { timeZone, hour: '2-digit', minute: '2-digit', hourCycle: 'h23' })
      .formatToParts(new Date(value))
    const get = (type: string) => Number(parts.find((p) => p.type === type)?.value ?? 0)
    return get('hour') * 60 + get('minute')
  } catch {
    const d = new Date(value)
    return d.getUTCHours() * 60 + d.getUTCMinutes()
  }
}

export function hourLabel(hour: number): string {
  return `${String(hour).padStart(2, '0')}:00`
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} kB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

export const WEEKDAYS: { value: number; short: string; long: string }[] = [
  { value: 1, short: 'Mon', long: 'Monday' },
  { value: 2, short: 'Tue', long: 'Tuesday' },
  { value: 3, short: 'Wed', long: 'Wednesday' },
  { value: 4, short: 'Thu', long: 'Thursday' },
  { value: 5, short: 'Fri', long: 'Friday' },
  { value: 6, short: 'Sat', long: 'Saturday' },
  { value: 7, short: 'Sun', long: 'Sunday' },
]

/** "Mon–Fri", "Mon, Wed, Fri", "Every day". */
export function formatDays(days: number[]): string {
  const sorted = [...days].sort((a, b) => a - b)
  if (sorted.length === 7) return 'Every day'
  const contiguous = sorted.every((d, i) => i === 0 || d === sorted[i - 1] + 1)
  const name = (d: number) => WEEKDAYS[d - 1]?.short ?? String(d)
  if (contiguous && sorted.length > 2) return `${name(sorted[0])}–${name(sorted[sorted.length - 1])}`
  return sorted.map(name).join(', ')
}

export function scheduleSummary(policy: {
  enabled: boolean
  interval_minutes: number
  work_hours_only: boolean
  work_start: string
  work_end: string
  work_days: number[]
}): string {
  if (!policy.enabled) return 'Off'
  const every = policy.interval_minutes === 1 ? 'Every minute' : `Every ${policy.interval_minutes} min`
  return policy.work_hours_only
    ? `${every} · ${formatDays(policy.work_days)} ${policy.work_start}–${policy.work_end}`
    : `${every} · during work sessions`
}
