import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api, toQuery } from '@/lib/api-client'
import { useAuthStore } from '@/stores/auth-store'
import type { Page, UserAdmin } from '@/types/api'

export interface SignInSession {
  id: string
  created_at: string
  last_seen_at: string
  expires_at: string
  device: string
  ip_address: string | null
  mfa: boolean
  current: boolean
}

export interface MfaSetup {
  secret: string
  uri: string
  qr_svg: string
}

export interface AuditPerson {
  id: string
  name: string
  email: string | null
}

export interface AuditEntry {
  id: string
  at: string
  action: string
  label: string
  category: string | null
  actor: AuditPerson | null
  subject: AuditPerson | null
  target_type: string | null
  target_id: string | null
  ip_address: string | null
  device: string | null
  details: Record<string, unknown>
}

export interface AuditFilters {
  category?: string
  employee_id?: string
  start?: string
  end?: string
  page: number
  page_size: number
}

export const securityKeys = {
  sessions: ['security', 'sessions'] as const,
  audit: (filters: AuditFilters) => ['security', 'audit', filters] as const,
  auditCategories: ['security', 'audit-categories'] as const,
}

// ---------------------------------------------------------------- sessions
export const useSessions = () => useQuery({ queryKey: securityKeys.sessions, queryFn: () => api.get<SignInSession[]>('/auth/sessions') })

export function useRevokeSession() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => api.delete<void>(`/auth/sessions/${id}`),
    onSuccess: (_, id) => client.setQueryData<SignInSession[]>(securityKeys.sessions, (list) => list?.filter((s) => s.id !== id)),
    onSettled: () => void client.invalidateQueries({ queryKey: securityKeys.sessions }),
  })
}

export function useRevokeOtherSessions() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: () => api.post<{ revoked: number }>('/auth/sessions/revoke-others'),
    onSettled: () => void client.invalidateQueries({ queryKey: securityKeys.sessions }),
  })
}

// ---------------------------------------------------------------- two-step verification
function useSetMfa() {
  const updateSession = useAuthStore((s) => s.updateSession)
  const user = useAuthStore((s) => s.user)
  return (enabled: boolean) => user && updateSession({ user: { ...user, mfa_enabled: enabled } })
}

export const useBeginMfaSetup = () => useMutation({ mutationFn: (password: string) => api.post<MfaSetup>('/auth/mfa/setup', { password }) })

export function useEnableMfa() {
  const setMfa = useSetMfa()
  return useMutation({
    mutationFn: (code: string) => api.post<{ codes: string[] }>('/auth/mfa/enable', { code }),
    onSuccess: () => setMfa(true),
  })
}

export function useDisableMfa() {
  const setMfa = useSetMfa()
  return useMutation({
    mutationFn: (input: { password: string; code: string }) => api.post<void>('/auth/mfa/disable', input),
    onSuccess: () => setMfa(false),
  })
}

export const useRegenerateRecoveryCodes = () =>
  useMutation({ mutationFn: (input: { password: string; code: string }) => api.post<{ codes: string[] }>('/auth/mfa/recovery-codes', input) })

// ---------------------------------------------------------------- administrators
export function useRevokeUserSessions() {
  return useMutation({ mutationFn: (userId: string) => api.post<{ revoked: number }>(`/users/${userId}/sessions/revoke`) })
}

export function useResetUserMfa() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (userId: string) => api.post<UserAdmin>(`/users/${userId}/mfa/reset`),
    onSuccess: () => void client.invalidateQueries({ queryKey: ['users'] }),
  })
}

// ---------------------------------------------------------------- audit trail
export const useAuditCategories = () =>
  useQuery({ queryKey: securityKeys.auditCategories, queryFn: () => api.get<{ key: string; label: string }[]>('/audit-logs/categories'), staleTime: Infinity })

export const useAuditLog = (filters: AuditFilters) =>
  useQuery({
    queryKey: securityKeys.audit(filters),
    queryFn: () => api.get<Page<AuditEntry>>(`/audit-logs${toQuery({ ...filters })}`),
    placeholderData: keepPreviousData,
  })
