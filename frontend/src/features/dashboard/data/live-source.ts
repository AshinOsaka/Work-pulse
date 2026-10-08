/**
 * LIVE DATA SOURCE — real WorkPulse APIs only.
 *
 * Available: head-count (People API), teams, live presence and work hours
 * (desktop agent, Phases 4-5) and the organisation activity feed (audit trail).
 * Productivity and alerts come from their modules; where something has no live source yet,
 * those methods return empty values and `availability` tells widgets to render
 * an honest empty state. To wire a new API, implement the method here —
 * widgets do not change.
 */
import { fetchTrend } from '@/features/productivity/api'
import { api, toQuery } from '@/lib/api-client'
import { subscribe as subscribeRealtime } from '@/lib/realtime'
import { NO_PERSON } from '@/features/dashboard/data/types'
import type {
  ActivityEvent,
  ActivityKind,
  DashboardDataSource,
  DashboardFilters,
  Kpi,
  LiveEmployee,
  TeamPresence,
} from '@/features/dashboard/data/types'
import type { Page, Employee, NotificationPage, Team } from '@/types/api'
import type { ProductivityTrend } from '@/types/api'

interface PresenceRow {
  employee: { id: string; full_name: string; job_title: string | null }
  team: { id: string; name: string } | null
  status: 'active' | 'idle' | 'offline'
  connected: boolean
  since: string | null
  session_started_at: string | null
  current_app: string | null
  device: { id: string; name: string; os: 'windows' | 'macos' | 'linux'; agent_version: string | null } | null
}

interface PresenceOverview {
  employees: PresenceRow[]
  counts: { online: number; active: number; idle: number; offline: number }
  as_of: string
}

interface WorkHours {
  current_hours: number
  previous_hours: number
  history: number[]
}

const presence = (filters: DashboardFilters) =>
  api.get<PresenceOverview>(`/presence${toQuery({ team_id: filters.teamId ?? undefined })}`)

interface FeedItem {
  id: string
  action: string
  occurred_at: string
  actor: { id: string; name: string; employee_id: string | null } | null
  subject: { employee_id: string; name: string } | null
  metadata: Record<string, unknown>
}

const unavailable: Kpi = { value: null, previous: null, history: [] }

const STATUS_LABEL: Record<string, string> = { active: 'active', on_leave: 'on leave', terminated: 'terminated' }
const ROLE_LABEL: Record<string, string> = {
  COMPANY_ADMIN: 'Company Admin',
  MANAGER: 'Manager',
  TEAM_LEAD: 'Team Lead',
  EMPLOYEE: 'Employee',
}

/** Translate an audit-trail item into a timeline entry. */
function toActivity(item: FeedItem): ActivityEvent {
  const subject = item.subject?.name ?? 'an employee'
  const meta = item.metadata
  const base = {
    id: item.id,
    timestamp: item.occurred_at,
    actor: item.actor ? { id: item.actor.id, name: item.actor.name, employeeId: item.actor.employee_id ?? undefined } : null,
  }
  const entry = (kind: ActivityKind, summary: string, detail?: string): ActivityEvent => ({ ...base, kind, summary, detail })

  switch (item.action) {
    case 'employee.created':
      return entry('people', `added ${subject} to the directory`, meta.invited ? 'Invitation sent' : undefined)
    case 'employee.updated':
      return entry('people', `updated ${subject}'s profile`, Array.isArray(meta.fields) ? `Changed: ${meta.fields.join(', ').replaceAll('_', ' ')}` : undefined)
    case 'employee.status_changed':
      return entry('people', `marked ${subject} as ${STATUS_LABEL[String(meta.to)] ?? String(meta.to)}`)
    case 'employee.invited':
      return entry('account', `invited ${subject} to WorkPulse`, meta.role ? `Role: ${ROLE_LABEL[String(meta.role)] ?? String(meta.role)}` : undefined)
    case 'invitation.accepted':
      return entry('account', 'joined the workspace')
    case 'device.registered':
      return entry('device', `registered a device for ${subject}`)
    case 'device.revoked':
      return entry('device', `revoked a device of ${subject}`)
    case 'user.role_changed':
      return entry('account', `changed ${subject}'s role`, `${ROLE_LABEL[String(meta.from)] ?? meta.from} → ${ROLE_LABEL[String(meta.to)] ?? meta.to}`)
    case 'department.created':
      return entry('people', typeof meta.name === 'string' ? `created the ${meta.name} department` : 'created a department')
    case 'device.enrolled':
      return entry('device', meta.method === 'enrollment_code' ? 'enrolled a device with a code' : 'connected the desktop agent', subject)
    case 'work.session_started':
      return entry('session', 'started a work session')
    case 'work.session_stopped':
      return entry('session', 'ended a work session', typeof meta.duration_minutes === 'number' ? formatMinutes(meta.duration_minutes) : undefined)
    case 'team.created':
      return entry('people', typeof meta.name === 'string' ? `created the ${meta.name} team` : 'created a team')
    case 'department.deleted':
      return entry('people', typeof meta.name === 'string' ? `deleted the ${meta.name} department` : 'deleted a department')
    case 'team.deleted':
      return entry('people', typeof meta.name === 'string' ? `deleted the ${meta.name} team` : 'deleted a team')
    default:
      return entry('people', item.action.replace('.', ' '))
  }
}

function formatMinutes(minutes: number): string {
  if (minutes < 1) return 'Under a minute'
  const h = Math.floor(minutes / 60)
  const m = minutes % 60
  return h ? `${h}h ${String(m).padStart(2, '0')}m` : `${m} min`
}

/** Latest bucket vs the one before, with the series as history (gaps where data is insufficient). */
function shareKpi(trend: ProductivityTrend): Kpi {
  const shares = trend.points.map((p) => p.productive_share)
  const known = shares.filter((v): v is number => v !== null)
  if (!known.length) return unavailable
  const latest = shares.at(-1) ?? null
  return { value: latest ?? known.at(-1)!, previous: shares.at(-2) ?? null, history: known }
}

async function headcount(filters: DashboardFilters): Promise<number> {
  const page = await api.get<Page<Employee>>(
    `/employees${toQuery({ status: ['active', 'on_leave'], team_id: filters.teamId ?? undefined, page_size: 1 })}`,
  )
  return page.total
}

export const liveSource: DashboardDataSource = {
  kind: 'live',
  availability: { presence: true, productivity: true, alerts: true, activity: true },
  getTeams: async () => (await api.get<Team[]>('/teams')).map(({ id, name }) => ({ id, name })),
  getKpis: async (filters) => {
    const [total, now, hours, trend] = await Promise.all([
      headcount(filters),
      presence(filters),
      api.get<WorkHours>(`/presence/work-hours${toQuery({ period: filters.period, team_id: filters.teamId ?? undefined })}`),
      fetchTrend(filters.period, filters.teamId).catch(() => null),
    ])
    const live = (value: number): Kpi => ({ value, previous: null, history: [] })
    return {
      totalEmployees: { value: total, previous: null, history: [] },
      online: live(now.counts.online),
      active: live(now.counts.active),
      idle: live(now.counts.idle),
      workHours: { value: hours.current_hours, previous: hours.previous_hours, history: hours.history },
      productivity: trend ? shareKpi(trend) : unavailable,
      asOf: now.as_of,
    }
  },
  getProductivityTrend: async (filters) => {
    const trend = await fetchTrend(filters.period, filters.teamId).catch(() => null)
    if (!trend || trend.points.every((p) => p.classified_seconds === 0)) return []
    return trend.points.map((p) => ({ date: p.start, productivity: p.productive_share, workHours: p.work_seconds / 3600 }))
  },
  getTeamActivity: async (filters) => {
    const now = await presence(filters)
    const teams = new Map<string, TeamPresence>()
    for (const row of now.employees) {
      const key = row.team?.id ?? 'none'
      const team = teams.get(key) ?? { teamId: key, teamName: row.team?.name ?? 'No team', active: 0, idle: 0, offline: 0 }
      team[row.status] += 1
      teams.set(key, team)
    }
    return { teams: [...teams.values()].sort((a, b) => a.teamName.localeCompare(b.teamName)), timeline: [] }
  },
  getLiveEmployees: async (filters) =>
    (await presence(filters)).employees.map(
      (row): LiveEmployee => ({
        person: { id: row.employee.id, name: row.employee.full_name, employeeId: row.employee.id },
        title: row.employee.job_title ?? 'No title',
        teamName: row.team?.name ?? 'No team',
        status: row.status,
        // Foreground application name only (activity policy permitting); tasks arrive in Phase 9.
        application: row.current_app ? { name: row.current_app } : null,
        task: null,
        since: row.session_started_at ?? row.since ?? now(),
        device: row.device ? { name: row.device.name, os: row.device.os } : null,
      }),
    ),
  // Your own notifications (the same ones as the bell): unread are "open", read are "acknowledged".
  getAlerts: async () =>
    (await api.get<NotificationPage>(`/notifications${toQuery({ page_size: 8 })}`)).items.map((n) => ({
      id: n.id,
      timestamp: n.last_occurred_at,
      person: n.employee ? { id: n.employee.id, name: n.employee.name, employeeId: n.employee.id } : { id: NO_PERSON, name: '' },
      type: n.type,
      detail: n.count > 1 ? `${n.title} (×${n.count})` : n.title,
      severity: n.severity,
      status: n.read ? 'acknowledged' : 'open',
    })),
  getActivity: async (filters) =>
    (await api.get<FeedItem[]>(`/activity/feed${toQuery({ limit: 30, team_id: filters.teamId ?? undefined })}`)).map(toActivity),
  // Notifications arrive over the gateway (see features/notifications); presence and activity still poll.
  subscribe: (listener) =>
    subscribeRealtime((event) => {
      if (event.type === 'presence.changed') listener({ type: 'presence.changed', at: event.ts })
    }),
}

const now = () => new Date().toISOString()
