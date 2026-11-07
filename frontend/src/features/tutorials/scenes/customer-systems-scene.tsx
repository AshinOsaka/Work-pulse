import { Check, ChevronDown, Clock, Gauge, Headset, LayoutDashboard, Pencil, Settings, Users, Activity, FileChartColumn, X } from 'lucide-react'

import { Logo } from '@/components/common/logo'
import { cn } from '@/lib/utils'

/**
 * The "Customer systems" tutorial, drawn as a simplified WorkPulse screen (960 × 540 design pixels, scaled by the
 * player). Everything is derived from (step, t) — the step index and the seconds elapsed in it — so the scene can be
 * paused, replayed and jumped to without any hidden state. Decorative mock-up only: no real data, no API calls.
 */

export const CAPTIONS = [
  'Customer systems: measure the time staff spend serving customers, in a CRM, ticketing portal or phone app.',
  'Open Settings from the sidebar, then choose the Customer systems tab.',
  'Type a name (for example OsakaConnect) and choose Website or Application.',
  'For a website, enter its domain (crm.osakaconnect.com). Subdomains are included. For an application, enter its program name.',
  'Choose the service (Visa, Ticketing, Insurance or Forex; required for websites) and the departments that use it.',
  'Click Add, then Save customer systems to apply the change.',
  'Click a name to edit it, × to remove it. Filter by service or department to find systems.',
  'Time in these systems now shows as customer time in Productivity, broken down by system.',
  'In Attendance, quiet time while a customer system is open (for example a call) counts towards the required hours.',
  'Done. Customer-facing staff are now measured by the work they really do.',
]

type Page = 'dashboard' | 'settings' | 'productivity' | 'attendance'

interface Frame {
  page: Page
  nav: string
  cursor: { x: number; y: number }
  click: boolean
  name: string
  kind: 'Website' | 'Application'
  domain: string
  service: string
  serviceOpen: boolean
  kindOpen: boolean
  added: boolean
  saved: boolean
  hoverName: boolean
  hoverRemove: boolean
  pulseFilters: boolean
  focus: 'name' | 'kind' | 'domain' | 'service' | 'dept' | 'add' | 'save' | null
}

/** Characters of `text` typed so far, typing from `from` to `to` seconds. */
function typed(text: string, t: number, from: number, to: number): string {
  if (t <= from) return ''
  if (t >= to) return text
  return text.slice(0, Math.ceil((text.length * (t - from)) / (to - from)))
}

const clickAt = (t: number, at: number) => t >= at && t < at + 0.35

// Design-pixel positions of the things the cursor visits.
const P = {
  navSettings: { x: 70, y: 506 },
  navProductivity: { x: 76, y: 232 },
  navAttendance: { x: 82, y: 200 },
  tab: { x: 620, y: 120 },
  name: { x: 300, y: 236 },
  kind: { x: 430, y: 236 },
  domain: { x: 548, y: 236 },
  service: { x: 690, y: 236 },
  dept: { x: 800, y: 236 },
  add: { x: 900, y: 236 },
  rowName: { x: 400, y: 330 },
  rowRemove: { x: 902, y: 330 },
  filters: { x: 330, y: 276 },
  save: { x: 850, y: 392 },
  rest: { x: 600, y: 420 },
}

function frameAt(step: number, t: number): Frame {
  const base: Frame = {
    page: 'settings',
    nav: 'Settings',
    cursor: P.rest,
    click: false,
    name: 'OsakaConnect',
    kind: 'Website',
    domain: 'crm.osakaconnect.com',
    service: 'Visa',
    serviceOpen: false,
    kindOpen: false,
    added: true,
    saved: true,
    hoverName: false,
    hoverRemove: false,
    pulseFilters: false,
    focus: null,
  }
  const empty = { name: '', domain: '', service: '', added: false, saved: false }
  switch (step) {
    case 0:
      return { ...base, ...empty, page: 'dashboard', nav: 'Dashboard', cursor: { x: 520, y: 300 } }
    case 1: {
      const onSettings = t >= 1.6
      return {
        ...base,
        ...empty,
        page: onSettings ? 'settings' : 'dashboard',
        nav: onSettings ? 'Settings' : 'Dashboard',
        cursor: t < 2.2 ? P.navSettings : P.tab,
        click: clickAt(t, 1.3) || clickAt(t, 3.0),
      }
    }
    case 2:
      return {
        ...base,
        ...empty,
        name: typed('OsakaConnect', t, 0.7, 2.3),
        cursor: t < 2.8 ? P.name : P.kind,
        click: clickAt(t, 0.4) || clickAt(t, 3.3),
        kindOpen: t >= 3.4 && t < 4.8,
        focus: t < 2.8 ? 'name' : 'kind',
      }
    case 3:
      return {
        ...base,
        ...empty,
        domain: typed('crm.osakaconnect.com', t, 0.9, 3.4),
        cursor: P.domain,
        click: clickAt(t, 0.5),
        focus: 'domain',
      }
    case 4:
      return {
        ...base,
        ...empty,
        service: t >= 3.0 ? 'Visa' : '',
        serviceOpen: t >= 1.0 && t < 3.0,
        cursor: t < 6.2 ? P.service : P.dept,
        click: clickAt(t, 0.8) || clickAt(t, 2.8) || clickAt(t, 6.6),
        focus: t < 6.2 ? 'service' : 'dept',
      }
    case 5:
      return {
        ...base,
        saved: t >= 3.4,
        added: t >= 1.0,
        name: t >= 1.0 ? '' : 'OsakaConnect',
        domain: t >= 1.0 ? '' : 'crm.osakaconnect.com',
        service: t >= 1.0 ? '' : 'Visa',
        cursor: t < 2.4 ? P.add : P.save,
        click: clickAt(t, 0.8) || clickAt(t, 3.2),
        focus: t < 2.4 ? 'add' : 'save',
      }
    case 6:
      return {
        ...base,
        name: '',
        domain: '',
        service: '',
        cursor: t < 3.0 ? P.rowName : t < 5.2 ? P.rowRemove : P.filters,
        hoverName: t >= 0.8 && t < 3.0,
        hoverRemove: t >= 3.6 && t < 5.2,
        pulseFilters: t >= 5.4,
      }
    case 7:
      return { ...base, page: t >= 1.1 ? 'productivity' : 'settings', nav: t >= 1.1 ? 'Productivity' : 'Settings', name: '', domain: '', service: '', cursor: t < 2 ? P.navProductivity : P.rest, click: clickAt(t, 0.8) }
    case 8:
      return { ...base, page: t >= 1.1 ? 'attendance' : 'productivity', nav: t >= 1.1 ? 'Time & Attendance' : 'Productivity', name: '', domain: '', service: '', cursor: t < 2 ? P.navAttendance : P.rest, click: clickAt(t, 0.8) }
    default:
      return { ...base, page: 'attendance', nav: 'Time & Attendance', name: '', domain: '', service: '' }
  }
}

const NAV = [
  { label: 'Dashboard', icon: LayoutDashboard },
  { label: 'People', icon: Users },
  { label: 'Activity', icon: Activity },
  { label: 'Time & Attendance', icon: Clock },
  { label: 'Productivity', icon: Gauge },
  { label: 'Reports', icon: FileChartColumn },
]

export function CustomerSystemsScene({ step, t }: { step: number; t: number }) {
  const f = frameAt(step, t)
  return (
    <div className="relative flex h-[540px] w-[960px] overflow-hidden bg-background text-foreground select-none">
      {/* Sidebar */}
      <aside className="flex w-[180px] shrink-0 flex-col border-r bg-sidebar px-3 py-4">
        <div className="mb-6 px-1">
          <Logo />
        </div>
        <ul className="space-y-1 text-[12px]">
          {NAV.map((n) => (
            <NavRow key={n.label} label={n.label} icon={n.icon} active={f.nav === n.label} />
          ))}
        </ul>
        <div className="mt-auto">
          <NavRow label="Settings" icon={Settings} active={f.nav === 'Settings'} />
        </div>
      </aside>

      {/* Main */}
      <div className="flex min-w-0 flex-1 flex-col">
        <div className="flex h-12 shrink-0 items-center justify-between border-b px-5">
          <div className="h-7 w-56 rounded-md border bg-card" />
          <div className="size-7 rounded-full bg-gradient-to-br from-violet-500 to-sky-500" />
        </div>
        <div key={f.page} className="relative min-h-0 flex-1 p-5 duration-500 animate-in fade-in-0 slide-in-from-bottom-2">
          {f.page === 'dashboard' && <DashboardMock />}
          {f.page === 'settings' && <SettingsMock f={f} />}
          {f.page === 'productivity' && <ProductivityMock t={step === 7 ? t - 1.1 : 9} />}
          {f.page === 'attendance' && <AttendanceMock t={step === 8 ? t - 1.1 : 9} />}
        </div>
      </div>

      {/* Title cards */}
      {(step === 0 || step === 9) && (
        <div className="absolute inset-0 flex items-center justify-center bg-background/70 backdrop-blur-sm duration-700 animate-in fade-in-0">
          <div className="flex flex-col items-center gap-4 text-center duration-700 animate-in zoom-in-95">
            <span className="flex size-16 items-center justify-center rounded-2xl bg-[linear-gradient(135deg,#7c3aed,#6366f1)] text-white shadow-[0_10px_30px_-8px_rgba(124,58,237,0.8)]">
              {step === 0 ? <Headset className="size-8" /> : <Check className="size-8" />}
            </span>
            <p className="text-[32px] font-semibold tracking-tight">{step === 0 ? 'Customer systems' : 'You are all set'}</p>
            <p className="max-w-md text-[15px] text-muted-foreground">
              {step === 0 ? 'Measure the time your team spends serving customers.' : 'Customer time now appears in Productivity and Attendance.'}
            </p>
          </div>
        </div>
      )}

      {/* Cursor */}
      {step !== 0 && step !== 9 && (
        <div
          className="pointer-events-none absolute z-20 transition-[left,top] duration-700 ease-[cubic-bezier(.22,1,.36,1)]"
          style={{ left: f.cursor.x, top: f.cursor.y }}
        >
          {f.click && <span className="absolute -top-4 -left-4 size-8 animate-ping rounded-full bg-primary/40" />}
          <svg width="22" height="22" viewBox="0 0 24 24" className="drop-shadow-md">
            <path d="M4 2l16 9.5-7 1.6-3.6 6.9z" fill="white" stroke="black" strokeWidth="1.4" strokeLinejoin="round" />
          </svg>
        </div>
      )}
    </div>
  )
}

function NavRow({ label, icon: Icon, active }: { label: string; icon: typeof Settings; active: boolean }) {
  return (
    <li
      className={cn(
        'flex items-center gap-2.5 rounded-md px-2.5 py-2 text-[12px] font-medium transition-colors duration-300',
        active ? 'bg-primary/10 text-primary' : 'text-muted-foreground',
      )}
    >
      <Icon className="size-4" />
      {label}
    </li>
  )
}

function DashboardMock() {
  return (
    <div className="space-y-4">
      <div className="h-6 w-48 rounded bg-muted" />
      <div className="grid grid-cols-4 gap-3">
        {[0, 1, 2, 3].map((i) => (
          <div key={i} className="h-20 rounded-xl border bg-card" />
        ))}
      </div>
      <div className="grid grid-cols-3 gap-3">
        <div className="col-span-2 h-56 rounded-xl border bg-card" />
        <div className="h-56 rounded-xl border bg-card" />
      </div>
    </div>
  )
}

function Field({ value, placeholder, focused, width, select }: { value: string; placeholder: string; focused: boolean; width: number; select?: boolean }) {
  return (
    <div
      className={cn(
        'flex h-9 shrink-0 items-center justify-between rounded-md border bg-card px-2.5 text-[12px] transition-shadow duration-300',
        focused && 'border-primary ring-[3px] ring-primary/25',
      )}
      style={{ width }}
    >
      <span className={cn('truncate', !value && 'text-muted-foreground')}>
        {value || placeholder}
        {focused && !select && <span className="ml-px inline-block h-3.5 w-px translate-y-0.5 animate-pulse bg-foreground" />}
      </span>
      {select && <ChevronDown className="size-3.5 shrink-0 opacity-60" />}
    </div>
  )
}

function Menu({ items, active, left }: { items: string[]; active: string; left: number }) {
  return (
    <div className="absolute top-[118px] z-10 w-32 rounded-lg border bg-popover p-1 text-[12px] shadow-lg duration-200 animate-in fade-in-0 zoom-in-95" style={{ left }}>
      {items.map((i) => (
        <div key={i} className={cn('rounded px-2 py-1.5', i === active && 'bg-accent font-medium')}>
          {i}
        </div>
      ))}
    </div>
  )
}

function SettingsMock({ f }: { f: Frame }) {
  const tabs = ['Profile', 'Workspace', 'Desktop agent', 'Monitoring & privacy', 'Customer systems', 'Appearance']
  return (
    <div className="space-y-4">
      <p className="text-[18px] font-semibold">Settings</p>
      <div className="flex gap-4 border-b text-[12px]">
        {tabs.map((tab) => (
          <span
            key={tab}
            className={cn('-mb-px border-b-2 pb-2', tab === 'Customer systems' ? 'border-primary font-medium text-foreground' : 'border-transparent text-muted-foreground')}
          >
            {tab}
          </span>
        ))}
      </div>
      <div className="relative rounded-xl border bg-card p-4">
        <p className="text-[14px] font-semibold">Customer-facing systems</p>
        <p className="mb-3 text-[11px] text-muted-foreground">Time spent in these systems is reported as customer time.</p>
        <div className="flex items-center gap-2">
          <Field value={f.name} placeholder="Name (e.g. OsakaConnect)" focused={f.focus === 'name'} width={150} />
          <Field value={f.kind} placeholder="Type" focused={f.focus === 'kind'} width={100} select />
          <Field value={f.domain} placeholder="crm.example.com" focused={f.focus === 'domain'} width={160} />
          <Field value={f.service} placeholder="Service type" focused={f.focus === 'service'} width={110} select />
          <Field value="All departments" placeholder="" focused={f.focus === 'dept'} width={110} select />
          <span
            className={cn(
              'flex h-9 items-center rounded-md border px-3 text-[12px] font-medium transition-shadow duration-300',
              f.focus === 'add' && 'border-primary ring-[3px] ring-primary/25',
            )}
          >
            Add
          </span>
        </div>
        {f.kindOpen && <Menu items={['Website', 'Application']} active="Website" left={176} />}
        {f.serviceOpen && <Menu items={['Visa', 'Ticketing', 'Insurance', 'Forex']} active="Visa" left={442} />}

        <div className={cn('mt-4 flex gap-4 text-[11px] text-muted-foreground transition-opacity', !f.added && 'opacity-0')}>
          <span className={cn('rounded-md border px-2 py-1', f.pulseFilters && 'animate-pulse border-primary text-primary')}>Service: All services</span>
          <span className={cn('rounded-md border px-2 py-1', f.pulseFilters && 'animate-pulse border-primary text-primary')}>Department: All departments</span>
        </div>
        <div className="mt-2 min-h-[46px] rounded-lg border">
          {f.added ? (
            <div className="flex items-center gap-2 px-3 py-2.5 text-[12px] duration-500 animate-in fade-in-0 slide-in-from-top-1">
              <span className="rounded bg-secondary px-1.5 py-0.5 text-[11px]">website</span>
              <span className="rounded border px-1.5 py-0.5 text-[11px]">Visa</span>
              <span className={cn('flex flex-1 items-center gap-1.5', f.hoverName && 'text-primary')}>
                <span className="font-medium">OsakaConnect</span>
                <span className="text-muted-foreground">· crm.osakaconnect.com</span>
                {f.hoverName && <Pencil className="size-3" />}
              </span>
              <span className="rounded-md border px-2 py-1 text-[11px]">All departments</span>
              <X className={cn('size-4 text-muted-foreground', f.hoverRemove && 'text-destructive')} />
            </div>
          ) : (
            <p className="px-3 py-3 text-[12px] text-muted-foreground">No customer systems yet.</p>
          )}
        </div>
        <div className="mt-4 flex justify-end">
          <span
            className={cn(
              'rounded-md bg-primary px-3 py-2 text-[12px] font-medium text-primary-foreground transition-shadow duration-300',
              f.focus === 'save' && 'ring-[3px] ring-primary/35',
            )}
          >
            Save customer systems
          </span>
        </div>
      </div>
      {f.saved && f.focus === 'save' && (
        <div className="absolute right-5 bottom-5 flex items-center gap-2 rounded-lg border bg-popover px-3 py-2 text-[12px] shadow-lg duration-300 animate-in fade-in-0 slide-in-from-bottom-2">
          <Check className="size-4 text-cat-productive" /> Customer systems updated
        </div>
      )}
    </div>
  )
}

function grow(t: number, delay: number) {
  return Math.max(0, Math.min(1, (t - delay) / 0.9))
}

function ProductivityMock({ t }: { t: number }) {
  const rows = [
    { name: 'OsakaConnect', time: '2h 10m', share: 1 },
    { name: 'Phone (softphone.exe)', time: '1h 10m', share: 0.54 },
  ]
  return (
    <div className="space-y-4">
      <p className="text-[18px] font-semibold">Productivity · Jamsheed</p>
      <div className="grid grid-cols-3 gap-3">
        <Stat label="Productive" value="5h 40m" />
        <Stat label="Customer time" value="3h 20m" highlight />
        <Stat label="Idle" value="0h 35m" />
      </div>
      <div className="rounded-xl border bg-card p-4">
        <p className="text-[14px] font-semibold">Customer time</p>
        <p className="mb-4 text-[11px] text-muted-foreground">Time in your customer-facing systems · 3h 20m total</p>
        <div className="space-y-4">
          {rows.map((r, i) => (
            <div key={r.name}>
              <div className="mb-1.5 flex justify-between text-[12px]">
                <span className="font-medium">{r.name}</span>
                <span className="tabular">{r.time}</span>
              </div>
              <div className="h-2 rounded-full bg-muted">
                <div className="h-full origin-left rounded-full bg-primary" style={{ width: `${r.share * 100}%`, transform: `scaleX(${grow(t, 0.4 + i * 0.3)})` }} />
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

function Stat({ label, value, highlight }: { label: string; value: string; highlight?: boolean }) {
  return (
    <div className={cn('rounded-xl border bg-card p-3', highlight && 'border-primary ring-[3px] ring-primary/20')}>
      <p className="text-[20px] font-semibold tabular">{value}</p>
      <p className="text-[11px] text-muted-foreground">{label}</p>
    </div>
  )
}

function AttendanceMock({ t }: { t: number }) {
  // A 9:30–18:00 day: active work, a 45-minute customer call with no typing (credited), more work.
  const parts = [
    { w: 34, cls: 'bg-cat-productive', label: 'Active' },
    { w: 9, cls: 'bg-primary', label: 'Customer call (quiet, CRM open)' },
    { w: 45, cls: 'bg-cat-productive', label: 'Active' },
  ]
  const shown = grow(t, 0.3)
  return (
    <div className="space-y-4">
      <p className="text-[18px] font-semibold">Time &amp; Attendance · Friday</p>
      <div className="rounded-xl border bg-card p-4">
        <div className="mb-3 flex items-center justify-between text-[12px]">
          <span className="font-medium">Jamsheed</span>
          <span className={cn('flex items-center gap-1.5 font-medium text-cat-productive transition-opacity duration-500', t < 2.2 && 'opacity-0')}>
            <Check className="size-4" /> 7h 50m required hours met
          </span>
        </div>
        <div className="flex h-7 gap-0.5 overflow-hidden rounded-md bg-muted">
          {parts.map((p, i) => (
            <div key={i} className={cn('h-full origin-left', p.cls, i === 1 && t > 1.4 && 'animate-pulse')} style={{ width: `${p.w}%`, transform: `scaleX(${shown})` }} />
          ))}
        </div>
        <div className="mt-2 flex justify-between text-[10px] text-muted-foreground">
          <span>9:30</span>
          <span>12:00</span>
          <span>15:00</span>
          <span>18:00</span>
        </div>
        <div className="mt-4 flex gap-5 text-[11px]">
          <span className="flex items-center gap-1.5"><span className="size-2.5 rounded-sm bg-cat-productive" /> Active work</span>
          <span className="flex items-center gap-1.5"><span className="size-2.5 rounded-sm bg-primary" /> Customer time, counted as work</span>
        </div>
      </div>
      <div className={cn('rounded-xl border border-primary/40 bg-primary/5 p-3 text-[12px] transition-opacity duration-500', t < 3.5 && 'opacity-0')}>
        The 45-minute call had no typing, but OsakaConnect was open, so it counts towards the required hours.
      </div>
    </div>
  )
}
