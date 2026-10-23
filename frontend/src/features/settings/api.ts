import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { peopleKeys } from '@/features/people/api'
import { api, toQuery } from '@/lib/api-client'
import { useAuthStore } from '@/stores/auth-store'
import type { AgentRelease, Company, CustomerSystem, Page, Role, UserAdmin } from '@/types/api'

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
    mutationFn: ({ userId, role }: { userId: string; role: Role }) =>
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
  holidays?: string[]
  customer_systems?: CustomerSystem[]
}

export function useUpdateCompany() {
  const updateSession = useAuthStore((s) => s.updateSession)
  return useMutation({
    mutationFn: (input: CompanyInput) => api.patch<Company>('/companies/current', input),
    onSuccess: (company) => updateSession({ company }),
  })
}

