import type { NotificationType } from '@/types/api'

/**
 * Dashboard data contracts.
 *
 * Every widget consumes ONLY these types, never a concrete data source. The
 * sample source (`./mock`) and the live source (`./live-source.ts`) both
 * implement `DashboardDataSource`; replacing sample data with real APIs means
 * filling in the live source, with no widget changes.
 */

export type Period = 'daily' | 'weekly' | 'monthly'
export type PresenceStatus = 'active' | 'idle' | 'offline'
export type AppCategory = 'productive' | 'neutral' | 'unproductive'
/** Sample data uses low…critical; live notifications use info / warning / critical. */
export type AlertSeverity = 'low' | 'medium' | 'high' | 'critical' | 'info' | 'warning'
export type AlertStatus = 'open' | 'acknowledged' | 'resolved'
/** Sample-data alert kinds, plus the real notification types (live data). */
export type AlertType = 'idle_time' | 'unproductive_app' | 'overtime' | 'agent_offline' | 'blocked_site' | NotificationType
export type ActivityKind = 'session' | 'application' | 'idle' | 'task' | 'alert' | 'people' | 'device' | 'account'

export interface DashboardFilters {
  period: Period
  /** null = all teams visible to the viewer. */
  teamId: string | null
}

export interface TeamOption {
  id: string
  name: string
}

/** A KPI value with its comparison and a short history for a sparkline. `null` = not available yet. */
export interface Kpi {
  value: number | null
  previous: number | null
  history: number[]
}

export interface KpiSnapshot {
  totalEmployees: Kpi
  online: Kpi
  active: Kpi
  idle: Kpi
  /** Total hours worked in the selected period. */
  workHours: Kpi
  /** Productive share of classified time, 0–100, in the selected period (null: not enough data). */
  productivity: Kpi
  asOf: string
}

export interface TrendPoint {
  /** ISO date of the bucket start (day, week or month). */
  date: string
  /** Productive share 0–100; null when too little activity is classified to say. */
  productivity: number | null
  workHours: number
}

export interface TeamPresence {
  teamId: string
  teamName: string
  active: number
  idle: number
  offline: number
}

export interface PresencePoint {
  time: string
  active: number
  idle: number
}

export interface TeamActivity {
  teams: TeamPresence[]
  /** Per-minute presence for the last hour, oldest first. */
  timeline: PresencePoint[]
}

/** Alerts about a task, a project or the workspace rather than a person. */
export const NO_PERSON = 'none'

export interface PersonRef {
  id: string
  name: string
  /** Real employee id when this person exists in WorkPulse (live data); absent for sample people. */
  employeeId?: string
}

export interface LiveEmployee {
  person: PersonRef
  title: string
  teamName: string
  status: PresenceStatus
  /** Category arrives with productivity classification (Phase 8). */
  application: { name: string; category?: AppCategory } | null
  task: string | null
  /** When the current status began (drives the live duration). */
  since: string
  device: { name: string; os: 'windows' | 'macos' | 'linux' } | null
}

export interface DashboardAlert {
  id: string
  timestamp: string
  person: PersonRef
  type: AlertType
  detail: string
  severity: AlertSeverity
  status: AlertStatus
}

export interface ActivityEvent {
  id: string
  timestamp: string
  kind: ActivityKind
  actor: PersonRef | null
  /** Short sentence fragment after the actor's name, e.g. "switched to Figma". */
  summary: string
  detail?: string
}

/** Pushed by a source between fetches (WebSocket in production, a timer in sample mode). */
export type DashboardEvent =
  | { type: 'presence.changed'; at: string }
  | { type: 'activity.created'; event: ActivityEvent }
  | { type: 'alert.created'; alert: DashboardAlert }

/** Which capabilities have real data behind them. Widgets render an honest empty state otherwise. */
export interface DashboardAvailability {
  presence: boolean
  productivity: boolean
  alerts: boolean
  activity: boolean
}

export interface DashboardDataSource {
  readonly kind: 'sample' | 'live'
  readonly availability: DashboardAvailability
  getTeams(): Promise<TeamOption[]>
  getKpis(filters: DashboardFilters): Promise<KpiSnapshot>
  getProductivityTrend(filters: DashboardFilters): Promise<TrendPoint[]>
  getTeamActivity(filters: DashboardFilters): Promise<TeamActivity | null>
  getLiveEmployees(filters: DashboardFilters): Promise<LiveEmployee[]>
  getAlerts(filters: DashboardFilters): Promise<DashboardAlert[]>
  getActivity(filters: DashboardFilters): Promise<ActivityEvent[]>
  /** Subscribe to realtime events; returns an unsubscribe function. */
  subscribe(listener: (event: DashboardEvent) => void): () => void
}
