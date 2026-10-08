import type { Role } from '@/types/api'

export const ROLE_LABELS: Record<Role, string> = {
  SUPER_ADMIN: 'Super Admin',
  COMPANY_ADMIN: 'Company Admin',
  MANAGER: 'Manager',
  TEAM_LEAD: 'Team Lead',
  EMPLOYEE: 'Employee',
}

const dateFormatter = new Intl.DateTimeFormat(undefined, { dateStyle: 'medium' })
const dateTimeFormatter = new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' })

export function formatDate(value: string | null | undefined): string {
  return value ? dateFormatter.format(new Date(value)) : '—'
}

export function formatDateTime(value: string | null | undefined): string {
  return value ? dateTimeFormatter.format(new Date(value)) : '—'
}

export function daysUntil(value: string | null | undefined): number | null {
  if (!value) return null
  return Math.max(0, Math.ceil((new Date(value).getTime() - Date.now()) / 86_400_000))
}

export function greeting(date = new Date()): string {
  const hour = date.getHours()
  if (hour < 12) return 'Good morning'
  if (hour < 18) return 'Good afternoon'
  return 'Good evening'
}

export function capitalize(value: string): string {
  return value.charAt(0).toUpperCase() + value.slice(1)
}

const ROLE_LEVELS: Record<Role, number> = {
  SUPER_ADMIN: 100,
  COMPANY_ADMIN: 80,
  MANAGER: 60,
  TEAM_LEAD: 40,
  EMPLOYEE: 20,
}

/** Mirrors `can_assign_role` on the API: up to your own level; Super Admin is platform-only. */
export function assignableRoles(actor: Role | undefined): Role[] {
  if (!actor) return []
  return (Object.keys(ROLE_LEVELS) as Role[]).filter(
    (role) => actor === 'SUPER_ADMIN' || (role !== 'SUPER_ADMIN' && ROLE_LEVELS[role] <= ROLE_LEVELS[actor]),
  )
}

export function timezones(): string[] {
  try {
    return Intl.supportedValuesOf('timeZone')
  } catch {
    return ['UTC']
  }
}

const relativeFormatter = new Intl.RelativeTimeFormat(undefined, { numeric: 'auto', style: 'short' })
const timeFormatter = new Intl.DateTimeFormat(undefined, { timeStyle: 'short' })

/** "just now", "5 min ago", "3 hr ago", "yesterday"… */
export function formatRelative(value: string | number | Date, now = Date.now()): string {
  const seconds = Math.round((new Date(value).getTime() - now) / 1000)
  const abs = Math.abs(seconds)
  if (abs < 45) return 'just now'
  if (abs < 3600) return relativeFormatter.format(Math.round(seconds / 60), 'minute')
  if (abs < 86_400) return relativeFormatter.format(Math.round(seconds / 3600), 'hour')
  return relativeFormatter.format(Math.round(seconds / 86_400), 'day')
}

export function formatTime(value: string | number | Date): string {
  return timeFormatter.format(new Date(value))
}

/** Elapsed duration as "2h 05m" or "4m 12s". */
export function formatDuration(ms: number): string {
  const totalSeconds = Math.max(0, Math.floor(ms / 1000))
  const hours = Math.floor(totalSeconds / 3600)
  const minutes = Math.floor((totalSeconds % 3600) / 60)
  const seconds = totalSeconds % 60
  if (hours > 0) return `${hours}h ${String(minutes).padStart(2, '0')}m`
  return `${minutes}m ${String(seconds).padStart(2, '0')}s`
}

const numberFormatter = new Intl.NumberFormat()
export function formatNumber(value: number): string {
  return numberFormatter.format(Math.round(value))
}
