import { useEffect } from 'react'
import { keepPreviousData, useQuery, useQueryClient } from '@tanstack/react-query'

import { liveSource } from '@/features/dashboard/data/live-source'
import { sampleSource } from '@/features/dashboard/data/mock/mock-source'
import type { DashboardDataSource, DashboardFilters } from '@/features/dashboard/data/types'
import { useUiStore } from '@/stores/ui-store'

export function useDashboardSource(): DashboardDataSource {
  const mode = useUiStore((s) => s.dashboardMode)
  return mode === 'sample' ? sampleSource : liveSource
}

const keys = {
  root: (kind: string) => ['dashboard', kind] as const,
  part: (kind: string, part: string, filters?: DashboardFilters) => ['dashboard', kind, part, filters] as const,
}

/** All dashboard queries plus the realtime subscription that keeps them fresh. */
export function useDashboard(filters: DashboardFilters) {
  const source = useDashboardSource()
  const client = useQueryClient()
  // Live presence is polled and refreshed on realtime presence events. Sample data streams via subscribe().
  const poll = source.kind === 'live' ? 30_000 : false
  const common = { placeholderData: keepPreviousData, staleTime: 15_000, refetchInterval: poll } as const

  const teams = useQuery({ queryKey: keys.part(source.kind, 'teams'), queryFn: () => source.getTeams(), staleTime: 300_000 })
  const kpis = useQuery({ ...common, queryKey: keys.part(source.kind, 'kpis', filters), queryFn: () => source.getKpis(filters) })
  const trend = useQuery({ ...common, queryKey: keys.part(source.kind, 'trend', filters), queryFn: () => source.getProductivityTrend(filters) })
  const teamActivity = useQuery({ ...common, queryKey: keys.part(source.kind, 'team-activity', filters), queryFn: () => source.getTeamActivity(filters) })
  const employees = useQuery({ ...common, queryKey: keys.part(source.kind, 'employees', filters), queryFn: () => source.getLiveEmployees(filters) })
  const alerts = useQuery({ ...common, queryKey: keys.part(source.kind, 'alerts', filters), queryFn: () => source.getAlerts(filters) })
  const activity = useQuery({
    ...common,
    queryKey: keys.part(source.kind, 'activity', filters),
    queryFn: () => source.getActivity(filters),
    // The live feed has no push channel yet; poll gently.
    refetchInterval: source.kind === 'live' ? 60_000 : false,
  })

  useEffect(
    () =>
      source.subscribe((event) => {
        const refresh = (...parts: string[]) =>
          parts.forEach((part) => void client.invalidateQueries({ queryKey: [...keys.root(source.kind), part] }))
        if (event.type === 'presence.changed') refresh('kpis', 'team-activity', 'employees')
        if (event.type === 'activity.created') refresh('activity')
        if (event.type === 'alert.created') refresh('alerts')
      }),
    [source, client],
  )

  /** Epoch ms of the most recent successful fetch (0 before the first one). */
  const updatedAt = Math.max(
    kpis.dataUpdatedAt,
    trend.dataUpdatedAt,
    teamActivity.dataUpdatedAt,
    employees.dataUpdatedAt,
    alerts.dataUpdatedAt,
    activity.dataUpdatedAt,
  )

  return { source, teams, kpis, trend, teamActivity, employees, alerts, activity, updatedAt }
}
