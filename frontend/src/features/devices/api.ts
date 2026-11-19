import { keepPreviousData, useQuery } from '@tanstack/react-query'

import { api, toQuery } from '@/lib/api-client'
import type { AgentVersions, AutomationCheckRow, DeviceConnectionRow, UsbFileRow } from '@/types/api'

export interface RangeParams {
  start: string
  end: string
  employee_id?: string
}

export function useDeviceConnections(params: RangeParams, enabled = true) {
  return useQuery({
    queryKey: ['devices', 'connections', params],
    queryFn: () => api.get<DeviceConnectionRow[]>(`/devices/connections${toQuery({ ...params })}`),
    placeholderData: keepPreviousData,
    enabled,
  })
}

export function useConnectionFiles(connectionId: string | null) {
  return useQuery({
    queryKey: ['devices', 'files', connectionId],
    queryFn: () => api.get<UsbFileRow[]>(`/devices/connections/${connectionId}/files`),
    enabled: !!connectionId,
  })
}

export function useAutomationChecks(params: RangeParams, enabled = true) {
  return useQuery({
    queryKey: ['devices', 'automation', params],
    queryFn: () => api.get<AutomationCheckRow[]>(`/automation/checks${toQuery({ ...params })}`),
    placeholderData: keepPreviousData,
    enabled,
  })
}

export function useAgentVersions(enabled = true) {
  return useQuery({
    queryKey: ['devices', 'agent-versions'],
    queryFn: () => api.get<AgentVersions>('/agent/versions'),
    refetchInterval: 60_000,
    enabled,
  })
}
