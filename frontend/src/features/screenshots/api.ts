import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api, toQuery } from '@/lib/api-client'
import type {
  EmployeeScreenshotSettings,
  MonitoringStatus,
  ScreenshotDetail,
  ScreenshotMode,
  ScreenshotPage,
  ScreenshotPolicy,
  ScreenshotTimeline,
} from '@/types/api'

export interface ScreenshotFilters {
  day: string
  employee_id?: string
  team_id?: string
  hour?: number
}

export const screenshotKeys = {
  all: ['screenshots'] as const,
  policy: () => ['screenshots', 'policy'] as const,
  list: (filters: ScreenshotFilters) => ['screenshots', 'list', filters] as const,
  timeline: (filters: Omit<ScreenshotFilters, 'hour'>) => ['screenshots', 'timeline', filters] as const,
  detail: (id: string) => ['screenshots', 'detail', id] as const,
  employee: (id: string) => ['screenshots', 'employee', id] as const,
  monitoring: () => ['me', 'monitoring'] as const,
}

/** Signed image URLs expire after a few minutes; refresh pages a little before that. */
const URL_REFRESH_MS = 4 * 60_000

export function useScreenshotPolicy() {
  return useQuery({
    queryKey: screenshotKeys.policy(),
    queryFn: () => api.get<ScreenshotPolicy>('/companies/current/screenshot-policy'),
  })
}

export function useUpdateScreenshotPolicy() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (input: Partial<ScreenshotPolicy>) =>
      api.patch<ScreenshotPolicy>('/companies/current/screenshot-policy', input),
    onSuccess: (policy) => {
      client.setQueryData(screenshotKeys.policy(), policy)
      void client.invalidateQueries({ queryKey: ['screenshots', 'employee'] })
      void client.invalidateQueries({ queryKey: screenshotKeys.monitoring() })
    },
  })
}

export function useEmployeeScreenshotSettings(employeeId: string) {
  return useQuery({
    queryKey: screenshotKeys.employee(employeeId),
    queryFn: () => api.get<EmployeeScreenshotSettings>(`/employees/${employeeId}/screenshot-settings`),
  })
}

export function useUpdateEmployeeScreenshotSettings(employeeId: string) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (input: { mode: ScreenshotMode; interval_minutes: number | null }) =>
      api.put<EmployeeScreenshotSettings>(`/employees/${employeeId}/screenshot-settings`, input),
    onSuccess: (settings) => client.setQueryData(screenshotKeys.employee(employeeId), settings),
  })
}

export function useScreenshots(filters: ScreenshotFilters) {
  return useInfiniteQuery({
    queryKey: screenshotKeys.list(filters),
    queryFn: ({ pageParam }) =>
      api.get<ScreenshotPage>(`/screenshots${toQuery({ ...filters, before: pageParam ?? undefined, limit: 48 })}`),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.next_before,
    staleTime: URL_REFRESH_MS,
    refetchInterval: URL_REFRESH_MS,
  })
}

export function useScreenshotTimeline(filters: Omit<ScreenshotFilters, 'hour'>) {
  return useQuery({
    queryKey: screenshotKeys.timeline(filters),
    queryFn: () => api.get<ScreenshotTimeline>(`/screenshots/timeline${toQuery({ ...filters })}`),
  })
}

/** Opening a screenshot is audited server-side; fetch only when the viewer actually shows it. */
export function useScreenshotDetail(id: string | null) {
  return useQuery({
    queryKey: screenshotKeys.detail(id ?? ''),
    queryFn: () => api.get<ScreenshotDetail>(`/screenshots/${id}`),
    enabled: Boolean(id),
    staleTime: URL_REFRESH_MS,
    gcTime: URL_REFRESH_MS,
  })
}

export function useDeleteScreenshot() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => api.delete<void>(`/screenshots/${id}`),
    onSuccess: () => void client.invalidateQueries({ queryKey: screenshotKeys.all }),
  })
}

export function useMyMonitoring(enabled = true) {
  return useQuery({
    queryKey: screenshotKeys.monitoring(),
    queryFn: () => api.get<MonitoringStatus>('/me/monitoring'),
    refetchInterval: 60_000,
    enabled,
  })
}
