import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api, toQuery } from '@/lib/api-client'
import type { ActivityPolicy, ApplicationUsageReport, EmployeeActivityDay } from '@/types/api'

export const activityKeys = {
  all: ['activity'] as const,
  policy: () => ['activity', 'policy'] as const,
  applications: (params: ApplicationUsageParams) => ['activity', 'applications', params] as const,
  employeeDay: (id: string, day: string) => ['activity', 'employee', id, day] as const,
}

export interface ApplicationUsageParams {
  start: string
  end: string
  team_id?: string
  employee_id?: string
}

export function useActivityPolicy() {
  return useQuery({
    queryKey: activityKeys.policy(),
    queryFn: () => api.get<ActivityPolicy>('/companies/current/activity-policy'),
  })
}

export function useUpdateActivityPolicy() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (input: Partial<ActivityPolicy>) => api.patch<ActivityPolicy>('/companies/current/activity-policy', input),
    onSuccess: (policy) => client.setQueryData(activityKeys.policy(), policy),
  })
}

export function useApplicationUsage(params: ApplicationUsageParams, enabled = true) {
  return useQuery({
    queryKey: activityKeys.applications(params),
    queryFn: () => api.get<ApplicationUsageReport>(`/activity/applications${toQuery({ ...params })}`),
    placeholderData: keepPreviousData,
    enabled,
  })
}

export function useEmployeeActivity(employeeId: string, day: string) {
  return useQuery({
    queryKey: activityKeys.employeeDay(employeeId, day),
    queryFn: () => api.get<EmployeeActivityDay>(`/employees/${employeeId}/activity${toQuery({ day })}`),
    placeholderData: keepPreviousData,
  })
}
