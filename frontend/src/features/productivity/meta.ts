import { shiftDay, todayIn } from '@/features/activity/format'
import type { ProductivityMetrics, RuleScope, ScoreKey, UsageCategory } from '@/types/api'

export const CATEGORY_ORDER: UsageCategory[] = ['productive', 'neutral', 'unproductive', 'unclassified']

export const CATEGORY: Record<UsageCategory, { label: string; color: string; swatch: string; metric: keyof ProductivityMetrics }> = {
  productive: { label: 'Productive', color: 'var(--cat-productive)', swatch: 'bg-cat-productive', metric: 'productive_seconds' },
  neutral: { label: 'Neutral', color: 'var(--cat-neutral)', swatch: 'bg-cat-neutral', metric: 'neutral_seconds' },
  unproductive: { label: 'Unproductive', color: 'var(--cat-unproductive)', swatch: 'bg-cat-unproductive', metric: 'unproductive_seconds' },
  unclassified: { label: 'Unclassified', color: 'var(--cat-unclassified)', swatch: 'bg-unclassified', metric: 'unclassified_seconds' },
}

export const SCOPE_LABEL: Record<RuleScope, string> = {
  company: 'Whole company',
  role: 'Role',
  department: 'Department',
  team: 'Team',
  profile: 'Work profile',
}

export type RangeKey = 'today' | '7d' | '14d' | '30d'

export const RANGES: { value: RangeKey; label: string }[] = [
  { value: 'today', label: 'Today' },
  { value: '7d', label: '7 days' },
  { value: '14d', label: '14 days' },
  { value: '30d', label: '30 days' },
]

export function rangeFor(key: RangeKey, timeZone: string): { start: string; end: string } {
  const today = todayIn(timeZone)
  const days = { today: 0, '7d': 6, '14d': 13, '30d': 29 }[key]
  return { start: shiftDay(today, -days), end: today }
}

export function share(part: number, whole: number): number {
  return whole > 0 ? Math.round((100 * part) / whole) : 0
}

/** Score order everywhere: input-based first, then the context-based scores. */
export const SCORE_ORDER: ScoreKey[] = ['activity_score', 'productive_share', 'focus_score', 'work_utilization']

export const SCORE_HINT: Record<ScoreKey, string> = {
  activity_score: 'Active ÷ work time. Input only, not productivity.',
  productive_share: 'Productive ÷ classified app and website time.',
  focus_score: 'Focus-session time ÷ productive time.',
  work_utilization: 'Time logged on tasks ÷ work time.',
}

/** Plain names for metric keys, used wherever a figure says what it is based on. */
export const METRIC_LABEL: Record<string, string> = {
  work_seconds: 'work time',
  active_seconds: 'active time',
  idle_seconds: 'idle time',
  extended_idle_seconds: 'extended idle',
  tracked_seconds: 'tracked time',
  productive_seconds: 'productive time',
  neutral_seconds: 'neutral',
  unproductive_seconds: 'unproductive',
  unclassified_seconds: 'unclassified',
  focus_sessions: 'focus sessions',
  focus_seconds: 'focus time',
  longest_focus_seconds: 'longest focus',
  context_switches: 'app switches',
  task_seconds: 'task time',
  tasks_completed: 'tasks completed',
  tasks_due_open: 'open tasks that were due',
}
