import { ArrowDown, ArrowUp, ChevronsUp, Minus, type LucideIcon } from 'lucide-react'

import type { ProjectColor, TaskPriority, TaskStatus } from '@/types/api'

export const STATUSES: TaskStatus[] = ['TODO', 'IN_PROGRESS', 'BLOCKED', 'IN_REVIEW', 'COMPLETED']

/** Status is identity + state: always shown with its label (and a dot), never colour alone. */
export const STATUS: Record<TaskStatus, { label: string; dot: string; badge: string }> = {
  TODO: { label: 'To do', dot: 'bg-muted-foreground/60', badge: 'bg-muted text-muted-foreground' },
  IN_PROGRESS: { label: 'In progress', dot: 'bg-info', badge: 'bg-info-soft text-info' },
  BLOCKED: { label: 'Blocked', dot: 'bg-destructive', badge: 'bg-destructive-soft text-destructive' },
  IN_REVIEW: { label: 'In review', dot: 'bg-warning', badge: 'bg-warning-soft text-warning' },
  COMPLETED: { label: 'Completed', dot: 'bg-success', badge: 'bg-success-soft text-success' },
}

export const PRIORITIES: TaskPriority[] = ['urgent', 'high', 'medium', 'low']

export const PRIORITY: Record<TaskPriority, { label: string; icon: LucideIcon; className: string }> = {
  urgent: { label: 'Urgent', icon: ChevronsUp, className: 'text-destructive' },
  high: { label: 'High', icon: ArrowUp, className: 'text-warning' },
  medium: { label: 'Medium', icon: Minus, className: 'text-muted-foreground' },
  low: { label: 'Low', icon: ArrowDown, className: 'text-muted-foreground' },
}

export const PROJECT_COLORS: ProjectColor[] = ['indigo', 'blue', 'teal', 'green', 'amber', 'orange', 'red', 'pink', 'violet', 'slate']

/** Decorative project accent (always paired with the project's name and key). */
export const PROJECT_COLOR: Record<ProjectColor, string> = {
  indigo: 'bg-indigo-500',
  blue: 'bg-blue-500',
  teal: 'bg-teal-500',
  green: 'bg-green-600',
  amber: 'bg-amber-500',
  orange: 'bg-orange-500',
  red: 'bg-red-500',
  pink: 'bg-pink-500',
  violet: 'bg-violet-500',
  slate: 'bg-slate-500',
}

/**
 * Label tones: a stable colour per label name, always shown with the label text (never colour alone).
 * Muted, low-chroma backgrounds so labels never compete with status or priority.
 */
const LABEL_TONES = [
  'bg-sky-100 text-sky-900 dark:bg-sky-950 dark:text-sky-200',
  'bg-violet-100 text-violet-900 dark:bg-violet-950 dark:text-violet-200',
  'bg-emerald-100 text-emerald-900 dark:bg-emerald-950 dark:text-emerald-200',
  'bg-amber-100 text-amber-900 dark:bg-amber-950 dark:text-amber-200',
  'bg-rose-100 text-rose-900 dark:bg-rose-950 dark:text-rose-200',
  'bg-teal-100 text-teal-900 dark:bg-teal-950 dark:text-teal-200',
  'bg-fuchsia-100 text-fuchsia-900 dark:bg-fuchsia-950 dark:text-fuchsia-200',
  'bg-slate-200 text-slate-900 dark:bg-slate-800 dark:text-slate-200',
]

export function labelTone(label: string): string {
  let hash = 0
  for (const ch of label) hash = (hash * 31 + ch.charCodeAt(0)) >>> 0
  return LABEL_TONES[hash % LABEL_TONES.length]
}

export const MAX_LABELS = 10

/** Mirrors the server's normalisation, so chips show what will be saved. */
export function normalizeLabel(raw: string): string {
  return raw.replace(/\s+/g, ' ').trim().toLowerCase().slice(0, 30)
}

export function formatDue(value: string): string {
  return new Date(`${value}T00:00:00Z`).toLocaleDateString(undefined, { timeZone: 'UTC', day: 'numeric', month: 'short' })
}

/** Elapsed timer as h:mm:ss. */
export function clock(seconds: number): string {
  const s = Math.max(0, Math.floor(seconds))
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  return `${h}:${String(m).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`
}
