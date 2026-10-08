/** Calendar helpers for activity, which is always bucketed by the workspace timezone. */

/** Today's date (YYYY-MM-DD) in a timezone. */
export function todayIn(timeZone: string): string {
  try {
    return new Intl.DateTimeFormat('en-CA', { timeZone }).format(new Date())
  } catch {
    return new Date().toISOString().slice(0, 10)
  }
}

/** Shift a YYYY-MM-DD date by whole days (calendar arithmetic, no timezone involved). */
export function shiftDay(day: string, days: number): string {
  const date = new Date(`${day}T00:00:00Z`)
  date.setUTCDate(date.getUTCDate() + days)
  return date.toISOString().slice(0, 10)
}

export function formatDay(day: string, style: 'long' | 'short' = 'long'): string {
  return new Date(`${day}T00:00:00Z`).toLocaleDateString(undefined, {
    timeZone: 'UTC',
    weekday: style === 'long' ? 'long' : 'short',
    day: 'numeric',
    month: style === 'long' ? 'long' : 'short',
  })
}

/** Clock time of an instant in the workspace timezone. */
export function formatClock(value: string | number, timeZone: string): string {
  try {
    return new Date(value).toLocaleTimeString(undefined, { timeZone, hour: '2-digit', minute: '2-digit' })
  } catch {
    return new Date(value).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })
  }
}

/** Tracked time as "3h 05m", "12m" or "<1m". */
export function formatSeconds(seconds: number): string {
  const minutes = Math.round(seconds / 60)
  if (seconds > 0 && minutes === 0) return '<1m'
  const hours = Math.floor(minutes / 60)
  if (hours === 0) return `${minutes}m`
  return `${hours}h ${String(minutes % 60).padStart(2, '0')}m`
}

export function percent(part: number, whole: number): number {
  return whole > 0 ? Math.round((100 * part) / whole) : 0
}
