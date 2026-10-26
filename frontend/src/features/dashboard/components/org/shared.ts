/** Helpers shared by the Organization View widgets. */

/** Seconds as a clock duration, "77:33:30" (hours can exceed 24). */
export function formatClock(seconds: number): string {
  const total = Math.max(0, Math.round(seconds))
  const h = Math.floor(total / 3600)
  const m = Math.floor((total % 3600) / 60)
  const s = total % 60
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${pad(h)}:${pad(m)}:${pad(s)}`
}

/** A compact "2h 05m" / "6m" label for list rows. */
export function formatShort(seconds: number): string {
  const total = Math.max(0, Math.round(seconds))
  const h = Math.floor(total / 3600)
  const m = Math.floor((total % 3600) / 60)
  if (h > 0) return `${h}h ${String(m).padStart(2, '0')}m`
  if (m > 0) return `${m}m`
  return `${total}s`
}

/** Label a day bucket for an axis, e.g. "21 Oct". */
export function dayLabel(iso: string, long = false): string {
  const d = new Date(`${iso}T00:00:00`)
  return d.toLocaleDateString(undefined, long ? { weekday: 'long', day: 'numeric', month: 'short' } : { day: 'numeric', month: 'short' })
}
