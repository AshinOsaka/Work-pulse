import type { StatusTone } from '@/components/common/status'
import type { AccessState, DeviceOs, DeviceStatus, EmployeeStatus, EmploymentType, Permission } from '@/types/api'

export const EMPLOYEE_STATUS: Record<EmployeeStatus, { label: string; tone: StatusTone }> = {
  active: { label: 'Active', tone: 'success' },
  on_leave: { label: 'On leave', tone: 'warning' },
  terminated: { label: 'Terminated', tone: 'neutral' },
}

export const ACCESS_STATE: Record<AccessState, { label: string; description: string }> = {
  none: { label: 'No account', description: 'This employee has not been invited to WorkPulse.' },
  invited: { label: 'Invited', description: 'An invitation has been sent and is awaiting acceptance.' },
  active: { label: 'Active', description: 'This employee can sign in to WorkPulse.' },
  suspended: { label: 'Suspended', description: 'Sign-in is temporarily blocked.' },
  deactivated: { label: 'Deactivated', description: 'Access was removed when the employee was terminated.' },
}

export const EMPLOYMENT_TYPES: Record<EmploymentType, string> = {
  full_time: 'Full-time',
  part_time: 'Part-time',
  contractor: 'Contractor',
}

export const DEVICE_OS: Record<DeviceOs, string> = { windows: 'Windows', macos: 'macOS', linux: 'Linux' }

export const DEVICE_STATUS: Record<DeviceStatus, { label: string; tone: StatusTone }> = {
  pending: { label: 'Awaiting enrolment', tone: 'warning' },
  active: { label: 'Active', tone: 'success' },
  inactive: { label: 'Inactive', tone: 'neutral' },
  revoked: { label: 'Revoked', tone: 'danger' },
}

/** Mirrors the backend permission catalogue (app/auth/permissions.py). */
export const PERMISSION_INFO: Record<Permission, { name: string; category: string }> = {
  EMPLOYEE_VIEW: { name: 'View employees', category: 'People' },
  EMPLOYEE_MANAGE: { name: 'Manage employees', category: 'People' },
  LIVE_STREAM_VIEW: { name: 'View live screens', category: 'Monitoring' },
  SCREENSHOT_VIEW: { name: 'View screenshots', category: 'Monitoring' },
  ACTIVITY_VIEW: { name: 'View activity', category: 'Monitoring' },
  REPORT_VIEW: { name: 'View reports', category: 'Reporting' },
  REPORT_EXPORT: { name: 'Export reports', category: 'Reporting' },
  TASK_MANAGE: { name: 'Manage tasks', category: 'Work' },
  PROJECT_MANAGE: { name: 'Manage projects', category: 'Work' },
  POLICY_MANAGE: { name: 'Manage policies', category: 'Administration' },
  USER_MANAGE: { name: 'Manage users', category: 'Administration' },
  AUDIT_LOG_VIEW: { name: 'View audit log', category: 'Administration' },
}
