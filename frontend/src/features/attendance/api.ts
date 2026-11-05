import { keepPreviousData, useQuery } from '@tanstack/react-query'

import { api, toQuery } from '@/lib/api-client'
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

/** Per-person active time against the required hours, with each day's sign-in and sign-out. */
export function useAttendanceReport(params: AttendanceReportParams, enabled = true) {
  return useQuery({
    queryKey: attendanceKeys.report(params),
    queryFn: () => api.get<AttendanceReport>(`/presence/attendance/report${toQuery({ ...params })}`),
    placeholderData: keepPreviousData,
    enabled,
  })
}
