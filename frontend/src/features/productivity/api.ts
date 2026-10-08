import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api, toQuery } from '@/lib/api-client'
import type {
  EmployeeProductivity,
  ProductivityGroups,
  ProductivityRule,
  ProductivityTrend,
  ProfileTemplate,
  RuleInput,
  TeamProductivity,
  UnclassifiedItem,
  WorkProfile,
} from '@/types/api'

export interface RangeParams {
  start: string
  end: string
}

/** Who a report or trend covers: everyone in scope, a department, a team, or one person. */
export interface ScopeParams {
  team_id?: string
  department_id?: string
  employee_id?: string
}

export type TrendPeriod = 'daily' | 'weekly' | 'monthly'

export const productivityKeys = {
  all: ['productivity'] as const,
  rules: () => ['productivity', 'rules'] as const,
  unclassified: (range: RangeParams) => ['productivity', 'unclassified', range] as const,
  team: (params: RangeParams & ScopeParams) => ['productivity', 'team', params] as const,
  employee: (id: string, range: RangeParams) => ['productivity', 'employee', id, range] as const,
  trend: (period: string, teamId?: string) => ['productivity', 'trend', period, teamId ?? ''] as const,
  trends: (period: TrendPeriod, scope: ScopeParams) => ['productivity', 'trends', period, scope] as const,
  groups: (by: string, range: RangeParams) => ['productivity', 'groups', by, range] as const,
  profiles: () => ['productivity', 'profiles'] as const,
  templates: () => ['productivity', 'templates'] as const,
}

export function useRules(enabled = true) {
  return useQuery({ queryKey: productivityKeys.rules(), queryFn: () => api.get<ProductivityRule[]>('/productivity/rules'), enabled })
}

/** Any rule change re-categorises everything: refresh every productivity view. */
function useRuleMutation<TVars, TResult>(fn: (vars: TVars) => Promise<TResult>) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: fn,
    onSuccess: () => void client.invalidateQueries({ queryKey: productivityKeys.all }),
  })
}

export const useCreateRule = () => useRuleMutation((input: RuleInput) => api.post<ProductivityRule>('/productivity/rules', input))
export const useUpdateRule = () =>
  useRuleMutation(({ id, ...input }: { id: string; category?: string; note?: string | null }) =>
    api.patch<ProductivityRule>(`/productivity/rules/${id}`, input),
  )
export const useDeleteRule = () => useRuleMutation((id: string) => api.delete<void>(`/productivity/rules/${id}`))
export const useLoadRecommended = () =>
  useRuleMutation(() => api.post<{ added: number; skipped: number }>('/productivity/rules/recommended'))

export function useUnclassified(range: RangeParams, enabled = true) {
  return useQuery({
    queryKey: productivityKeys.unclassified(range),
    queryFn: () => api.get<UnclassifiedItem[]>(`/productivity/unclassified${toQuery({ ...range })}`),
    placeholderData: keepPreviousData,
    enabled,
  })
}

export function useTeamProductivity(params: RangeParams & ScopeParams, enabled = true) {
  return useQuery({
    queryKey: productivityKeys.team(params),
    queryFn: () => api.get<TeamProductivity>(`/productivity/team${toQuery({ ...params })}`),
    placeholderData: keepPreviousData,
    enabled,
  })
}

export function useEmployeeProductivity(employeeId: string, range: RangeParams, enabled = true) {
  return useQuery({
    queryKey: productivityKeys.employee(employeeId, range),
    queryFn: () => api.get<EmployeeProductivity>(`/productivity/employees/${employeeId}${toQuery({ ...range })}`),
    placeholderData: keepPreviousData,
    enabled: enabled && Boolean(employeeId),
  })
}

export function useProductivityTrend(period: TrendPeriod, scope: ScopeParams) {
  return useQuery({
    queryKey: productivityKeys.trends(period, scope),
    queryFn: () => api.get<ProductivityTrend>(`/productivity/trend${toQuery({ period, ...scope })}`),
    placeholderData: keepPreviousData,
  })
}

export function useProductivityGroups(by: 'department' | 'team', range: RangeParams) {
  return useQuery({
    queryKey: productivityKeys.groups(by, range),
    queryFn: () => api.get<ProductivityGroups>(`/productivity/groups${toQuery({ by, ...range })}`),
    placeholderData: keepPreviousData,
  })
}

export const useWorkProfiles = (enabled = true) =>
  useQuery({ queryKey: productivityKeys.profiles(), queryFn: () => api.get<WorkProfile[]>('/productivity/profiles'), enabled })

export const useProfileTemplates = (enabled = true) =>
  useQuery({
    queryKey: productivityKeys.templates(),
    queryFn: () => api.get<ProfileTemplate[]>('/productivity/profile-templates'),
    staleTime: Infinity,
    enabled,
  })

export const useCreateProfile = () =>
  useRuleMutation((input: { name: string; description?: string | null; template?: string | null }) =>
    api.post<WorkProfile>('/productivity/profiles', input),
  )
export const useUpdateProfile = () =>
  useRuleMutation(({ id, ...input }: { id: string; name?: string; description?: string | null }) =>
    api.patch<WorkProfile>(`/productivity/profiles/${id}`, input),
  )
export const useSetProfileMembers = () =>
  useRuleMutation(({ id, employee_ids }: { id: string; employee_ids: string[] }) =>
    api.put<WorkProfile>(`/productivity/profiles/${id}/members`, { employee_ids }),
  )
export const useDeleteProfile = () => useRuleMutation((id: string) => api.delete<void>(`/productivity/profiles/${id}`))

export function fetchTrend(period: string, teamId?: string | null) {
  return api.get<ProductivityTrend>(`/productivity/trend${toQuery({ period, team_id: teamId ?? undefined })}`)
}
