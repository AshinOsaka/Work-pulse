import { useQuery } from '@tanstack/react-query'

import { api, ApiError, API_BASE_URL } from '@/lib/api-client'
import { usePermissions } from '@/stores/auth-store'
import type { HealthResponse, RolesResponse } from '@/types/api'

export function useHealth() {
  return useQuery({
    queryKey: ['system', 'health'],
    queryFn: async () => {
      // A degraded backend answers 503 with a valid body; surface it as data.
      const response = await fetch(`${API_BASE_URL}/health`, { headers: { Accept: 'application/json' } })
      if (response.status === 200 || response.status === 503) return (await response.json()) as HealthResponse
      throw new ApiError(response.status, 'health_unavailable', 'Health endpoint unavailable')
    },
    refetchInterval: 30_000,
    retry: false,
  })
}

export function useRoles() {
  const { can } = usePermissions()
  return useQuery({
    queryKey: ['roles'],
    queryFn: () => api.get<RolesResponse>('/roles'),
    enabled: can('USER_MANAGE'),
    staleTime: 5 * 60_000,
  })
}
