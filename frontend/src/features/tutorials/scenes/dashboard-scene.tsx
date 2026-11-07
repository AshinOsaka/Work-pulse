import { CalendarRange, Check, ChevronDown, GripVertical, LayoutDashboard, LayoutGrid, Plus, RotateCcw, Save, Settings2, SlidersHorizontal, X } from 'lucide-react'

import { cn } from '@/lib/utils'
import { Btn, Cursor, Shell, TitleCard, Toast, clickAt, ramp, type Point } from './parts'

/**
 * The "Dashboard" tutorial: the toolbar (view, team, range, calendar), the three areas, and customizing
 * (drag, rename/remove, add widget, save). Positions are absolute in the content box (origin 200, 44). Example data.
 */

export const CAPTIONS = [
  'The Dashboard: who is connected, work hours, productivity, websites and attendance, at a glance.',
  'Use the toolbar: choose Organization, Team or Individual, and filter by team.',
  'Pick a range — Today, 7, 14 or 30 days — or click the calendar to choose your own dates.',
  'Top row: Connected now and Work hours. Main column: productivity trend, websites & applications, attendance.',
  'Side column: member productivity (top and less productive) and recent activity. Click a person to open their profile.',
  'To change the layout, click Customize dashboard at the top right.',
  'Drag a widget to move it. Use the buttons on each widget to rename (configure) or remove it.',
  'Click Add widget to bring one back, or add optional widgets like My work and Daily work hours.',
  'Click Save dashboard. Reset returns to the standard layout. Your layout is saved for you alone.',
  'Done. Next: set up your productivity rules.',
]

const O = { x: 200, y: 44 }
const at = (x: number, y: number): Point => ({ x: O.x + x, y: O.y + y })

// Toolbar items (content-box coordinates of their centres).
const TB_Y = 76
const P: Record<string, Point> = {
  team: at(196, TB_Y),
  teamFilter: at(371, TB_Y),
  sevenDays: at(507, TB_Y),
  calendar: at(659, TB_Y),
  customize: at(715, 30),
  person: at(560, 282),
  grip: at(424, 430),
  remove: at(722, 410),
  addWidget: at(430, 76),
  addRecent: { x: 383, y: 238 },
  save: at(669, 76),
  rest: { x: 640, y: 480 },
}

type MainId = 'trend' | 'sites' | 'attendance'
const MAIN_H: Record<MainId, number> = { trend: 100, sites: 90, attendance: 52 }
const MAIN_TITLE: Record<MainId, string> = { trend: 'Productivity trend', sites: 'Websites & applications', attendance: 'Attendance' }

export function DashboardScene({ step, t }: { step: number; t: number }) {
  let cursor: Point = P.rest
  let click = false
  if (step === 1) {
    cursor = t < 2.6 ? P.team : P.teamFilter
    click = clickAt(t, 1.4) || clickAt(t, 3.4)
  } else if (step === 2) {
    cursor = t < 3 ? P.sevenDays : P.calendar
    click = clickAt(t, 1.4) || clickAt(t, 4.6)
  } else if (step === 4) {
    cursor = t >= 4.4 ? P.person : P.rest
  } else if (step === 5) {
    cursor = P.customize
    click = clickAt(t, 2.4)
  } else if (step === 6) {
    cursor = t < 1 ? P.grip : t < 2.6 ? at(424, 224) : P.remove
    click = clickAt(t, 0.8) || clickAt(t, 4.4)
  } else if (step === 7) {
    cursor = t < 1.8 ? P.addWidget : P.addRecent
    click = clickAt(t, 1.0) || clickAt(t, 3.4)
  } else if (step === 8) {
    cursor = t < 1.4 ? P.save : P.rest
    click = clickAt(t, 0.9)
  }

  const customizing = (step === 5 && t >= 2.6) || step === 6 || step === 7 || (step === 8 && t < 1.1)
  // Main column order: Attendance is dragged to the top in step 6.
  const dragged = step > 6 || (step === 6 && t >= 1.6)
  const order: MainId[] = dragged ? ['attendance', 'trend', 'sites'] : ['trend', 'sites', 'attendance']
  const recentGone = (step === 6 && t >= 4.6) || (step === 7 && t < 3.6)
  const view = step === 1 && t >= 1.5 ? 'Team' : 'Organization'
  const range = step === 2 ? (t >= 1.5 ? '7 days' : 'Today') : step >= 3 ? '7 days' : 'Today'

  return (
    <div className="relative h-[540px] w-[960px] overflow-hidden bg-background text-foreground select-none">
      <Shell active="Dashboard">
        <p className="absolute text-[18px] font-semibold" style={{ left: 20, top: 16 }}>
          Good afternoon, Admin
        </p>
        {!customizing && (
          <span
            className={cn('absolute flex size-8 items-center justify-center rounded-md text-muted-foreground', step === 5 && t > 0.8 && 'bg-primary/10 text-primary ring-[3px] ring-primary/25')}
            style={{ left: 699, top: 14 }}
          >
            <SlidersHorizontal className="size-4" />
          </span>
        )}
        {step === 5 && t > 0.8 && t < 2.6 && (
          <span className="absolute z-20 rounded-md bg-foreground px-2 py-1 text-[11px] whitespace-nowrap text-background" style={{ left: 600, top: 52 }}>
            Customize dashboard
          </span>
        )}

        {customizing ? <CustomizeBar step={step} t={t} /> : <Toolbar step={step} t={t} view={view} range={range} />}

        {/* Top row */}
        <Widget x={20} y={112} w={350} h={84} title="Connected now" glow={step === 3 && t < 3.6} edit={customizing}>
          <div className="mt-1 flex gap-6 text-[12px]">
            <Stat value="18" label="Online" tone="text-cat-productive" />
            <Stat value="2" label="Idle" tone="text-amber-500" />
            <Stat value="3" label="Offline" tone="text-muted-foreground" />
          </div>
        </Widget>
        <Widget x={380} y={112} w={360} h={84} title="Work hours" glow={step === 3 && t < 3.6} edit={customizing}>
          <div className="mt-1 flex gap-6 text-[12px]">
            <Stat value="146h" label="Active" />
            <Stat value="119h" label="Productive" tone="text-cat-productive" />
            <Stat value="21h" label="Neutral" tone="text-muted-foreground" />
          </div>
        </Widget>

        {/* Main column */}
        {order.map((id, i) => {
          const y = 206 + order.slice(0, i).reduce((sum, o) => sum + MAIN_H[o] + 8, 0)
          return (
            <Widget key={id} x={20} y={y} w={470} h={MAIN_H[id]} title={MAIN_TITLE[id]} glow={step === 3 && t >= 3.6} edit={customizing} lifted={step === 6 && id === 'attendance' && t >= 0.8 && t < 2.6}>
              {id === 'trend' && <Trend t={step === 0 ? 9 : t} />}
              {id === 'sites' && <Sites />}
              {id === 'attendance' && <AttendanceStrip />}
            </Widget>
          )
        })}

        {/* Side column */}
        <Widget x={500} y={206} w={240} h={176} title="Member productivity" glow={step === 4 && t < 6} edit={customizing}>
          <MemberList highlight={step === 4 && t >= 4.4} />
        </Widget>
        {!recentGone && (
          <Widget x={500} y={392} w={240} h={100} title="Recent activity" glow={step === 4 && t >= 2.6 && t < 6} edit={customizing} fresh={step === 7 && t >= 3.6}>
            <div className="mt-1 space-y-1.5 text-[11px] text-muted-foreground">
              <p>Jamsheed K P was added to Visa</p>
              <p>Work schedule updated</p>
            </div>
          </Widget>
        )}
      </Shell>

      {step === 2 && t >= 4.8 && <CalendarPopover />}
      {step === 7 && t >= 1.2 && t < 3.6 && <AddWidgetDialog />}
      {step === 8 && t >= 1.1 && <Toast title="Dashboard saved" />}
      {step === 0 && <TitleCard icon={LayoutDashboard} title="The Dashboard" text="Your team at a glance — and arranged the way you like." />}
      {step === 9 && <TitleCard icon={Check} title="Dashboard ready" text="Next: set up your productivity rules." />}
      {step !== 0 && step !== 9 && <Cursor at={cursor} click={click} />}
    </div>
  )
}

function Toolbar({ step, t, view, range }: { step: number; t: number; view: string; range: string }) {
  const seg = (items: string[], active: string, width: number) =>
    items.map((item) => (
      <span key={item} className={cn('flex h-7 items-center justify-center rounded-md text-[11.5px] transition-colors duration-300', item === active ? 'bg-background font-medium shadow-sm' : 'text-muted-foreground')} style={{ width }}>
        {item}
      </span>
    ))
  return (
    <div className="absolute flex h-10 items-center gap-1.5 rounded-2xl border bg-card px-1.5 shadow-xs" style={{ left: 80, top: 56 }}>
      <span className="flex rounded-lg bg-muted p-0.5">{seg(['Organization', 'Team', 'Individual'], view, 72)}</span>
      <span className="h-6 w-px bg-border" />
      <span className={cn('flex h-7 w-[100px] items-center justify-between rounded-md border px-2 text-[11.5px]', step === 1 && t >= 3.2 && 'border-primary ring-[3px] ring-primary/25')}>
        {step === 1 && t >= 3.6 ? 'Visa desk' : 'All teams'}
        <ChevronDown className="size-3 opacity-60" />
      </span>
      <span className="flex rounded-lg bg-muted p-0.5">{seg(['Today', '7 days', '14 days', '30 days'], range, 52)}</span>
      <span className={cn('flex size-7 items-center justify-center rounded-md border', step === 2 && t >= 4.2 && 'border-primary text-primary ring-[3px] ring-primary/25')}>
        <CalendarRange className="size-3.5" />
      </span>
    </div>
  )
}

function CustomizeBar({ step, t }: { step: number; t: number }) {
  const dirty = step >= 6 && !(step === 6 && t < 1.6)
  return (
    <div className="absolute flex h-12 items-center justify-between rounded-xl border border-primary/30 bg-primary/[0.04] px-3 duration-300 animate-in fade-in-0" style={{ left: 20, top: 52, width: 720 }}>
      <div>
        <p className="text-[12.5px] font-semibold">Customize dashboard</p>
        <p className="text-[11px] whitespace-nowrap text-muted-foreground">Drag, rename, add or remove widgets.</p>
      </div>
      <div className="flex items-center gap-1.5">
        <span className="mr-1 text-[11px] whitespace-nowrap text-muted-foreground">{dirty ? 'Unsaved changes' : 'No changes'}</span>
        <Btn focused={step === 7 && t < 1.6}>
          <Plus className="size-3.5" /> Add widget
        </Btn>
        <Btn>
          <RotateCcw className="size-3.5" /> Reset
        </Btn>
        <Btn>Exit</Btn>
        <Btn primary focused={step === 8}>
          <Save className="size-3.5" /> Save dashboard
        </Btn>
      </div>
    </div>
  )
}

function Widget({
  x,
  y,
  w,
  h,
  title,
  glow,
  edit,
  lifted,
  fresh,
  children,
}: {
  x: number
  y: number
  w: number
  h: number
  title: string
  glow?: boolean
  edit?: boolean
  lifted?: boolean
  fresh?: boolean
  children: React.ReactNode
}) {
  return (
    <div
      className={cn(
        'absolute rounded-xl border bg-card px-3 py-2.5 transition-all duration-700 ease-[cubic-bezier(.22,1,.36,1)]',
        glow && 'border-primary shadow-[0_0_0_3px] shadow-primary/20',
        edit && 'border-dashed border-primary/50',
        lifted && 'z-10 scale-[1.02] shadow-xl',
        fresh && 'duration-500 animate-in fade-in-0 zoom-in-95',
      )}
      style={{ left: x, top: y, width: w, height: h }}
    >
      <p className="text-[12px] font-semibold">{title}</p>
      {children}
      {edit && (
        <div className="absolute top-2 right-2 flex gap-1 text-muted-foreground">
          <span className="flex size-5 items-center justify-center rounded border bg-card">
            <GripVertical className="size-3" />
          </span>
          <span className="flex size-5 items-center justify-center rounded border bg-card">
            <Settings2 className="size-3" />
          </span>
          <span className="flex size-5 items-center justify-center rounded border bg-card">
            <X className="size-3" />
          </span>
        </div>
      )}
    </div>
  )
}

function Stat({ value, label, tone }: { value: string; label: string; tone?: string }) {
  return (
    <span>
      <span className={cn('block text-[18px] font-semibold tabular', tone)}>{value}</span>
      <span className="text-[10.5px] text-muted-foreground">{label}</span>
    </span>
  )
}

function Trend({ t }: { t: number }) {
  const prod = [52, 60, 48, 70, 66, 74, 80]
  return (
    <div className="mt-2 flex h-[58px] items-end gap-3 px-1">
      {prod.map((v, i) => (
        <div key={i} className="flex h-full flex-1 flex-col justify-end gap-0.5">
          <div className="origin-bottom rounded-t bg-cat-productive" style={{ height: `${v * 0.8}%`, transform: `scaleY(${ramp(t, 0.2 + i * 0.08, 0.6)})` }} />
          <div className="h-1.5 rounded-b bg-cat-unproductive/70" />
        </div>
      ))}
    </div>
  )
}

function Sites() {
  return (
    <div className="mt-1.5 space-y-1.5">
      {[
        ['claude.ai', 0.9],
        ['osakaconnect.com', 0.6],
        ['Microsoft Excel', 0.35],
      ].map(([name, w]) => (
        <div key={name as string} className="flex items-center gap-2 text-[11px]">
          <span className="w-28 truncate">{name}</span>
          <span className="h-1.5 flex-1 rounded-full bg-muted">
            <span className="block h-full rounded-full bg-primary" style={{ width: `${(w as number) * 100}%` }} />
          </span>
        </div>
      ))}
    </div>
  )
}

function AttendanceStrip() {
  return (
    <div className="mt-1.5 flex gap-1">
      {['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'].map((d, i) => (
        <span key={d} className={cn('flex-1 rounded py-0.5 text-center text-[10px]', i === 3 ? 'bg-amber-500/15 text-amber-600' : 'bg-cat-productive/15 text-cat-productive')}>
          {d}
        </span>
      ))}
    </div>
  )
}

function MemberList({ highlight }: { highlight: boolean }) {
  return (
    <div className="mt-2 space-y-2">
      {[
        ['Basith', '90%'],
        ['Jamsheed', '86%'],
        ['Snigda', '81%'],
      ].map(([name, pct], i) => (
        <div key={name} className={cn('flex items-center gap-2 rounded-md px-1 py-0.5 text-[11.5px]', highlight && i === 1 && 'bg-primary/10 text-primary')}>
          <span className="size-6 rounded-full bg-gradient-to-br from-amber-400 to-rose-500" />
          <span className="flex-1">{name}</span>
          <span className="tabular text-muted-foreground">{pct}</span>
        </div>
      ))}
    </div>
  )
}

function CalendarPopover() {
  return (
    <div className="absolute z-20 w-56 rounded-xl border bg-popover p-3 shadow-xl duration-200 animate-in fade-in-0 zoom-in-95" style={{ left: 712, top: 140 }}>
      <p className="mb-2 text-[12px] font-semibold">November 2026</p>
      <div className="grid grid-cols-7 gap-1 text-center text-[10px]">
        {Array.from({ length: 28 }, (_, i) => (
          <span key={i} className={cn('rounded py-1', i >= 2 && i <= 6 ? 'bg-primary text-primary-foreground' : 'text-muted-foreground')}>
            {i + 1}
          </span>
        ))}
      </div>
      <p className="mt-2 text-center text-[11px] text-muted-foreground">Reset to preset</p>
    </div>
  )
}

function AddWidgetDialog() {
  const items = [
    { title: 'Recent activity', text: 'Organisation changes in your scope.' },
    { title: 'My work', text: 'Your current task, timer and tasks for today.' },
    { title: 'Daily work hours', text: 'Compare active, productive and neutral hours day by day.' },
    { title: 'Attendance', text: 'Already on this dashboard' },
  ]
  return (
    <div className="absolute inset-0 z-20 bg-black/30 duration-300 animate-in fade-in-0">
      <div className="absolute rounded-xl border bg-card p-4 shadow-xl duration-300 animate-in zoom-in-95" style={{ left: 260, top: 150, width: 460 }}>
        <p className="flex items-center gap-2 text-[14px] font-semibold">
          <LayoutGrid className="size-4 text-muted-foreground" /> Add widget
        </p>
        <p className="mb-3 text-[11px] text-muted-foreground">Choose a widget. It goes back to its usual place, and you can move it afterwards.</p>
        <div className="grid grid-cols-2 gap-2">
          {items.map((i, n) => (
            <div key={i.title} className={cn('rounded-lg border p-2.5', n === 0 && 'border-primary bg-primary/5', n === 3 && 'opacity-50')}>
              <p className="text-[12px] font-semibold">{i.title}</p>
              <p className="text-[10.5px] text-muted-foreground">{i.text}</p>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
