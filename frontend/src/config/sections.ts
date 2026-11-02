import { useAuthStore } from '@/stores/auth-store'

/**
 * Dashboard sections an admin can show or hide per person (mirrors app/auth/sections.py on the backend).
 * A section hidden for a person is omitted from their navigation, routes and profile. It is a visibility
 * control only — role and scope still govern what the API returns.
 */
export interface SectionInfo {
  key: string
  label: string
  /** The person sees this about themselves when they have no workspace permission for it. */
  selfData: boolean
  /** One-line help shown in the access editor. */
  hint: string
}

export const SECTIONS: SectionInfo[] = [
  { key: 'activity', label: 'Activity', selfData: true, hint: 'Application and website usage.' },
  { key: 'productivity', label: 'Productivity', selfData: true, hint: 'Time by category, focus and insights.' },
  { key: 'screenshots', label: 'Screenshots', selfData: true, hint: 'Captured screenshots.' },
  { key: 'live', label: 'Live view', selfData: false, hint: 'On-demand live screen viewing.' },
  { key: 'reports', label: 'Reports', selfData: false, hint: 'Workforce reports and exports.' },
  { key: 'people', label: 'People', selfData: false, hint: 'Employee directory and org structure.' },
  { key: 'projects', label: 'Projects & tasks', selfData: false, hint: 'Projects, boards and tasks.' },
  { key: 'assistant', label: 'AI assistant', selfData: false, hint: 'Questions answered from WorkPulse records.' },
  { key: 'alerts', label: 'Alerts', selfData: false, hint: 'Realtime alerts and the notification center.' },
]

export const SECTION_KEYS: ReadonlySet<string> = new Set(SECTIONS.map((s) => s.key))

/** Hook: is a given section hidden for the signed-in user? Also returns the raw set for bulk checks. */
export function useHiddenSections() {
  const hidden = useAuthStore((s) => s.user?.hidden_sections ?? [])
  const set = new Set(hidden)
  return { hidden: set, isHidden: (key: string | undefined) => (key ? set.has(key) : false) }
}
