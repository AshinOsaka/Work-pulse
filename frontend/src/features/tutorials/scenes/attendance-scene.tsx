import { CalendarDays, Check, Clock, Download, RefreshCw, Users } from 'lucide-react'

import { cn } from '@/lib/utils'
import { Btn, Cursor, Shell, TitleCard, Toast, clickAt, navPoint, ramp, rise, type Point } from './parts'

/**
 * The "Time & Attendance" tutorial: views and periods, the tiles, what "logged" means (active + customer-system
 * idle), how a day is Completed / Short / Absent / Holiday (as the backend decides), the per-person calendar and
 * day detail, auto-refresh, and Export CSV. Example data only.
 */

export const CAPTIONS = [
  "Time & Attendance: compare each person's logged time with the required hours of every working day.",
  'Choose Organization view or Individual view, and a period: Today, This week, This month, Last month or Custom.',
  'The tiles: people, days completed, short days, and untracked days (no work session).',
  'Logged = active time (keyboard or mouse input) + idle time with a customer system in front, e.g. a call with the CRM open.',
  'Completed: logged ≥ required. Short: worked, but less. Absent: a working day with no session. Days off and holidays never count as absence.',
  'Each row: logged and expected hours, status, and completed, holiday and untracked days. Click the calendar icon for a person’s month.',
  'The calendar colours each day. Click a day for active, signed in, idle and required time, sessions and customer time.',
  'Today shows as In progress until the day ends, and the page refreshes itself every minute.',
  'Click Export CSV to download the attendance for the period.',
  'Done. Next: screenshots and live view.',
]

const O = { x: 200, y: 44 }
const at = (x: number, y: number): Point => ({ x: O.x + x, y: O.y + y })

const P: Record<string, Point> = {
  attendance: navPoint('Time & Attendance'),
  orgView: at(77, 78),
  thisMonth: at(448, 78),
  calendarIcon: at(710, 328),
  day: at(498, 253),
  export: at(694, 78),
  rest: { x: 640, y: 480 },
}

const PEOPLE = [
  { name: 'Abdul Basith', dept: 'Visa', logged: '47h 10m', expected: '47h 00m', status: 'Completed', done: 6, hol: 1, un: 0 },
  { name: 'Jamsheed K P', dept: 'Visa', logged: '44h 35m', expected: '47h 00m', status: '−2h 25m', done: 4, hol: 1, un: 0 },
  { name: 'Snigda', dept: 'Ticketing', logged: '48h 05m', expected: '47h 00m', status: 'Over by 1h 05m', done: 6, hol: 1, un: 0 },
  { name: 'Abhinav Krishna', dept: 'Ticketing', logged: '37h 20m', expected: '47h 00m', status: '−9h 40m', done: 4, hol: 1, un: 1 },
]

type Day = 'met' | 'short' | 'absent' | 'holiday' | 'progress' | 'upcoming'
// November 2026 starts on a Sunday. Example statuses for the first 30 days.
const MONTH: Day[] = Array.from({ length: 30 }, (_, i) => {
  const d = i + 1
  const dow = (i + 0) % 7 // 0 = Sunday
  if (d > 7) return 'upcoming'
  if (d === 7) return 'progress'
  if (dow === 0) return 'holiday'
  if (d === 3) return 'short'
  if (d === 5) return 'absent'
  return 'met'
})
const DAY_CLS: Record<Day, string> = {
  met: 'bg-cat-productive/15 border-cat-productive/40 text-cat-productive',
  short: 'bg-destructive/10 border-destructive/40 text-destructive',
  absent: 'bg-destructive/10 border-destructive/40 text-destructive',
  holiday: 'bg-muted/70 text-muted-foreground',
  progress: 'bg-sky-500/15 border-sky-500/40 text-sky-600',
  upcoming: 'text-muted-foreground/50',
}

export function AttendanceScene({ step, t }: { step: number; t: number }) {
  let cursor: Point = P.rest
  let click = false
  if (step === 1) {
    cursor = t < 1.4 ? P.attendance : t < 4.4 ? P.orgView : P.thisMonth
    click = clickAt(t, 0.8) || clickAt(t, 3.6) || clickAt(t, 6.4)
  } else if (step === 5) {
    cursor = t < 6 ? P.rest : P.calendarIcon
    click = clickAt(t, 7.6)
  } else if (step === 6) {
    cursor = P.day
    click = clickAt(t, 2.6)
  } else if (step === 8) {
    cursor = P.export
    click = clickAt(t, 1)
  }

  const onPage = !(step === 1 && t < 1.0)
  const period = step === 1 && t < 6.5 ? 'This week' : 'This month'
  const calendar = (step === 5 && t >= 7.8) || step === 6 || step === 7
  const dayOpen = step === 6 ? t >= 2.8 : step === 7

  return (
    <div className="relative h-[540px] w-[960px] overflow-hidden bg-background text-foreground select-none">
      <Shell active={onPage && step >= 1 ? 'Time & Attendance' : 'Dashboard'}>
        {onPage && step >= 1 && (
          <>
            <p className="absolute text-[18px] font-semibold" style={{ left: 20, top: 12 }}>
              Attendance
            </p>
            <p className="absolute text-[11px] text-muted-foreground" style={{ left: 20, top: 38 }}>
              Sign-in and sign-out per day, and active time against the required hours.
            </p>
            <Toolbar step={step} t={t} period={period} />
            <Tiles step={step} t={t} />
            <PeopleTable step={step} t={t} narrow={calendar} />
            {calendar && <CalendarPanel step={step} t={t} dayOpen={dayOpen} />}
            {step === 3 && <LoggedExplainer t={t} />}
            {step === 4 && <StatusRules t={t} />}
          </>
        )}
      </Shell>
      {step === 8 && t >= 1.2 && <Toast title="Attendance exported" text="attendance-2026-11-01_2026-11-07.csv" />}
      {step === 0 && <TitleCard icon={Clock} title="Time & Attendance" text="Logged time against the required hours, day by day." />}
      {step === 9 && <TitleCard icon={Check} title="Attendance covered" text="Next: screenshots and live view." />}
      {step !== 0 && step !== 9 && <Cursor at={cursor} click={click} />}
    </div>
  )
}

function Seg({ items, active, width }: { items: string[]; active: string; width: number }) {
  return (
    <div className="flex rounded-lg bg-muted p-0.5">
      {items.map((i) => (
        <span key={i} className={cn('flex h-7 items-center justify-center rounded-md text-[11px] transition-colors duration-300', i === active ? 'bg-background font-medium shadow-sm' : 'text-muted-foreground')} style={{ width }}>
          {i}
        </span>
      ))}
    </div>
  )
}

function Toolbar({ step, t, period }: { step: number; t: number; period: string }) {
  return (
    <>
      <div className="absolute" style={{ left: 20, top: 62 }}>
        <Seg items={['Organization view', 'Individual view']} active="Organization view" width={113} />
      </div>
      <div className="absolute" style={{ left: 266, top: 62 }}>
        <Seg items={['Today', 'This week', 'This month', 'Last month', 'Custom']} active={period} width={72} />
      </div>
      <div className="absolute" style={{ right: 20, top: 62 }}>
        <Btn focused={step === 8 && t < 1.4}>
          <Download className="size-3.5" /> Export CSV
        </Btn>
      </div>
      {step === 7 && (
        <span className="absolute z-10 flex items-center gap-1.5 rounded-full border border-sky-500/30 bg-card px-2.5 py-1 text-[11px] text-sky-600 shadow-sm" style={{ left: 36, top: 456, opacity: ramp(t, 2.5) }}>
          <RefreshCw className="size-3 animate-spin [animation-duration:2s]" /> Updates every minute
        </span>
      )}
    </>
  )
}

function Tiles({ step, t }: { step: number; t: number }) {
  const tiles = [
    { label: 'People', value: '4', hint: 'This month', dot: '' },
    { label: 'Days completed', value: '20', hint: 'of 24 working days', dot: 'bg-cat-productive' },
    { label: 'Short days', value: '3', hint: 'Worked, but under the required hours', dot: 'bg-destructive' },
    { label: 'Untracked days', value: '1', hint: 'Working days with no work session', dot: 'bg-muted-foreground' },
  ]
  return (
    <>
      {tiles.map((tile, i) => (
        <div
          key={tile.label}
          className={cn('absolute rounded-xl border bg-card px-3 py-2.5 transition-shadow duration-300', step === 2 && t >= 0.6 + i * 1.2 && t < 1.8 + i * 1.2 && 'border-primary shadow-[0_0_0_3px] shadow-primary/20')}
          style={{ left: 20 + i * 182, top: 104, width: 172, height: 66 }}
        >
          <p className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
            {tile.dot ? <span className={cn('size-2 rounded-full', tile.dot)} /> : <Users className="size-3" />}
            {tile.label}
          </p>
          <p className="text-[20px] font-semibold tabular">{tile.value}</p>
          <p className="truncate text-[10px] text-muted-foreground">{tile.hint}</p>
        </div>
      ))}
    </>
  )
}

function PeopleTable({ step, t, narrow }: { step: number; t: number; narrow: boolean }) {
  const cols = narrow ? 'grid-cols-[1.4fr_0.8fr_1fr_0.5fr]' : 'grid-cols-[1.3fr_0.8fr_0.8fr_1.1fr_0.75fr_0.7fr_0.8fr_0.7fr]'
  return (
    <div className="absolute overflow-hidden rounded-xl border bg-card transition-all duration-500" style={{ left: 20, top: 182, width: narrow ? 330 : 720, height: 310 }}>
      <p className="absolute text-[13px] font-semibold" style={{ left: 16, top: 12 }}>
        Attendance by person
      </p>
      <p className="absolute truncate text-[10.5px] text-muted-foreground" style={{ left: 16, right: 16, top: 32 }}>
        This month · Logged = active time plus idle time with a customer system in front.
      </p>
      <div className="absolute" style={{ left: 0, right: 0, top: 58 }}>
        <div className={cn('grid h-7 items-center border-y bg-subtle/60 px-4 text-[9.5px] font-medium tracking-wide text-muted-foreground uppercase', cols)}>
          <span>Name</span>
          <span className={cn('text-right', step === 3 && 'text-primary')}>Logged</span>
          {!narrow && <span className="text-right">Expected</span>}
          <span className="pl-3">Status</span>
          {!narrow && <span className="text-right">Completed</span>}
          {!narrow && <span className="text-right">Holidays</span>}
          {!narrow && <span className="text-right">Untracked</span>}
          <span className="text-right">Calendar</span>
        </div>
        {PEOPLE.map((p, i) => {
          const good = p.status === 'Completed' || p.status.startsWith('Over')
          return (
            <div key={p.name} className={cn('grid h-10 items-center border-b px-4 text-[11.5px]', cols, narrow && i === 1 && 'bg-primary/5')} style={rise(step === 1 ? t - 6.5 : 9, 0.2 + i * 0.1)}>
              <span className="min-w-0">
                <span className="block truncate font-medium">{p.name}</span>
                <span className="block text-[10px] text-muted-foreground">{p.dept}</span>
              </span>
              <span className={cn('text-right font-medium tabular', step === 3 && 'text-primary')}>{p.logged}</span>
              {!narrow && <span className="text-right text-muted-foreground tabular">{p.expected}</span>}
              <span className="pl-3">
                <span className={cn('rounded-full px-2 py-0.5 text-[10px] font-medium whitespace-nowrap', good ? 'bg-cat-productive/15 text-cat-productive' : 'bg-destructive/10 text-destructive')}>{p.status}</span>
              </span>
              {!narrow && <span className="text-right tabular">{p.done}</span>}
              {!narrow && <span className="text-right tabular">{p.hol}</span>}
              {!narrow && <span className={cn('text-right tabular', p.un > 0 && 'font-medium text-destructive')}>{p.un}</span>}
              <span className="flex justify-end">
                <span className={cn('flex size-7 items-center justify-center rounded-md border', step === 5 && i === 1 && t >= 6.8 && 'border-primary text-primary ring-[3px] ring-primary/25')}>
                  <CalendarDays className="size-3.5" />
                </span>
              </span>
            </div>
          )
        })}
      </div>
    </div>
  )
}

function CalendarPanel({ step, t, dayOpen }: { step: number; t: number; dayOpen: boolean }) {
  return (
    <div className="absolute rounded-xl border bg-card p-3 duration-500 animate-in fade-in-0 slide-in-from-right-4" style={{ left: 360, top: 182, width: 380, height: 310 }}>
      <div className="mb-2 flex items-center justify-between">
        <p className="text-[13px] font-semibold">Jamsheed K P</p>
        <p className="text-[12px] font-medium">November 2026</p>
      </div>
      <div className="grid grid-cols-7 gap-1 text-center text-[9.5px] text-muted-foreground">
        {['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'].map((d) => (
          <span key={d}>{d}</span>
        ))}
      </div>
      <div className="mt-1 grid grid-cols-7 gap-1">
        {MONTH.map((s, i) => (
          <span
            key={i}
            className={cn('flex h-[26px] items-center justify-center rounded-md border border-transparent text-[10.5px] font-medium tabular', DAY_CLS[s], dayOpen && step !== 7 && i === 2 && 'ring-2 ring-primary', step === 7 && i === 6 && 'animate-pulse ring-2 ring-sky-500')}
            style={{ opacity: ramp(step === 5 ? t - 7.8 : 9, i * 0.02, 0.3) }}
          >
            {i + 1}
          </span>
        ))}
      </div>
      {!dayOpen ? (
        <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-[10px] text-muted-foreground">
          {[
            ['bg-cat-productive', 'Completed'],
            ['bg-destructive', 'Short / Absent'],
            ['bg-sky-500', 'In progress'],
            ['bg-muted-foreground/50', 'Holiday'],
          ].map(([c, l]) => (
            <span key={l} className="flex items-center gap-1">
              <span className={cn('size-2 rounded-full', c)} /> {l}
            </span>
          ))}
        </div>
      ) : (
        <div className="mt-2 rounded-lg border bg-subtle/50 p-2 text-[10.5px] duration-300 animate-in fade-in-0">
          <p className="mb-1 flex justify-between">
            <span className="font-semibold">Tue, 3 Nov</span>
            <span className="font-medium text-destructive">Short by 0h 40m</span>
          </p>
          <div className="grid grid-cols-4 gap-1">
            {[
              ['Active (logged)', '7h 10m'],
              ['Signed in', '8h 05m'],
              ['Idle', '0h 55m'],
              ['Required', '7h 50m'],
            ].map(([l, v]) => (
              <span key={l}>
                <span className="block text-muted-foreground">{l}</span>
                <span className="font-medium tabular">{v}</span>
              </span>
            ))}
          </div>
          <p className="mt-1 text-muted-foreground">Includes 0h 45m of customer time, counted as active.</p>
        </div>
      )}
    </div>
  )
}

function LoggedExplainer({ t }: { t: number }) {
  return (
    <div className="absolute z-10 flex items-center gap-2 rounded-xl border border-primary/40 bg-card p-3 text-[12px] shadow-lg" style={{ left: 120, top: 380, ...rise(t, 0.5) }}>
      <span className="rounded-md bg-cat-productive/15 px-2 py-1 font-medium text-cat-productive">Active time</span>
      <span className="text-muted-foreground">keyboard or mouse input</span>
      <span className="text-[16px] font-semibold">+</span>
      <span className="rounded-md bg-primary/15 px-2 py-1 font-medium text-primary" style={{ opacity: ramp(t, 2.6) }}>
        Customer time
      </span>
      <span className="text-muted-foreground" style={{ opacity: ramp(t, 2.6) }}>
        idle, CRM open
      </span>
      <span className="text-[16px] font-semibold" style={{ opacity: ramp(t, 5) }}>
        = Logged
      </span>
    </div>
  )
}

function StatusRules({ t }: { t: number }) {
  const rules = [
    ['bg-cat-productive', 'Completed', 'Logged ≥ required hours'],
    ['bg-destructive', 'Short', 'Worked, but less than required'],
    ['bg-destructive', 'Absent', 'Working day, no work session'],
    ['bg-muted-foreground/50', 'Holiday', 'Day off or company holiday — never absence'],
  ]
  return (
    <div className="absolute z-10 w-[420px] space-y-1.5 rounded-xl border bg-card p-3 shadow-lg" style={{ left: 170, top: 300 }}>
      {rules.map(([c, l, d], i) => (
        <p key={l} className="flex items-center gap-2 text-[12px]" style={rise(t, 0.4 + i * 2.2)}>
          <span className={cn('size-2.5 rounded-full', c)} />
          <span className="w-20 font-semibold">{l}</span>
          <span className="text-muted-foreground">{d}</span>
        </p>
      ))}
    </div>
  )
}
