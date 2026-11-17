import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { peopleKeys } from '@/features/people/api'
import { api, toQuery } from '@/lib/api-client'
import { useAuthStore } from '@/stores/auth-store'
import type { AgentRelease, UnproductiveAlertRow, AutoReportOverview, AutoReports, AutoReportStatus, Company, CustomerSystem, Page, Role, UserAdmin } from '@/types/api'

/** Desktop-agent version, download link and the API base to point the agent at. */
export function useAgentRelease() {
  return useQuery({ queryKey: ['agent', 'release'], queryFn: () => api.get<AgentRelease>('/agent/release'), staleTime: 300_000 })
}

export interface UserListParams {
  search?: string
  role?: Role
  page?: number
  page_size?: number
}

export function useUsers(params: UserListParams) {
  return useQuery({
    queryKey: ['users', params],
    queryFn: () => api.get<Page<UserAdmin>>(`/users${toQuery({ ...params })}`),
    placeholderData: keepPreviousData,
  })
}

export function useChangeUserRole() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: ({ userId, role }: { userId: string; role: string }) =>
      api.patch<UserAdmin>(`/users/${userId}/role`, { role }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ['users'] })
      void client.invalidateQueries({ queryKey: peopleKeys.all })
    },
  })
}

export interface CompanyInput {
  name?: string
  timezone?: string
  industry?: string | null
  size?: string | null
  work_days?: number[]
  required_minutes?: number[]
  time_claim_auto_minutes?: number
  start_check_enabled?: boolean
  start_check_time?: string
  start_check_grace_minutes?: number
  holidays?: string[]
  customer_systems?: CustomerSystem[]
  auto_reports?: AutoReports
}

/** Automatic reports: whether AI and e-mail are set up on the server, and the recent runs. */
export function useAutoReportStatus(enabled = true) {
  return useQuery({
    queryKey: ['auto-reports', 'status'],
    queryFn: () => api.get<AutoReportStatus>('/auto-reports/status'),
    enabled,
  })
}

/** Who receives which report, the departments and teams behind it, and the e-mails of the last 7 days. */
export function useAutoReportOverview() {
  return useQuery({
    queryKey: ['auto-reports', 'overview'],
    queryFn: () => api.get<AutoReportOverview>('/auto-reports/overview'),
  })
}

/** Unproductive alerts sent between two local days (YYYY-MM-DD), newest first. */
export function useUnproductiveAlerts(start: string, end: string) {
  return useQuery({
    queryKey: ['auto-reports', 'alerts', start, end],
    queryFn: () => api.get<UnproductiveAlertRow[]>(`/auto-reports/alerts${toQuery({ start, end })}`),
    placeholderData: keepPreviousData,
  })
}

/** Send one report now, only to the signed-in administrator. */
export function useSendTestReport() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (slot: 'midday' | 'evening') =>
      api.post<{ sent_to: string; people: number; ai: boolean }>('/auto-reports/test', { slot }),
    onSuccess: () => void client.invalidateQueries({ queryKey: ['auto-reports'] }),
  })
}

export function useUpdateCompany() {
  const updateSession = useAuthStore((s) => s.updateSession)
  return useMutation({
    mutationFn: (input: CompanyInput) => api.patch<Company>('/companies/current', input),
    onSuccess: (company) => updateSession({ company }),
  })
}

