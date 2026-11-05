import { keepPreviousData, useQuery } from '@tanstack/react-query'

import { todayIn } from '@/features/activity/format'
import { api, toQuery } from '@/lib/api-client'
import { useAuthStore } from '@/stores/auth-store'
import type { AttendanceReport } from '@/types/api'

export interface AttendanceReportParams {
  start: string
  end: string
  team_id?: string
  department_id?: string
  employee_id?: string
  /** false: leave out each day's detail when the report covers several people (totals only). */
  details?: boolean
}

export const attendanceKeys = {
  all: ['attendance'] as const,
  report: (params: AttendanceReportParams) => ['attendance', 'report', params] as const,
}

/** Today's figures grow while people work (the agent reports every minute), so a range that includes today
 *  refreshes on its own at the same pace as the dashboard. Past ranges don't change and aren't refetched. */
const LIVE_REFRESH_MS = 60_000

/** Per-person active time against the required hours, with each day's sign-in and sign-out. */
export function useAttendanceReport(params: AttendanceReportParams, enabled = true) {
  const timeZone = useAuthStore((s) => s.company?.timezone ?? 'UTC')
  const includesToday = params.end >= todayIn(timeZone)
  return useQuery({
    queryKey: attendanceKeys.report(params),
    queryFn: () => api.get<AttendanceReport>(`/presence/attendance/report${toQuery({ ...params })}`),
    placeholderData: keepPreviousData,
    enabled,
    refetchInterval: enabled && includesToday ? LIVE_REFRESH_MS : false,
  })
}
