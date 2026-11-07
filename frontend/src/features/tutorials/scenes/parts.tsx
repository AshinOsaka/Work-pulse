import type { ReactNode } from 'react'
import {
  Activity,
  BellRing,
  ChevronDown,
  Clock,
  FileChartColumn,
  FolderKanban,
  Gauge,
  LayoutDashboard,
  MonitorPlay,
  Settings,
  ShieldCheck,
  Users,
  type LucideIcon,
} from 'lucide-react'

import { Logo } from '@/components/common/logo'
import { cn } from '@/lib/utils'

/**
 * Shared building blocks for tutorial scenes: a simplified WorkPulse frame, the animated cursor, form fields and
 * timing helpers. Scenes are 960 × 540 design pixels and derive everything from (step, t). Decorative only.
 */

export type Point = { x: number; y: number }

export const clamp01 = (v: number) => Math.max(0, Math.min(1, v))
/** 0 → 1 between `from` and `from + span` seconds. */
export const ramp = (t: number, from: number, span = 0.6) => clamp01((t - from) / span)
/** True for a moment just after `at` seconds: drives the click ripple. */
export const clickAt = (t: number, at: number) => t >= at && t < at + 0.35
/** Characters of `text` typed so far, typing from `from` to `to` seconds. */
export function typed(text: string, t: number, from: number, to: number): string {
  if (t <= from) return ''
  if (t >= to) return text
  return text.slice(0, Math.ceil((text.length * (t - from)) / (to - from)))
}
/** Fade-and-rise style for something appearing at `from` seconds. */
export const rise = (t: number, from: number) => ({ opacity: ramp(t, from), transform: `translateY(${(1 - ramp(t, from)) * 12}px)` })

const NAV: { section: string; items: { label: string; icon: LucideIcon }[] }[] = [
  { section: 'Overview', items: [{ label: 'Dashboard', icon: LayoutDashboard }] },
  {
    section: 'Workforce',
    items: [
      { label: 'People', icon: Users },
      { label: 'Live Tracking', icon: MonitorPlay },
      { label: 'Activity', icon: Activity },
      { label: 'Time & Attendance', icon: Clock },
    ],
  },
  { section: 'Work', items: [{ label: 'Projects & Tasks', icon: FolderKanban }, { label: 'Productivity', icon: Gauge }] },
  { section: 'Operations', items: [{ label: 'Alerts', icon: BellRing }, { label: 'Reports', icon: FileChartColumn }] },
  { section: 'Administration', items: [{ label: 'Settings', icon: Settings }, { label: 'Security', icon: ShieldCheck }] },
]

/** Design-pixel centre of a sidebar item in `Shell` (for pointing the cursor at it). */
export function navPoint(label: string): Point {
  let y = 58
  for (const group of NAV) {
    y += 17
    for (const item of group.items) {
      if (item.label === label) return { x: 70, y: y + 11 }
      y += 24
    }
    y += 6
  }
  return { x: 70, y: 60 }
}

/** The app frame: sidebar (with `active` lit), top bar, and the page. Content area starts at x 200, y 44. */
export function Shell({ active, topRight, children }: { active: string; topRight?: ReactNode; children: ReactNode }) {
  return (
    <div className="flex h-full">
      <aside className="w-[200px] shrink-0 border-r bg-sidebar px-3 pt-3">
        <div className="mb-3 h-[34px] px-1">
          <Logo />
        </div>
        {NAV.map((group) => (
          <div key={group.section} className="mb-1.5">
            <p className="h-[17px] px-2 pt-1 text-[9px] font-semibold tracking-wide text-muted-foreground uppercase">{group.section}</p>
            {group.items.map((item) => (
              <p
                key={item.label}
                className={cn(
                  'flex h-[24px] items-center gap-2 rounded-md px-2 text-[11.5px] font-medium transition-colors duration-300',
                  item.label === active ? 'bg-primary/10 text-primary' : 'text-muted-foreground',
                )}
              >
                <item.icon className="size-3.5" />
                {item.label}
              </p>
            ))}
          </div>
        ))}
      </aside>
      <div className="flex min-w-0 flex-1 flex-col">
        <div className="flex h-11 shrink-0 items-center justify-between border-b px-5">
          <div className="h-6 w-52 rounded-md border bg-card" />
          <div className="flex items-center gap-3">
            {topRight}
            <div className="size-7 rounded-full bg-gradient-to-br from-violet-500 to-sky-500" />
          </div>
        </div>
        <div className="relative min-h-0 flex-1 p-5">{children}</div>
      </div>
    </div>
  )
}

/** Page tabs like the app's LinkTabs; `active` is underlined. */
export function Tabs({ tabs, active, pulse }: { tabs: string[]; active: string; pulse?: string }) {
  return (
    <div className="flex gap-5 border-b text-[12px]">
      {tabs.map((tab) => (
        <span
          key={tab}
          className={cn(
            '-mb-px border-b-2 pb-2 transition-colors duration-300',
            tab === active ? 'border-primary font-medium text-foreground' : 'border-transparent text-muted-foreground',
            tab === pulse && tab !== active && 'text-primary',
          )}
        >
          {tab}
        </span>
      ))}
    </div>
  )
}

export function Field({
  label,
  value,
  placeholder,
  focused,
  select,
  className,
}: {
  label?: string
  value: string
  placeholder?: string
  focused?: boolean
  select?: boolean
  className?: string
}) {
  return (
    <div className={className}>
      {label && <p className="mb-1 text-[11px] font-medium">{label}</p>}
      <div
        className={cn(
          'flex h-8 items-center justify-between rounded-md border bg-card px-2.5 text-[12px] transition-shadow duration-300',
          focused && 'border-primary ring-[3px] ring-primary/25',
        )}
      >
        <span className={cn('truncate', !value && 'text-muted-foreground')}>
          {value || placeholder}
          {focused && !select && <span className="ml-px inline-block h-3.5 w-px translate-y-0.5 animate-pulse bg-foreground" />}
        </span>
        {select && <ChevronDown className="size-3.5 shrink-0 opacity-60" />}
      </div>
    </div>
  )
}

export function Btn({ children, primary, focused, className }: { children: ReactNode; primary?: boolean; focused?: boolean; className?: string }) {
  return (
    <span
      className={cn(
        'inline-flex h-8 items-center gap-1.5 rounded-md border px-3 text-[12px] font-medium whitespace-nowrap transition-shadow duration-300',
        primary && 'border-primary bg-primary text-primary-foreground',
        focused && 'ring-[3px] ring-primary/35',
        className,
      )}
    >
      {children}
    </span>
  )
}

/** A small dropdown list opened under a field. */
export function Menu({ items, active, style }: { items: string[]; active: string; style: React.CSSProperties }) {
  return (
    <div className="absolute z-10 w-40 rounded-lg border bg-popover p-1 text-[12px] shadow-lg duration-200 animate-in fade-in-0 zoom-in-95" style={style}>
      {items.map((item) => (
        <div key={item} className={cn('rounded px-2 py-1.5', item === active && 'bg-accent font-medium')}>
          {item}
        </div>
      ))}
    </div>
  )
}

export function Toast({ title, text }: { title: string; text?: string }) {
  return (
    <div className="absolute right-5 bottom-5 z-30 w-72 rounded-lg border bg-popover px-3.5 py-2.5 text-[12px] shadow-lg duration-300 animate-in fade-in-0 slide-in-from-bottom-2">
      <p className="font-medium">{title}</p>
      {text && <p className="mt-0.5 text-muted-foreground">{text}</p>}
    </div>
  )
}

/** The mouse pointer, gliding between points; `click` shows a ripple. */
export function Cursor({ at, click }: { at: Point; click?: boolean }) {
  return (
    <div className="pointer-events-none absolute z-40 transition-[left,top] duration-700 ease-[cubic-bezier(.22,1,.36,1)]" style={{ left: at.x, top: at.y }}>
      {click && <span className="absolute -top-4 -left-4 size-8 animate-ping rounded-full bg-primary/40" />}
      <svg width="22" height="22" viewBox="0 0 24 24" className="drop-shadow-md">
        <path d="M4 2l16 9.5-7 1.6-3.6 6.9z" fill="white" stroke="black" strokeWidth="1.4" strokeLinejoin="round" />
      </svg>
    </div>
  )
}

/** Full-scene title card used for the first and last step. */
export function TitleCard({ icon: Icon, title, text }: { icon: LucideIcon; title: string; text: string }) {
  return (
    <div className="absolute inset-0 z-30 flex items-center justify-center bg-background/75 backdrop-blur-sm duration-700 animate-in fade-in-0">
      <div className="flex flex-col items-center gap-4 text-center duration-700 animate-in zoom-in-95">
        <span className="flex size-16 items-center justify-center rounded-2xl bg-[linear-gradient(135deg,#7c3aed,#6366f1)] text-white shadow-[0_10px_30px_-8px_rgba(124,58,237,0.8)]">
          <Icon className="size-8" />
        </span>
        <p className="text-[32px] font-semibold tracking-tight">{title}</p>
        <p className="max-w-md text-[15px] text-muted-foreground">{text}</p>
      </div>
    </div>
  )
}
