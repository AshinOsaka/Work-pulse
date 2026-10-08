/** Mirrors backend schemas in backend/app/schemas. Keep in sync. */

export const ROLES = ['SUPER_ADMIN', 'COMPANY_ADMIN', 'MANAGER', 'TEAM_LEAD', 'EMPLOYEE'] as const
export type Role = (typeof ROLES)[number]

export const PERMISSIONS = [
  'EMPLOYEE_VIEW',
  'EMPLOYEE_MANAGE',
  'LIVE_STREAM_VIEW',
  'SCREENSHOT_VIEW',
  'ACTIVITY_VIEW',
  'REPORT_VIEW',
  'REPORT_EXPORT',
  'TASK_MANAGE',
  'PROJECT_MANAGE',
  'POLICY_MANAGE',
  'USER_MANAGE',
  'AUDIT_LOG_VIEW',
] as const
export type Permission = (typeof PERMISSIONS)[number]

export type UserStatus = 'active' | 'invited' | 'suspended' | 'deactivated'
export type CompanyStatus = 'trial' | 'active' | 'suspended'
export type CompanyPlan = 'trial' | 'starter' | 'business' | 'enterprise'

export interface User {
  id: string
  company_id: string
  email: string
  full_name: string
  role: Role
  status: UserStatus
  email_verified: boolean
  last_login_at: string | null
  created_at: string
  employee_id: string | null
  /** Two-step verification (authenticator app) is on for this account. */
  mfa_enabled: boolean
}

export interface Company {
  id: string
  name: string
  slug: string
  status: CompanyStatus
  plan: CompanyPlan
  timezone: string
  industry: string | null
  size: string | null
  trial_ends_at: string | null
  created_at: string
}

export interface SessionResponse {
  user: User
  company: Company
  permissions: Permission[]
}

export interface AuthResponse extends SessionResponse {
  access_token: string
  token_type: 'bearer'
  expires_in: number
}

/** Sign-in answer for accounts with two-step verification: finish at /auth/mfa/verify. */
export interface MfaChallengeResponse {
  mfa_required: true
  challenge: string
  expires_in: number
}

export const isMfaChallenge = (r: AuthResponse | MfaChallengeResponse): r is MfaChallengeResponse => 'mfa_required' in r

export interface MessageResponse {
  message: string
}

export interface HealthResponse {
  status: 'ok' | 'degraded'
  service: string
  version: string
  environment: string
  timestamp: string
  checks: Record<string, { status: 'ok' | 'unavailable'; latency_ms: number | null }>
}

export interface PermissionInfo {
  key: Permission
  name: string
  description: string
  category: string
}

export interface RoleInfo {
  key: Role
  name: string
  description: string
  level: number
  is_system: boolean
  permissions: Permission[]
}

export interface RolesResponse {
  roles: RoleInfo[]
  permissions: PermissionInfo[]
}

export interface ApiErrorBody {
  error: { code: string; message: string; details: unknown }
  request_id: string | null
}

export interface FieldErrorDetail {
  field: string | null
  message: string
  type: string
}

// --------------------------------------------------------------------------- Phase 2: organisation

export interface Page<T> {
  items: T[]
  total: number
  page: number
  page_size: number
  pages: number
}

export type EmployeeStatus = 'active' | 'on_leave' | 'terminated'
export type EmploymentType = 'full_time' | 'part_time' | 'contractor'
export type AccessState = 'none' | 'invited' | 'active' | 'suspended' | 'deactivated'
export type EmployeeSort = 'full_name' | 'job_title' | 'status' | 'employee_code' | 'hired_on' | 'created_at'

export interface Ref {
  id: string
  name: string
}

export interface EmployeeRef {
  id: string
  full_name: string
  email: string
  job_title: string | null
  status: EmployeeStatus
}

export interface Account {
  user_id: string
  role: Role
  status: UserStatus
  email_verified: boolean
  last_login_at: string | null
}

export interface Employee {
  id: string
  full_name: string
  email: string
  employee_code: string | null
  job_title: string | null
  employment_type: EmploymentType
  status: EmployeeStatus
  timezone: string
  location: string | null
  hired_on: string | null
  terminated_at: string | null
  department: Ref | null
  team: Ref | null
  manager: EmployeeRef | null
  account: Account | null
  access: AccessState
  created_at: string
  updated_at: string
}

export interface EmployeeDetail extends Employee {
  direct_reports: EmployeeRef[]
  device_count: number
  permissions: Permission[]
}

export interface EmployeeInput {
  full_name?: string
  email?: string
  employee_code?: string | null
  job_title?: string | null
  department_id?: string | null
  team_id?: string | null
  manager_employee_id?: string | null
  employment_type?: EmploymentType
  timezone?: string
  location?: string | null
  hired_on?: string | null
  invite?: boolean
  role?: Role
}

export interface EmployeeListParams {
  search?: string
  status?: EmployeeStatus[]
  department_id?: string
  team_id?: string
  manager_id?: string
  sort?: EmployeeSort
  order?: 'asc' | 'desc'
  page?: number
  page_size?: number
}

export interface PeopleSummary {
  total: number
  by_status: Record<EmployeeStatus, number>
  pending_invitations: number
  departments: { id: string | null; name: string; count: number }[]
  recent: EmployeeRef[]
}

export interface Department {
  id: string
  name: string
  description: string | null
  head: EmployeeRef | null
  employee_count: number
  team_count: number
  created_at: string
}

export interface Team {
  id: string
  name: string
  description: string | null
  department: Ref | null
  lead: EmployeeRef | null
  member_count: number
  created_at: string
}

export type DeviceOs = 'windows' | 'macos' | 'linux'
export type DeviceStatus = 'pending' | 'active' | 'inactive' | 'revoked'

export interface Device {
  id: string
  employee_id: string
  name: string
  hostname: string | null
  os: DeviceOs
  os_version: string | null
  agent_version: string | null
  status: DeviceStatus
  enrollment_expires_at: string | null
  enrolled_at: string | null
  last_seen_at: string | null
  revoked_at: string | null
  created_at: string
}

export interface DeviceRegistered extends Device {
  enrollment_code: string
}

export type UserAdmin = User

export interface InvitationPreview {
  email: string
  full_name: string
  company_name: string
  expires_at: string
}

// --------------------------------------------------------------------------- Phase 5: activity tracking

export interface ActivityPolicy {
  track_applications: boolean
  /** Off by default; never applied to password managers, private browsing, messaging or e-mail. */
  capture_window_titles: boolean
  /** Domain of the active browser tab only; off by default. */
  track_websites: boolean
  excluded_apps: string[]
}

export interface AppUsage {
  app_id: string
  app_name: string
  seconds: number
  active_seconds: number
  employees: number
}

export interface ApplicationUsageReport {
  start: string
  end: string
  timezone: string
  total_seconds: number
  active_seconds: number
  applications: AppUsage[]
}

export interface ActivitySegment {
  app_id: string
  app_name: string
  window_title: string | null
  started_at: string
  ended_at: string
  duration_seconds: number
  active_seconds: number
  activity_level: number
}

export interface EmployeeActivityDay {
  employee_id: string
  day: string
  timezone: string
  tracked_seconds: number
  active_seconds: number
  applications: AppUsage[]
  segments: ActivitySegment[]
  truncated: boolean
}

// --------------------------------------------------------------------------- Phase 6: screenshot monitoring

export interface ScreenshotPolicy {
  enabled: boolean
  interval_minutes: number
  work_hours_only: boolean
  /** 24-hour "HH:MM", in each employee's own timezone. */
  work_start: string
  work_end: string
  /** ISO weekdays: 1 = Monday … 7 = Sunday. */
  work_days: number[]
  retention_days: number
}

export type ScreenshotMode = 'inherit' | 'enabled' | 'disabled'

export interface EffectiveScreenshotPolicy extends ScreenshotPolicy {
  timezone: string
  source: 'workspace' | 'employee'
}

export interface EmployeeScreenshotSettings {
  employee_id: string
  mode: ScreenshotMode
  interval_minutes: number | null
  effective: EffectiveScreenshotPolicy
}

export interface ScreenshotItem {
  id: string
  employee: EmployeeRef
  captured_at: string
  width: number
  height: number
  /** Short-lived, viewer-bound signed URL. */
  thumbnail_url: string
}

export interface ScreenshotPage {
  items: ScreenshotItem[]
  next_before: string | null
  day: string
  timezone: string
}

export interface ScreenshotDetail extends ScreenshotItem {
  image_url: string
  device_name: string | null
  application: string | null
  size_bytes: number
  expires_at: string
  url_expires_in: number
}

export interface ScreenshotTimeline {
  day: string
  timezone: string
  total: number
  buckets: { hour: number; count: number }[]
  captures: { id: string; captured_at: string }[] | null
}

export interface MonitoringStatus {
  has_employee_record: boolean
  agent_connected: boolean
  session_active: boolean
  track_applications: boolean
  capture_window_titles: boolean
  screenshots:
    | (Omit<ScreenshotPolicy, 'retention_days'> & {
        retention_days: number
        timezone: string
        in_schedule_now: boolean
        last_captured_at: string | null
      })
    | null
  monitoring_active: boolean
  live_view_enabled: boolean
  live_viewer: string | null
}

// --------------------------------------------------------------------------- Phase 7: live screen viewing

export interface LivePolicy {
  enabled: boolean
  max_session_minutes: number
}

export type LiveStatus = 'requested' | 'connecting' | 'live' | 'interrupted' | 'ended'
export type LiveAvailability = 'available' | 'offline' | 'not_working' | 'in_session' | 'disabled'

export interface LiveDevice {
  id: string
  name: string
  os: 'windows' | 'macos' | 'linux'
  /** The agent's last heartbeat. */
  last_seen_at?: string | null
}

export interface LiveEmployee {
  employee: EmployeeRef
  department: { id: string; name: string } | null
  team: { id: string; name: string } | null
  device: LiveDevice | null
  online: boolean
  presence: 'active' | 'idle' | null
  current_app: string | null
  status_since: string | null
  live_session: { id: string; status: LiveStatus; viewer_name: string; mine: boolean } | null
  availability: LiveAvailability
}

export interface LiveEmployeeList {
  enabled: boolean
  max_session_minutes: number
  employees: LiveEmployee[]
}

export interface LiveSession {
  id: string
  status: LiveStatus
  employee: EmployeeRef
  device: LiveDevice | null
  viewer_name: string
  created_at: string
  connected_at: string | null
  expires_at: string
  ended_at: string | null
  end_reason: string | null
  duration_seconds: number | null
  reconnects: number
  /** How media was negotiated: 'p2p' today; an SFU route can be added server-side. */
  media_route: string
  /** Where the WebRTC connection stands, derived from the status. */
  connection_state: 'waiting_for_peer' | 'negotiating' | 'connected' | 'reconnecting' | 'closed'
}

export interface LiveSessionList {
  items: LiveSession[]
}

export type LiveEventType =
  | 'STREAM_REQUESTED'
  | 'STREAM_AUTHORIZED'
  | 'STREAM_CONNECTING'
  | 'STREAM_STARTED'
  | 'STREAM_DISCONNECTED'
  | 'STREAM_RECONNECTED'
  | 'STREAM_STOPPED'
  | 'STREAM_FAILED'

export interface LiveSessionEvent {
  id: string
  event: LiveEventType
  actor_role: string
  actor_id: string | null
  metadata: Record<string, unknown>
  timestamp: string
}

export interface LiveSessionEventList {
  session_id: string
  items: LiveSessionEvent[]
}

// --------------------------------------------------------------------------- Phase 8: productivity intelligence

export type ProductivityCategory = 'productive' | 'neutral' | 'unproductive'
export type UsageCategory = ProductivityCategory | 'unclassified'
export type RuleKind = 'app' | 'website'
export type RuleScope = 'company' | 'role' | 'department' | 'team' | 'profile'

export interface ProductivityRule {
  id: string
  kind: RuleKind
  pattern: string
  category: ProductivityCategory
  scope: RuleScope
  scope_ref: { id: string; name: string } | null
  role: Role | null
  note: string | null
  created_at: string
}

export interface RuleInput {
  kind: RuleKind
  pattern: string
  category: ProductivityCategory
  scope: RuleScope
  scope_id?: string | null
  role?: Role | null
  note?: string | null
}

export interface UnclassifiedItem {
  kind: RuleKind
  key: string
  name: string
  seconds: number
  employees: number
}

export interface ProductivityMetrics {
  work_seconds: number
  active_seconds: number
  idle_seconds: number
  extended_idle_seconds: number
  away_seconds: number
  tracked_seconds: number
  productive_seconds: number
  neutral_seconds: number
  unproductive_seconds: number
  unclassified_seconds: number
  focus_sessions: number
  focus_seconds: number
  longest_focus_seconds: number
  context_switches: number
  task_seconds: number
  tasks_completed: number
  tasks_due_open: number
}

export interface ProductivityScore {
  key: ScoreKey
  label: string
  value: number | null
  status: 'ok' | 'insufficient_data'
  formula: string
  components: { key: string; label: string; seconds: number }[]
  interpretation: string
  reason?: string | null
  coverage?: number | null
}

export type ScoreKey = 'activity_score' | 'productive_share' | 'focus_score' | 'work_utilization'
export type ProductivityScores = Record<ScoreKey, ProductivityScore>

export interface SummaryLine {
  key: string
  label: string
  value: string
  metrics: string[]
}

export interface ProjectSignal {
  id: string
  name: string
  key: string
  color: ProjectColor
  task_seconds: number
  tasks_completed: number
  progress: number
  total_tasks: number
}

export interface WorkProfile {
  id: string
  name: string
  description: string | null
  template: string | null
  members: EmployeeRef[]
  rule_count: number
  created_at: string
}

export interface ProfileTemplate {
  key: string
  name: string
  description: string
  rules: { kind: RuleKind; pattern: string; category: ProductivityCategory }[]
}

export interface ProductivityGroupRow {
  group: { id: string; name: string } | null
  people: number
  people_with_data: number
  metrics: ProductivityMetrics
  scores: ProductivityScores
  task_completion: number | null
}

export interface ProductivityGroups {
  by: 'department' | 'team'
  start: string
  end: string
  timezone: string
  rows: ProductivityGroupRow[]
  disclaimer: string
}

export interface ProductivityInsight {
  tone: 'positive' | 'info' | 'attention'
  title: string
  detail: string
  metrics: string[]
}

export interface DayProductivity {
  day: string
  metrics: ProductivityMetrics
  activity_score: number | null
  productive_share: number | null
  focus_score: number | null
  work_utilization: number | null
}

export interface UsageItem {
  kind: RuleKind
  key: string
  name: string
  seconds: number
  category: UsageCategory
  rule_scope: RuleScope | null
  rule_pattern: string | null
}

export interface FocusSession {
  started_at: string
  ended_at: string
  seconds: number
  productive_seconds: number
  top_apps: string[]
}

interface ProductivityBase {
  start: string
  end: string
  timezone: string
  totals: ProductivityMetrics
  scores: ProductivityScores
  task_completion: {
    available: boolean
    reason: string
    value: number | null
    formula?: string | null
    completed?: number
    due_open?: number
    task_seconds?: number
    interpretation?: string | null
  }
  days: DayProductivity[]
  summary: SummaryLine[]
  projects: ProjectSignal[]
  insights: ProductivityInsight[]
  disclaimer: string
}

export interface EmployeeProductivity extends ProductivityBase {
  employee: EmployeeRef
  work_profile: { id: string; name: string } | null
  usage: UsageItem[]
  focus_sessions: FocusSession[]
}

export interface TeamProductivityRow {
  employee: EmployeeRef
  team: { id: string; name: string } | null
  work_profile: { id: string; name: string } | null
  metrics: ProductivityMetrics
  activity_score: number | null
  productive_share: number | null
  focus_score: number | null
  work_utilization: number | null
}

export interface TeamProductivity extends ProductivityBase {
  rows: TeamProductivityRow[]
}

export interface ProductivityTrendPoint {
  start: string
  end: string
  productive_share: number | null
  activity_score: number | null
  focus_score: number | null
  work_utilization: number | null
  work_seconds: number
  active_seconds: number
  productive_seconds: number
  classified_seconds: number
  focus_seconds: number
  task_seconds: number
  people: number
}

export interface ProductivityTrend {
  period: 'daily' | 'weekly' | 'monthly'
  timezone: string
  focus_available: boolean
  points: ProductivityTrendPoint[]
}

// --------------------------------------------------------------------------- Phase 9: projects & tasks

export type TaskStatus = 'TODO' | 'IN_PROGRESS' | 'BLOCKED' | 'IN_REVIEW' | 'COMPLETED'
export type TaskPriority = 'low' | 'medium' | 'high' | 'urgent'
export type ProjectColor = 'indigo' | 'blue' | 'teal' | 'green' | 'amber' | 'orange' | 'red' | 'pink' | 'violet' | 'slate'

export interface ProjectStats {
  total: number
  completed: number
  by_status: Record<TaskStatus, number>
  overdue: number
  time_spent_seconds: number
  progress: number
}

export interface Project {
  id: string
  name: string
  key: string
  description: string | null
  color: ProjectColor
  status: 'active' | 'archived'
  owner: EmployeeRef | null
  members: EmployeeRef[]
  due_date: string | null
  stats: ProjectStats
  created_at: string
  can_manage: boolean
  can_manage_tasks: boolean
}

export interface Task {
  id: string
  project_id: string
  project_key: string
  reference: string
  title: string
  description: string | null
  status: TaskStatus
  priority: TaskPriority
  assignees: EmployeeRef[]
  parent_id: string | null
  due_date: string | null
  start_date: string | null
  labels: string[]
  milestone_id: string | null
  overdue: boolean
  rank: number
  estimate_minutes: number | null
  completed_at: string | null
  created_at: string
  updated_at: string
  time_spent_seconds: number
  comment_count: number
  attachment_count: number
  subtask_total: number
  subtask_done: number
  timer_running: boolean
  can_edit: boolean
}

export interface Milestone {
  id: string
  project_id: string
  name: string
  description: string | null
  due_date: string | null
  closed: boolean
  closed_at: string | null
  total: number
  completed: number
  progress: number
  overdue: boolean
  can_manage: boolean
}

export interface LabelCount {
  name: string
  count: number
}

export interface TaskComment {
  id: string
  author: EmployeeRef | null
  body: string
  created_at: string
  edited_at: string | null
  can_edit: boolean
}

export interface TaskActivityItem {
  id: string
  kind: string
  actor: EmployeeRef | null
  data: Record<string, unknown>
  created_at: string
}

export interface TaskAttachment {
  id: string
  filename: string
  content_type: string
  size_bytes: number
  uploaded_by: EmployeeRef | null
  created_at: string
  download_url: string
  can_delete: boolean
}

export interface TimeEntry {
  id: string
  task_id: string
  employee: EmployeeRef | null
  started_at: string
  ended_at: string | null
  seconds: number
  source: 'timer' | 'manual'
  note: string | null
}

export interface TaskDetail extends Task {
  project_name: string
  subtasks: Task[]
  comments: TaskComment[]
  activity: TaskActivityItem[]
  attachments: TaskAttachment[]
  time_entries: TimeEntry[]
}

export interface TimerState {
  running: boolean
  task: Task | null
  started_at: string | null
  elapsed_seconds: number
  today_seconds: number
}

export interface MyWork {
  has_employee_record: boolean
  timer: TimerState
  current_task: Task | null
  today: Task[]
  overdue: Task[]
  upcoming: Task[]
  assigned: Task[]
  recently_completed: Task[]
  counts: Record<string, number>
}

export interface MemberWorkload {
  employee: EmployeeRef
  open_tasks: number
  in_progress: number
  blocked: number
  overdue: number
  completed_in_period: number
  time_spent_seconds: number
}

export interface WorkSummary {
  start: string
  end: string
  timezone: string
  completed: number
  created: number
  open: number
  overdue: number
  on_time_completed: number
  on_time_rate: number | null
  time_spent_seconds: number
  blocked: number
  members: MemberWorkload[]
  projects: Project[]
  blocked_tasks: Task[]
  overdue_tasks: Task[]
}

// --------------------------------------------------------------------------- Phase 13: reports

export type ReportType =
  | 'attendance'
  | 'work_hours'
  | 'activity'
  | 'applications'
  | 'websites'
  | 'screenshots'
  | 'projects'
  | 'tasks'
  | 'productivity'
  | 'live_sessions'
export type ReportFormat = 'csv' | 'xlsx' | 'pdf'
export type ReportPeriod = 'daily' | 'weekly' | 'monthly' | 'custom'
export type ReportStatus = 'queued' | 'preparing' | 'generating' | 'ready' | 'failed' | 'expired'
export type ReportFilterKey = 'employee' | 'department' | 'team' | 'role' | 'work_profile' | 'project'

export interface ReportTypeInfo {
  key: ReportType
  label: string
  description: string
  filters: ReportFilterKey[]
  allowed: boolean
  requires: string | null
}

export interface ReportFiltersInput {
  employee_ids?: string[]
  department_id?: string | null
  team_id?: string | null
  role?: Role | null
  work_profile_id?: string | null
  project_id?: string | null
}

export interface ReportRequestInput {
  report_type: ReportType
  format: ReportFormat
  period: ReportPeriod
  start: string
  end: string
  filters: ReportFiltersInput
}

export interface ReportPreview {
  title: string
  columns: { key: string; label: string; kind: string }[]
  rows: Record<string, string>[]
  total_rows: number
  people: number
  notes: string[]
}

export interface ReportJob {
  id: string
  report_type: ReportType
  label: string
  format: ReportFormat
  period: ReportPeriod
  start: string
  end: string
  status: ReportStatus
  progress: number
  row_count: number | null
  filename: string | null
  size_bytes: number | null
  error: string | null
  notes: string[]
  created_at: string
  finished_at: string | null
  expires_at: string | null
  download_url: string | null
}

// --------------------------------------------------------------------------- Phase 14: notifications

export type NotificationType =
  | 'employee_offline'
  | 'device_offline'
  | 'extended_idle'
  | 'shift_started'
  | 'shift_ended'
  | 'task_overdue'
  | 'project_deadline'
  | 'live_session_started'
  | 'live_session_ended'
  | 'screenshot_policy'
export type NotificationSeverity = 'info' | 'warning' | 'critical'

export interface AppNotification {
  id: string
  type: NotificationType
  severity: NotificationSeverity
  title: string
  body: string
  employee: { id: string; name: string } | null
  link: string | null
  count: number
  read: boolean
  created_at: string
  last_occurred_at: string
}

export interface NotificationPage {
  items: AppNotification[]
  total: number
  unread: number
  page: number
  page_size: number
}

export interface NotificationChannels {
  in_app: boolean
  email: boolean
}

export interface NotificationPreferences {
  throttle_minutes: number
  email_address: string
  channels: { key: string; label: string; available: boolean }[]
  types: {
    type: NotificationType
    label: string
    description: string
    audience: string
    severity: NotificationSeverity
    applies: boolean
    channels: NotificationChannels
  }[]
}
