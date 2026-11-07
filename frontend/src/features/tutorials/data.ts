import type { ComponentType } from 'react'

import { DURATIONS as ACTIVITY_DURATIONS } from '@/features/tutorials/content/activity-durations'
import { DURATIONS as ACTIVITY_DETAILS_DURATIONS } from '@/features/tutorials/content/activity-details-durations'
import { DURATIONS as ADD_EMPLOYEES_DURATIONS } from '@/features/tutorials/content/add-employees-durations'
import { DURATIONS as ATTENDANCE_DURATIONS } from '@/features/tutorials/content/attendance-durations'
import { DURATIONS as CUSTOMER_SYSTEMS_DURATIONS } from '@/features/tutorials/content/customer-systems-durations'
import { DURATIONS as MONITORING_PRIVACY_DURATIONS } from '@/features/tutorials/content/monitoring-privacy-durations'
import { DURATIONS as REPORTS_DURATIONS } from '@/features/tutorials/content/reports-durations'
import { DURATIONS as ROLES_ACCESS_DURATIONS } from '@/features/tutorials/content/roles-access-durations'
import { DURATIONS as SCREENSHOTS_LIVE_DURATIONS } from '@/features/tutorials/content/screenshots-live-durations'
import { DURATIONS as WORKSPACE_SETUP_DURATIONS } from '@/features/tutorials/content/workspace-setup-durations'
import { DURATIONS as DASHBOARD_DURATIONS } from '@/features/tutorials/content/dashboard-durations'
import { DURATIONS as PRODUCTIVITY_RULES_DURATIONS } from '@/features/tutorials/content/productivity-rules-durations'
import { DURATIONS as INSTALL_AGENT_DURATIONS } from '@/features/tutorials/content/install-agent-durations'
import { DURATIONS as INTRODUCTION_DURATIONS } from '@/features/tutorials/content/introduction-durations'
import { ActivityScene, CAPTIONS as ACTIVITY_CAPTIONS } from '@/features/tutorials/scenes/activity-scene'
import { ActivityDetailsScene, CAPTIONS as ACTIVITY_DETAILS_CAPTIONS } from '@/features/tutorials/scenes/activity-details-scene'
import { AddEmployeesScene, CAPTIONS as ADD_EMPLOYEES_CAPTIONS } from '@/features/tutorials/scenes/add-employees-scene'
import { AttendanceScene, CAPTIONS as ATTENDANCE_CAPTIONS } from '@/features/tutorials/scenes/attendance-scene'
import { CAPTIONS as CUSTOMER_SYSTEMS_CAPTIONS, CustomerSystemsScene } from '@/features/tutorials/scenes/customer-systems-scene'
import { CAPTIONS as MONITORING_PRIVACY_CAPTIONS, MonitoringPrivacyScene } from '@/features/tutorials/scenes/monitoring-privacy-scene'
import { CAPTIONS as REPORTS_CAPTIONS, ReportsScene } from '@/features/tutorials/scenes/reports-scene'
import { CAPTIONS as ROLES_ACCESS_CAPTIONS, RolesAccessScene } from '@/features/tutorials/scenes/roles-access-scene'
import { CAPTIONS as SCREENSHOTS_LIVE_CAPTIONS, ScreenshotsLiveScene } from '@/features/tutorials/scenes/screenshots-live-scene'
import { CAPTIONS as WORKSPACE_SETUP_CAPTIONS, WorkspaceSetupScene } from '@/features/tutorials/scenes/workspace-setup-scene'
import { CAPTIONS as DASHBOARD_CAPTIONS, DashboardScene } from '@/features/tutorials/scenes/dashboard-scene'
import { CAPTIONS as PRODUCTIVITY_RULES_CAPTIONS, ProductivityRulesScene } from '@/features/tutorials/scenes/productivity-rules-scene'
import { CAPTIONS as INSTALL_AGENT_CAPTIONS, InstallAgentScene } from '@/features/tutorials/scenes/install-agent-scene'
import { CAPTIONS as INTRODUCTION_CAPTIONS, IntroductionScene } from '@/features/tutorials/scenes/introduction-scene'

export interface Tutorial {
  slug: string
  title: string
  description: string
  scene: ComponentType<{ step: number; t: number }>
  captions: string[]
  /** Seconds of voice-over per step (generated with the audio). */
  durations: number[]
}

/** Card colours by position: purple, blue, green, amber, rose, then again. */
export const CARD_GRADIENTS = [
  'from-[#5b3df5] to-[#8b5cf6]',
  'from-[#2563eb] to-[#38bdf8]',
  'from-[#059669] to-[#34d399]',
  'from-[#d97706] to-[#fbbf24]',
  'from-[#e11d48] to-[#fb7185]',
]

/** Voice-over parts live at /tutorials/<slug>/01.mp3, 02.mp3, … (see scripts/make-tutorial-audio.py). */
export const audioUrl = (slug: string, step: number) => `/tutorials/${slug}/${String(step + 1).padStart(2, '0')}.mp3`

/** In the order a new workspace needs them. */
export const TUTORIALS: Tutorial[] = [
  {
    slug: 'introduction',
    title: 'Introduction',
    description: 'What WorkPulse does, how it works, and a tour of the sections.',
    scene: IntroductionScene,
    captions: INTRODUCTION_CAPTIONS,
    durations: INTRODUCTION_DURATIONS,
  },
  {
    slug: 'add-employees',
    title: 'Add employees',
    description: 'Create departments, add employees and invite them to WorkPulse.',
    scene: AddEmployeesScene,
    captions: ADD_EMPLOYEES_CAPTIONS,
    durations: ADD_EMPLOYEES_DURATIONS,
  },
  {
    slug: 'install-agent',
    title: 'Install the desktop agent',
    description: 'Download, install, sign in and start a work session.',
    scene: InstallAgentScene,
    captions: INSTALL_AGENT_CAPTIONS,
    durations: INSTALL_AGENT_DURATIONS,
  },
  {
    slug: 'workspace-setup',
    title: 'Workspace setup',
    description: 'Time zone, working days, required hours and holidays.',
    scene: WorkspaceSetupScene,
    captions: WORKSPACE_SETUP_CAPTIONS,
    durations: WORKSPACE_SETUP_DURATIONS,
  },
  {
    slug: 'monitoring-privacy',
    title: 'Monitoring & privacy',
    description: 'Choose what is recorded, and show everyone exactly what that is.',
    scene: MonitoringPrivacyScene,
    captions: MONITORING_PRIVACY_CAPTIONS,
    durations: MONITORING_PRIVACY_DURATIONS,
  },
  {
    slug: 'dashboard',
    title: 'Dashboard',
    description: 'Read the cards, change the range, and customize the layout.',
    scene: DashboardScene,
    captions: DASHBOARD_CAPTIONS,
    durations: DASHBOARD_DURATIONS,
  },
  {
    slug: 'productivity-rules',
    title: 'Productivity rules',
    description: 'Decide what counts as productive, and how the productive share is calculated.',
    scene: ProductivityRulesScene,
    captions: PRODUCTIVITY_RULES_CAPTIONS,
    durations: PRODUCTIVITY_RULES_DURATIONS,
  },
  {
    slug: 'activity-details',
    title: 'Productivity & activity details',
    description: 'Breakdown by day, the details window, keyboard & mouse, window titles and export.',
    scene: ActivityDetailsScene,
    captions: ACTIVITY_DETAILS_CAPTIONS,
    durations: ACTIVITY_DETAILS_DURATIONS,
  },
  {
    slug: 'attendance',
    title: 'Time & Attendance',
    description: 'Logged time against the required hours: completed, short and absent days.',
    scene: AttendanceScene,
    captions: ATTENDANCE_CAPTIONS,
    durations: ATTENDANCE_DURATIONS,
  },
  {
    slug: 'screenshots-live',
    title: 'Screenshots & live view',
    description: 'The screenshot gallery, ZIP downloads, live view and the session log.',
    scene: ScreenshotsLiveScene,
    captions: SCREENSHOTS_LIVE_CAPTIONS,
    durations: SCREENSHOTS_LIVE_DURATIONS,
  },
  {
    slug: 'reports',
    title: 'Reports',
    description: 'Export workforce data as CSV, Excel or PDF in four steps.',
    scene: ReportsScene,
    captions: REPORTS_CAPTIONS,
    durations: REPORTS_DURATIONS,
  },
  {
    slug: 'roles-access',
    title: 'Roles & dashboard access',
    description: 'Who can do what, and which dashboard sections each person sees.',
    scene: RolesAccessScene,
    captions: ROLES_ACCESS_CAPTIONS,
    durations: ROLES_ACCESS_DURATIONS,
  },
  {
    slug: 'activity',
    title: 'Activity',
    description: 'Which applications and websites are used, and how actively.',
    scene: ActivityScene,
    captions: ACTIVITY_CAPTIONS,
    durations: ACTIVITY_DURATIONS,
  },
  {
    slug: 'customer-systems',
    title: 'Customer systems',
    description: 'Measure the time staff spend serving customers.',
    scene: CustomerSystemsScene,
    captions: CUSTOMER_SYSTEMS_CAPTIONS,
    durations: CUSTOMER_SYSTEMS_DURATIONS,
  },
]
