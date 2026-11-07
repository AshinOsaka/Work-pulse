import {
  Activity,
  AppWindow,
  BellRing,
  CalendarRange,
  Check,
  Clock,
  Cloud,
  FileChartColumn,
  FolderKanban,
  Gauge,
  Globe,
  CircleHelp,
  LayoutDashboard,
  Laptop,
  Monitor,
  MonitorPlay,
  Settings,
  ShieldCheck,
  SlidersHorizontal,
  Users,
  X,
} from 'lucide-react'

import { Logo } from '@/components/common/logo'
import { cn } from '@/lib/utils'

/**
 * The "Introduction" tutorial, drawn as simplified WorkPulse screens (960 × 540 design pixels, scaled by the
 * player). Everything is derived from (step, t) so the scene can be paused, sought and replayed. Decorative only.
 */

export const CAPTIONS = [
  'Welcome to WorkPulse: attendance, applications, websites and productivity in one clear view.',
  'Three parts: the desktop agent on each Windows computer sends activity to WorkPulse, and you see it in your browser.',
  'Open and consent-based: each employee reviews what may be recorded and accepts every item. A tray icon shows WorkPulse is running.',
  'WorkPulse records times and counts, never content: never typed text, passwords or private browsing windows.',
  'The sidebar is grouped into sections. Overview holds the Dashboard, your home page.',
  'Workforce: People, Live Tracking (screenshots and live view), Activity, and Time & Attendance.',
  'Work: Projects & Tasks and Productivity. Operations: Alerts and Reports.',
  'Administration: Settings (workspace, monitoring, customer systems) and Security. Help, with these tutorials, is in your profile menu.',
  'On the Dashboard, choose a date range and use Customize to add, hide or move cards.',
  'To get started: add employees, install the desktop agent, and set your work schedule.',
]

const SECTIONS: { name: string; items: { label: string; icon: typeof Users }[] }[] = [
  { name: 'Overview', items: [{ label: 'Dashboard', icon: LayoutDashboard }] },
  {
    name: 'Workforce',
    items: [
      { label: 'People', icon: Users },
      { label: 'Live Tracking', icon: MonitorPlay },
      { label: 'Activity', icon: Activity },
      { label: 'Time & Attendance', icon: Clock },
    ],
  },
  {
    name: 'Work',
    items: [
      { label: 'Projects & Tasks', icon: FolderKanban },
      { label: 'Productivity', icon: Gauge },
    ],
  },
  {
    name: 'Operations',
    items: [
      { label: 'Alerts', icon: BellRing },
      { label: 'Reports', icon: FileChartColumn },
    ],
  },
  {
    name: 'Administration',
    items: [
      { label: 'Settings', icon: Settings },
      { label: 'Security', icon: ShieldCheck },
    ],
  },
]

/** Which sidebar sections are highlighted on each sidebar step. */
const HIGHLIGHT: Record<number, string[]> = {
  4: ['Overview'],
  5: ['Workforce'],
  6: ['Work', 'Operations'],
  7: ['Administration'],
  8: ['Overview'],
}

const clamp01 = (v: number) => Math.max(0, Math.min(1, v))
/** 0 → 1 between `from` and `from + span` seconds. */
const ramp = (t: number, from: number, span = 0.6) => clamp01((t - from) / span)

export function IntroductionScene({ step, t }: { step: number; t: number }) {
  return (
    <div className="relative h-[540px] w-[960px] overflow-hidden bg-background text-foreground select-none">
      {step === 0 && <TitleCard t={t} />}
      {step === 1 && <ThreeParts t={t} />}
      {step === 2 && <Consent t={t} />}
      {step === 3 && <NeverContent t={t} />}
      {step >= 4 && step <= 8 && <AppShell step={step} t={t} />}
      {step === 9 && <GetStarted t={t} />}
    </div>
  )
}

function TitleCard({ t }: { t: number }) {
  const tiles = [
    { icon: Clock, label: 'Attendance' },
    { icon: AppWindow, label: 'Applications' },
    { icon: Globe, label: 'Websites' },
    { icon: Gauge, label: 'Productivity' },
  ]
  return (
    <div className="flex h-full flex-col items-center justify-center gap-6 bg-[radial-gradient(ellipse_at_top,rgba(124,58,237,0.16),transparent_60%)]">
      <div className="scale-[2.2] duration-700 animate-in fade-in-0 zoom-in-90">
        <Logo />
      </div>
      <p className="mt-6 text-[17px] text-muted-foreground duration-700 animate-in fade-in-0">How your team spends its working time, in one clear view.</p>
      <div className="mt-2 flex gap-4">
        {tiles.map((tile, i) => (
          <div
            key={tile.label}
            className="flex w-36 flex-col items-center gap-2 rounded-xl border bg-card px-4 py-4 shadow-sm transition-all duration-500"
            style={{ opacity: ramp(t, 1.2 + i * 0.5), transform: `translateY(${(1 - ramp(t, 1.2 + i * 0.5)) * 14}px)` }}
          >
            <span className="flex size-10 items-center justify-center rounded-lg bg-primary/10 text-primary">
              <tile.icon className="size-5" />
            </span>
            <span className="text-[13px] font-medium">{tile.label}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

function ThreeParts({ t }: { t: number }) {
  const parts = [
    { icon: Laptop, title: 'Desktop agent', text: "On each employee's Windows computer" },
    { icon: Cloud, title: 'WorkPulse', text: 'Receives and summarises activity' },
    { icon: Monitor, title: 'Your browser', text: 'Dashboards, reports and settings' },
  ]
  const at = [0.6, 3.4, 6.2]
  return (
    <div className="flex h-full flex-col items-center justify-center gap-10">
      <p className="text-[24px] font-semibold tracking-tight">How WorkPulse works</p>
      <div className="relative flex items-start gap-24">
        {/* Links with travelling dots */}
        {[0, 1].map((i) => (
          <div key={i} className="absolute top-12 h-0.5 w-24 bg-border" style={{ left: 176 + i * 296, opacity: ramp(t, at[i + 1] - 0.6) }}>
            {t > at[i + 1] && (
              <span className="absolute -top-1 size-2.5 rounded-full bg-primary shadow-[0_0_10px_var(--primary)]" style={{ left: `${((t * 45) % 100).toFixed(1)}%` }} />
            )}
          </div>
        ))}
        {parts.map((p, i) => (
          <div
            key={p.title}
            className="flex w-44 flex-col items-center gap-3 text-center"
            style={{ opacity: ramp(t, at[i]), transform: `scale(${0.9 + 0.1 * ramp(t, at[i])})` }}
          >
            <span className="flex size-24 items-center justify-center rounded-3xl border bg-card text-primary shadow-md">
              <p.icon className="size-11" />
            </span>
            <span className="text-[16px] font-semibold">{p.title}</span>
            <span className="text-[13px] text-muted-foreground">{p.text}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

function Consent({ t }: { t: number }) {
  const items = ['Work time', 'Applications', 'Websites', 'Screenshots', 'Live view', 'Keyboard & mouse']
  return (
    <div className="flex h-full items-center justify-center gap-10 bg-subtle/40">
      <div className="w-[420px] rounded-xl border bg-card shadow-xl duration-500 animate-in fade-in-0 zoom-in-95">
        <div className="flex items-center gap-2 border-b px-4 py-3">
          <ShieldCheck className="size-4 text-primary" />
          <span className="text-[14px] font-semibold">WorkPulse Agent · Permissions &amp; consent</span>
        </div>
        <p className="px-4 pt-3 text-[12px] text-muted-foreground">Review what WorkPulse may collect while you work and confirm each item.</p>
        <ul className="space-y-1.5 p-4">
          {items.map((item, i) => {
            const on = t >= 2.2 + i * 0.7
            return (
              <li key={item} className="flex items-center gap-2.5 rounded-md border px-3 py-2 text-[13px]">
                <span className={cn('flex size-4 items-center justify-center rounded border transition-colors duration-200', on && 'border-primary bg-primary text-primary-foreground')}>
                  {on && <Check className="size-3" />}
                </span>
                {item}
              </li>
            )
          })}
        </ul>
        <div className="flex justify-end border-t px-4 py-3">
          <span className={cn('rounded-md px-3 py-1.5 text-[12px] font-medium transition-colors duration-300', t >= 6.6 ? 'bg-primary text-primary-foreground' : 'bg-muted text-muted-foreground')}>
            I agree, continue
          </span>
        </div>
      </div>
      {/* Windows taskbar with the tray icon */}
      <div className="flex flex-col items-center gap-3" style={{ opacity: ramp(t, 7.6) }}>
        <div className="flex items-center gap-3 rounded-xl border bg-card px-4 py-3 shadow-md">
          <span className="text-[12px] text-muted-foreground">Taskbar</span>
          <span className="relative flex size-9 items-center justify-center rounded-lg bg-[linear-gradient(135deg,#7c3aed,#6366f1)] text-white">
            <Activity className="size-5" />
            {t > 8.2 && <span className="absolute -inset-1 animate-ping rounded-xl border-2 border-primary" />}
          </span>
          <span className="text-[12px] tabular text-muted-foreground">9:30</span>
        </div>
        <span className="text-[13px] font-medium">Tray icon: WorkPulse is running</span>
      </div>
    </div>
  )
}

function NeverContent({ t }: { t: number }) {
  const yes = ['Work and idle time', 'Which apps and websites', 'Keyboard & mouse counts']
  const no = ['What is typed', 'Passwords', 'Private browsing windows']
  return (
    <div className="flex h-full items-center justify-center gap-8">
      <List title="Recorded" tone="yes" items={yes} t={t} start={0.4} />
      <List title="Never recorded" tone="no" items={no} t={t} start={2.6} />
    </div>
  )
}

function List({ title, tone, items, t, start }: { title: string; tone: 'yes' | 'no'; items: string[]; t: number; start: number }) {
  return (
    <div className="w-80 rounded-xl border bg-card p-5 shadow-md" style={{ opacity: ramp(t, start) }}>
      <p className={cn('mb-4 text-[16px] font-semibold', tone === 'yes' ? 'text-cat-productive' : 'text-destructive')}>{title}</p>
      <ul className="space-y-3">
        {items.map((item, i) => (
          <li key={item} className="flex items-center gap-3 text-[14px]" style={{ opacity: ramp(t, start + 0.5 + i * 0.6), transform: `translateX(${(1 - ramp(t, start + 0.5 + i * 0.6)) * -10}px)` }}>
            <span className={cn('flex size-6 items-center justify-center rounded-full text-white', tone === 'yes' ? 'bg-cat-productive' : 'bg-destructive')}>
              {tone === 'yes' ? <Check className="size-3.5" /> : <X className="size-3.5" />}
            </span>
            {item}
          </li>
        ))}
      </ul>
    </div>
  )
}

function AppShell({ step, t }: { step: number; t: number }) {
  const lit = HIGHLIGHT[step] ?? []
  return (
    <div className="flex h-full">
      <aside className="flex w-[200px] shrink-0 flex-col border-r bg-sidebar px-3 py-3">
        <div className="mb-3 px-1">
          <Logo />
        </div>
        <div className="space-y-1.5">
          {SECTIONS.map((section) => {
            const on = lit.includes(section.name)
            return (
              <div key={section.name} className={cn('rounded-lg border border-transparent px-1.5 py-1 transition-all duration-500', on && step !== 8 && 'border-primary bg-primary/5 shadow-[0_0_0_3px] shadow-primary/15')}>
                <p className={cn('px-1 pb-0.5 text-[9px] font-semibold tracking-wide text-muted-foreground uppercase', on && step !== 8 && 'text-primary')}>{section.name}</p>
                {section.items.map((item) => (
                  <p
                    key={item.label}
                    className={cn(
                      'flex items-center gap-2 rounded px-1.5 py-[3px] text-[11.5px] font-medium',
                      item.label === 'Dashboard' && step === 8 ? 'bg-primary/10 text-primary' : 'text-muted-foreground',
                      on && step !== 8 && 'text-foreground',
                    )}
                  >
                    <item.icon className="size-3.5" />
                    {item.label}
                  </p>
                ))}
              </div>
            )
          })}
        </div>
      </aside>
      <div className="flex min-w-0 flex-1 flex-col">
        <div className="flex h-11 shrink-0 items-center justify-between border-b px-5">
          <div className="h-6 w-52 rounded-md border bg-card" />
          <div className="size-7 rounded-full bg-gradient-to-br from-violet-500 to-sky-500" />
        </div>
        <div className="min-h-0 flex-1 p-5">{step === 8 ? <DashboardTour t={t} /> : <SectionPreview step={step} t={t} />}</div>
      </div>
    </div>
  )
}

/** A big card naming what the highlighted section is for. */
function SectionPreview({ step, t }: { step: number; t: number }) {
  const cards: Record<number, { icon: typeof Users; title: string; text: string }[]> = {
    4: [{ icon: LayoutDashboard, title: 'Dashboard', text: 'Your home page: the whole team at a glance.' }],
    5: [
      { icon: Users, title: 'People', text: 'Employees, departments and teams.' },
      { icon: MonitorPlay, title: 'Live Tracking', text: 'Screenshots and live view.' },
      { icon: Activity, title: 'Activity', text: 'Applications and websites used.' },
      { icon: Clock, title: 'Time & Attendance', text: 'Hours against the required time.' },
    ],
    6: [
      { icon: FolderKanban, title: 'Projects & Tasks', text: 'Boards, tasks and timers.' },
      { icon: Gauge, title: 'Productivity', text: 'Productive, neutral and idle time.' },
      { icon: BellRing, title: 'Alerts', text: 'Notifications that need attention.' },
      { icon: FileChartColumn, title: 'Reports', text: 'CSV, Excel and PDF exports.' },
    ],
    7: [
      { icon: Settings, title: 'Settings', text: 'Workspace, monitoring, customer systems.' },
      { icon: ShieldCheck, title: 'Security', text: 'Password, two-step verification, sessions and the audit log.' },
      { icon: CircleHelp, title: 'Help (profile menu)', text: 'Short tutorials like this one.' },
    ],
  }
  const list = cards[step] ?? []
  return (
    <div key={step} className={cn('grid gap-4 pt-6', list.length === 1 ? 'grid-cols-1 px-24' : 'grid-cols-2')}>
      {list.map((c, i) => (
        <div
          key={c.title}
          className="flex items-center gap-4 rounded-xl border bg-card p-5 shadow-sm"
          style={{ opacity: ramp(t, 0.3 + i * 0.6), transform: `translateY(${(1 - ramp(t, 0.3 + i * 0.6)) * 12}px)` }}
        >
          <span className="flex size-12 shrink-0 items-center justify-center rounded-xl bg-primary/10 text-primary">
            <c.icon className="size-6" />
          </span>
          <span>
            <span className="block text-[16px] font-semibold">{c.title}</span>
            <span className="block text-[13px] text-muted-foreground">{c.text}</span>
          </span>
        </div>
      ))}
    </div>
  )
}

function DashboardTour({ t }: { t: number }) {
  const datePulse = t > 0.8 && t < 4
  const customizePulse = t > 6
  const bars = [0.9, 0.55, 0.35, 0.2]
  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <p className="text-[18px] font-semibold">Good afternoon, Admin</p>
        <div className="flex items-center gap-2">
          <span className={cn('flex items-center gap-1.5 rounded-md border bg-card px-2.5 py-1.5 text-[12px] transition-shadow', datePulse && 'border-primary ring-[3px] ring-primary/25')}>
            <CalendarRange className="size-3.5" /> This week
          </span>
          <span className={cn('flex size-8 items-center justify-center rounded-md border bg-card transition-shadow', customizePulse && 'border-primary ring-[3px] ring-primary/25')}>
            <SlidersHorizontal className="size-3.5" />
          </span>
        </div>
      </div>
      <div className="grid grid-cols-4 gap-3">
        {[
          ['Present today', '18 / 20'],
          ['Productivity', '82%'],
          ['Active time', '146h'],
          ['Customer time', '38h'],
        ].map(([label, value], i) => (
          <div key={label} className="rounded-xl border bg-card p-3" style={{ opacity: ramp(t, 1.4 + i * 0.3) }}>
            <p className="text-[18px] font-semibold tabular">{value}</p>
            <p className="text-[11px] text-muted-foreground">{label}</p>
          </div>
        ))}
      </div>
      <div className="grid grid-cols-3 gap-3">
        <div className="col-span-2 rounded-xl border bg-card p-4">
          <p className="mb-3 text-[13px] font-semibold">Websites &amp; Applications</p>
          {['claude.ai', 'osakaconnect.com', 'Microsoft Excel', 'chatgpt.com'].map((name, i) => (
            <div key={name} className="mb-2.5">
              <p className="mb-1 text-[12px]">{name}</p>
              <div className="h-1.5 rounded-full bg-muted">
                <div className="h-full origin-left rounded-full bg-primary" style={{ width: `${bars[i] * 100}%`, transform: `scaleX(${ramp(t, 2.4 + i * 0.25, 0.8)})` }} />
              </div>
            </div>
          ))}
        </div>
        <div className="rounded-xl border bg-card p-4">
          <p className="mb-3 text-[13px] font-semibold">Member Productivity</p>
          {['Basith', 'Jamsheed', 'Snigda'].map((name, i) => (
            <div key={name} className="mb-3 flex items-center gap-2" style={{ opacity: ramp(t, 3 + i * 0.3) }}>
              <span className="size-6 rounded-full bg-gradient-to-br from-amber-400 to-rose-500" />
              <span className="text-[12px]">{name}</span>
            </div>
          ))}
        </div>
      </div>
      <div
        className="absolute right-9 bottom-24 rounded-lg border bg-popover px-3 py-2 text-[12px] shadow-lg transition-opacity duration-300"
        style={{ opacity: customizePulse ? 1 : 0 }}
      >
        Customize: add, hide or move cards
      </div>
    </div>
  )
}

function GetStarted({ t }: { t: number }) {
  const steps = [
    { icon: Users, label: 'Add your employees' },
    { icon: Laptop, label: 'Install the desktop agent' },
    { icon: CalendarRange, label: 'Set your work schedule' },
  ]
  return (
    <div className="flex h-full flex-col items-center justify-center gap-6">
      <p className="text-[26px] font-semibold tracking-tight">Get started in three steps</p>
      <div className="space-y-3">
        {steps.map((s, i) => {
          const done = t >= 2.2 + i * 1.2
          return (
            <div key={s.label} className="flex w-96 items-center gap-4 rounded-xl border bg-card px-4 py-3 shadow-sm" style={{ opacity: ramp(t, 0.4 + i * 0.5) }}>
              <span className={cn('flex size-8 items-center justify-center rounded-full border text-[13px] font-semibold transition-colors duration-300', done && 'border-cat-productive bg-cat-productive text-white')}>
                {done ? <Check className="size-4" /> : i + 1}
              </span>
              <s.icon className="size-5 text-primary" />
              <span className="text-[15px] font-medium">{s.label}</span>
            </div>
          )
        })}
      </div>
      <p className="text-[13px] text-muted-foreground" style={{ opacity: ramp(t, 5.6) }}>
        The next tutorials show each step.
      </p>
    </div>
  )
}
