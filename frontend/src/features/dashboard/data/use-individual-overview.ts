/**
 * Individual View data — one member's real WorkPulse figures.
 *
 * The employee productivity report drives Work Hours, the Productivity Trend and the Time Tracker
 * report (per-day metrics + activity span). A separate month-scoped report feeds the attendance
 * calendar; application/website usage and today's activity timeline come from their own endpoints.
 * Every query is disabled until a member is chosen.
 */
import { keepPreviousData, useQuery } from '@tanstack/react-query'

import { todayIn } from '@/features/activity/format'
import { api, toQuery } from '@/lib/api-client'
import type {
  ApplicationUsageReport,
  EmployeeActivityDay,
  EmployeeProductivity,
  WebsiteUsageReport,
} from '@/types/api'

export interface OrgRange {
  start: string
  end: string
}

/** First and last day of the local month that `day` falls in (YYYY-MM-DD). */
export function monthRange(day: string): OrgRange {
  const [y, m] = day.split('-').map(Number)
  const start = `${y}-${String(m).padStart(2, '0')}-01`
  const lastDay = new Date(Date.UTC(y, m, 0)).getUTCDate()
  return { start, end: `${y}-${String(m).padStart(2, '0')}-${String(lastDay).padStart(2, '0')}` }
}

const common = { placeholderData: keepPreviousData, staleTime: 15_000 } as const

export function useIndividualOverview(employeeId: string | null, range: OrgRange, timezone: string) {
  const enabled = Boolean(employeeId)
  const today = todayIn(timezone)
  const month = monthRange(range.end)

  const productivity = useQuery({
    ...common,
    enabled,
    queryKey: ['individual', 'productivity', employeeId, range],
    queryFn: () => api.get<EmployeeProductivity>(`/productivity/employees/${employeeId}${toQuery({ ...range })}`),
  })
  const calendar = useQuery({
    ...common,
    enabled,
    queryKey: ['individual', 'calendar', employeeId, month],
    queryFn: () => api.get<EmployeeProductivity>(`/productivity/employees/${employeeId}${toQuery({ ...month })}`),
  })
  const websites = useQuery({
    ...common,
    enabled,
    queryKey: ['individual', 'websites', employeeId, range],
    queryFn: () => api.get<WebsiteUsageReport>(`/activity/websites${toQuery({ ...range, employee_id: employeeId! })}`),
  })
  const applications = useQuery({
    ...common,
    enabled,
    queryKey: ['individual', 'applications', employeeId, range],
    queryFn: () => api.get<ApplicationUsageReport>(`/activity/applications${toQuery({ ...range, employee_id: employeeId! })}`),
  })
  const activityToday = useQuery({
    ...common,
    enabled,
    queryKey: ['individual', 'today', employeeId, today],
    queryFn: () => api.get<EmployeeActivityDay>(`/employees/${employeeId}/activity${toQuery({ day: today })}`),
    refetchInterval: enabled ? 60_000 : false,
  })

  return { productivity, calendar, websites, applications, today: activityToday, month }
}
