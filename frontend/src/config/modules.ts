import {
  Activity,
  BellRing,
  Camera,
  Clock,
  FileChartColumn,
  FolderKanban,
  Gauge,
  LayoutDashboard,
  MonitorPlay,
  Settings,
  ShieldCheck,
  Sparkles,
  Users,
  type LucideIcon,
} from 'lucide-react'

import type { Permission } from '@/types/api'

/**
 * The module registry drives the sidebar, command menu, routing and the
 * "coming soon" pages. A module is `available` only when it is genuinely
 * implemented; everything else is honestly marked with its delivery phase.
 */
export type ModuleStatus = 'available' | 'upcoming'

export interface AppModule {
  key: string
  label: string
  path: string
  icon: LucideIcon
  section: NavSection
  status: ModuleStatus
  /** Delivery phase for upcoming modules. */
  phase?: number
  /** Required to see the module. Omit for modules every member can open. */
  permission?: Permission
  description: string
  planned?: string[]
  dependsOn?: string
  /** Sub-items shown nested under this item in the sidebar (e.g. Live Tracking → Screenshot, Live Stream). */
  children?: AppModule[]
}

export type NavSection = 'Overview' | 'Workforce' | 'Work' | 'Operations' | 'Administration'

export const NAV_SECTIONS: NavSection[] = ['Overview', 'Workforce', 'Work', 'Operations', 'Administration']

export const PHASES: Record<number, string> = {
  1: 'Foundation',
  2: 'People & organisation',
  3: 'Manager dashboard',
  4: 'Windows desktop agent',
  5: 'Activity tracking',
  6: 'Screenshot monitoring',
  7: 'Live screen viewing',
  8: 'Productivity intelligence',
  9: 'Projects & tasks',
  10: 'Attendance, alerts & reports',
}

export const MODULES: AppModule[] = [
  {
    key: 'dashboard',
    label: 'Dashboard',
    path: '/dashboard',
    icon: LayoutDashboard,
    section: 'Overview',
    status: 'available',
    description: 'Workspace overview, setup progress and system status.',
  },
  {
    key: 'people',
    label: 'People',
    path: '/people',
    icon: Users,
    section: 'Workforce',
    status: 'available',
    permission: 'EMPLOYEE_VIEW',
    description: 'Employee directory, departments, teams and reporting lines.',
  },
  {
    key: 'live-tracking',
    label: 'Live Tracking',
    path: '/screenshots',
    icon: MonitorPlay,
    section: 'Workforce',
    status: 'available',
    description: 'Screenshots and on-demand live screen viewing.',
    children: [
      {
        key: 'screenshots',
        label: 'Screenshot',
        path: '/screenshots',
        icon: Camera,
        section: 'Workforce',
        status: 'available',
        permission: 'SCREENSHOT_VIEW',
        description: 'Policy-driven screenshots, private and audited.',
      },
      {
        key: 'live',
        label: 'Live Stream',
        path: '/live',
        icon: MonitorPlay,
        section: 'Workforce',
        status: 'available',
        permission: 'LIVE_STREAM_VIEW',
        description: 'Online employees and on-demand live screen viewing.',
      },
    ],
  },
  {
    key: 'activity',
    label: 'Activity',
    path: '/activity',
    icon: Activity,
    section: 'Workforce',
    status: 'available',
    permission: 'ACTIVITY_VIEW',
    description: 'Application usage and active time, recorded by the desktop agent.',
  },
  {
    key: 'attendance',
    label: 'Time & Attendance',
    path: '/attendance',
    icon: Clock,
    section: 'Workforce',
    status: 'upcoming',
    phase: 10,
    description: 'Automatic timesheets, shifts and attendance records.',
    planned: ['Automatic clock-in from agent activity', 'Shifts, breaks and overtime', 'Timesheet approval workflow'],
  },
  {
    key: 'projects',
    label: 'Projects & Tasks',
    path: '/projects',
    icon: FolderKanban,
    section: 'Work',
    status: 'available',
    description: 'Projects, boards, tasks, timers and time spent.',
  },
  {
    key: 'productivity',
    label: 'Productivity',
    path: '/productivity',
    icon: Gauge,
    section: 'Work',
    status: 'available',
    permission: 'ACTIVITY_VIEW',
    description: 'Time by category under configurable rules, focus sessions and insights.',
  },
  {
    key: 'assistant',
    label: 'AI Assistant',
    path: '/assistant',
    icon: Sparkles,
    section: 'Work',
    status: 'available',
    permission: 'REPORT_VIEW',
    description: 'Ask questions about attendance, activity, projects and tasks — answered only from WorkPulse records.',
  },
  {
    key: 'alerts',
    label: 'Alerts',
    path: '/alerts',
    icon: BellRing,
    section: 'Operations',
    status: 'available',
    description: 'Realtime alerts and the notification center, with per-person preferences.',
  },
  {
    key: 'reports',
    label: 'Reports',
    path: '/reports',
    icon: FileChartColumn,
    section: 'Operations',
    status: 'available',
    permission: 'REPORT_VIEW',
    description: 'On-demand workforce reports as CSV, Excel or PDF.',
  },
  {
    key: 'settings',
    label: 'Settings',
    path: '/settings',
    icon: Settings,
    section: 'Administration',
    status: 'available',
    description: 'Profile, workspace and appearance settings.',
  },
  {
    key: 'security',
    label: 'Security',
    path: '/security',
    icon: ShieldCheck,
    section: 'Administration',
    status: 'available',
    description: 'Password, roles & permissions and access controls.',
  },
]

export function getModule(key: string): AppModule {
  const module = MODULES.find((m) => m.key === key)
  if (!module) throw new Error(`Unknown module: ${key}`)
  return module
}

/** All modules flattened to leaves: a parent with children is replaced by its children. */
export function leafModules(modules: AppModule[]): AppModule[] {
  return modules.flatMap((m) => (m.children?.length ? m.children : [m]))
}

export function findModuleByPath(pathname: string): AppModule | undefined {
  const matches = (m: AppModule) => pathname === m.path || pathname.startsWith(`${m.path}/`)
  const all = leafModules(MODULES)
  return all.find(matches) ?? MODULES.find(matches)
}
