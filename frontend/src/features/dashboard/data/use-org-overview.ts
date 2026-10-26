/**
 * Organization View data — real WorkPulse APIs only.
 *
 * One date range and one team filter scope every widget: live presence, work-hours and
 * productivity (the productivity module), application and website usage (activity tracking)
 * and attendance (presence). Each query is independent so a slow or empty one never blocks
 * the rest; widgets render an honest empty state when their data is missing.
 */
import { keepPreviousData, useQuery } from '@tanstack/react-query'

import { liveSource } from '@/features/dashboard/data/live-source'
import { api, toQuery } from '@/lib/api-client'
import type {
  ApplicationUsageReport,
  AttendanceSummary,
  PresenceOverview,
  Team,
  TeamProductivity,
  WebsiteUsageReport,
} from '@/types/api'

export interface OrgRange {
  start: string
  end: string
}

const common = { placeholderData: keepPreviousData, staleTime: 15_000 } as const

const keys = {
  presence: (teamId: string | null) => ['org', 'presence', teamId] as const,
  team: (range: OrgRange, teamId: string | null) => ['org', 'team-productivity', range, teamId] as const,
  apps: (range: OrgRange, teamId: string | null) => ['org', 'applications', range, teamId] as const,
  sites: (range: OrgRange, teamId: string | null) => ['org', 'websites', range, teamId] as const,
  attendance: (range: OrgRange, teamId: string | null) => ['org', 'attendance', range, teamId] as const,
  activity: (teamId: string | null) => ['org', 'activity', teamId] as const,
}

export function useOrgOverview(range: OrgRange, teamId: string | null) {
  const scope = { team_id: teamId ?? undefined }

  const teams = useQuery({
    queryKey: ['org', 'teams'],
    queryFn: () => api.get<Team[]>('/teams'),
    staleTime: 300_000,
  })
  // Live presence refreshes on its own; the rest is historical and only changes on range/scope.
  const presence = useQuery({
    ...common,
    queryKey: keys.presence(teamId),
    queryFn: () => api.get<PresenceOverview>(`/presence${toQuery(scope)}`),
    refetchInterval: 30_000,
  })
  const productivity = useQuery({
    ...common,
    queryKey: keys.team(range, teamId),
    queryFn: () => api.get<TeamProductivity>(`/productivity/team${toQuery({ ...range, ...scope })}`),
  })
  const applications = useQuery({
    ...common,
    queryKey: keys.apps(range, teamId),
    queryFn: () => api.get<ApplicationUsageReport>(`/activity/applications${toQuery({ ...range, ...scope })}`),
  })
  const websites = useQuery({
    ...common,
    queryKey: keys.sites(range, teamId),
    queryFn: () => api.get<WebsiteUsageReport>(`/activity/websites${toQuery({ ...range, ...scope })}`),
  })
  const attendance = useQuery({
    ...common,
    queryKey: keys.attendance(range, teamId),
    queryFn: () => api.get<AttendanceSummary>(`/presence/attendance${toQuery({ ...range, ...scope })}`),
  })
  // Organisation activity feed (audit trail) — scoped to the viewer, independent of the date range.
  const activity = useQuery({
    ...common,
    queryKey: keys.activity(teamId),
    queryFn: () => liveSource.getActivity({ period: 'daily', teamId }),
    refetchInterval: 60_000,
  })

  return { teams, presence, productivity, applications, websites, attendance, activity }
}
