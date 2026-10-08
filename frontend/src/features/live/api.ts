import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api, toQuery } from '@/lib/api-client'
import type { LiveEmployeeList, LivePolicy, LiveSession, LiveSessionList } from '@/types/api'

export const liveKeys = {
  all: ['live'] as const,
  policy: () => ['live', 'policy'] as const,
  employees: () => ['live', 'employees'] as const,
  session: (id: string) => ['live', 'session', id] as const,
  log: () => ['live', 'log'] as const,
}

export function useLivePolicy() {
  return useQuery({
    queryKey: liveKeys.policy(),
    queryFn: () => api.get<LivePolicy>('/companies/current/live-policy'),
  })
}

export function useUpdateLivePolicy() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (input: Partial<LivePolicy>) => api.patch<LivePolicy>('/companies/current/live-policy', input),
    onSuccess: (policy) => {
      client.setQueryData(liveKeys.policy(), policy)
      void client.invalidateQueries({ queryKey: liveKeys.employees() })
    },
  })
}

/** Online status changes as agents connect: refresh often, keep showing the last list while refetching. */
export function useLiveEmployees() {
  return useQuery({
    queryKey: liveKeys.employees(),
    queryFn: () => api.get<LiveEmployeeList>('/live/employees'),
    refetchInterval: 10_000,
  })
}

export function useStartLive() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (employeeId: string) => api.post<LiveSession>('/live/sessions', { employee_id: employeeId }),
    onSuccess: (session) => {
      client.setQueryData(liveKeys.session(session.id), session)
      void client.invalidateQueries({ queryKey: liveKeys.employees() })
    },
  })
}

/** The session log: who watched whom, on which device, when, and how it ended. */
export function useLiveSessionLog(enabled: boolean) {
  return useQuery({
    queryKey: liveKeys.log(),
    queryFn: () => api.get<LiveSessionList>(`/live/sessions${toQuery({ limit: 100 })}`),
    enabled,
    refetchInterval: 15_000,
  })
}

export function useLiveSession(id: string | undefined) {
  return useQuery({
    queryKey: liveKeys.session(id ?? ''),
    queryFn: () => api.get<LiveSession>(`/live/sessions/${id}`),
    enabled: Boolean(id),
  })
}

export function useStopLive() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => api.post<LiveSession>(`/live/sessions/${id}/stop`),
    onSuccess: (session) => {
      client.setQueryData(liveKeys.session(session.id), session)
      void client.invalidateQueries({ queryKey: liveKeys.employees() })
    },
  })
}
