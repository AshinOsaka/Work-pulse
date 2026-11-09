import type { TimeClaimKind, TimeClaimStatus } from '@/types/api'

export const KINDS: TimeClaimKind[] = ['meeting', 'client_meeting', 'field_visit', 'call', 'other']

export const KIND_LABEL: Record<TimeClaimKind, string> = {
  meeting: 'Meeting',
  client_meeting: 'Client meeting',
  field_visit: 'Field visit',
  call: 'Call',
  other: 'Other work away from the computer',
}

export const STATUS: Record<TimeClaimStatus, { label: string; variant: 'success' | 'warning' | 'destructive' }> = {
  approved: { label: 'Counted', variant: 'success' },
  pending: { label: 'Waiting for approval', variant: 'warning' },
  rejected: { label: 'Rejected', variant: 'destructive' },
}

/** 90 → "1h 30m", 120 → "2h", 45 → "45m". */
export function formatMinutes(minutes: number): string {
  const hours = Math.floor(minutes / 60)
  const rest = minutes % 60
  if (!hours) return `${rest}m`
  return rest ? `${hours}h ${String(rest).padStart(2, '0')}m` : `${hours}h`
}
