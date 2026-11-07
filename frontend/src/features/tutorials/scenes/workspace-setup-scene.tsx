import { CalendarCheck2, Check } from 'lucide-react'

import { cn } from '@/lib/utils'
import { Btn, Cursor, Field, Shell, Tabs, TitleCard, Toast, clickAt, navPoint, ramp, typed, type Point } from './parts'

/**
 * The "Workspace setup" tutorial: Settings → Workspace — time zone, working days, required hours per day and
 * holidays, then Save schedule. Positions inside the page are absolute (relative to the content box at 200, 44)
 * so the cursor targets below are exact. Example values only.
 */

export const CAPTIONS = [
  'Workspace setup: tell WorkPulse when your team works, so attendance and productivity use the right days and hours.',
  'Open Settings and choose the Workspace tab.',
  'In Workspace profile, check the name and the default time zone (days and hours are counted in it). Click Save changes.',
  'In Working days & holidays, tick the days your team works, for example Monday–Saturday.',
  'Days not ticked, like Sunday, are shown as holidays, not as absence.',
  'Set the required hours per working day: active time, breaks excluded. 9:30–6:00 with a 40-minute break = 7h 50m.',
  'Saturday can have its own, shorter requirement. Leave 0 for no requirement.',
  'Add company holidays: pick a date and click Add holiday. A holiday is never counted as absence.',
  "Click Save schedule. Attendance now compares each person's active time with these hours.",
  'Done. Next: choose what WorkPulse monitors, in Monitoring & privacy.',
]

const TABS = ['Profile', 'Workspace', 'Desktop agent', 'Monitoring & privacy', 'Customer systems', 'Appearance']
const DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

// Cards sit at (20, 100) in the content box, which starts at (200, 44): card point (x, y) = scene (220 + x, 144 + y).
const C = { x: 220, y: 144 }
const at = (x: number, y: number): Point => ({ x: C.x + x, y: C.y + y })
const chip = (i: number) => at(55 + i * 78, 82)
/** Required-hours box for weekday i (Mon = 0), inside the card. */
const hoursBox = (i: number) => ({ left: 20 + (i % 3) * 222, top: 150 + Math.floor(i / 3) * 42 })

const P: Record<string, Point> = {
  settings: navPoint('Settings'),
  workspaceTab: { x: 307, y: 129 },
  timezone: at(520, 80),
  saveProfile: at(630, 144),
  sat: chip(5),
  sun: chip(6),
  monHours: at(hoursBox(0).left + 68, hoursBox(0).top + 17),
  monMinutes: at(hoursBox(0).left + 131, hoursBox(0).top + 17),
  satHours: at(hoursBox(5).left + 68, hoursBox(5).top + 17),
  satMinutes: at(hoursBox(5).left + 131, hoursBox(5).top + 17),
  date: at(95, 274),
  addHoliday: at(226, 274),
  save: at(627, 334),
  rest: { x: 640, y: 470 },
}

export function WorkspaceSetupScene({ step, t }: { step: number; t: number }) {
  let cursor: Point = P.rest
  let click = false
  if (step === 1) {
    cursor = t < 1.4 ? P.settings : P.workspaceTab
    click = clickAt(t, 0.8) || clickAt(t, 2.0)
  } else if (step === 2) {
    cursor = t < 5.6 ? P.timezone : P.saveProfile
    click = clickAt(t, 3.2) || clickAt(t, 7.6)
  } else if (step === 3) {
    cursor = P.sat
    click = clickAt(t, 2.4)
  } else if (step === 4) {
    cursor = P.sun
  } else if (step === 5) {
    cursor = t < 3.5 ? P.monHours : P.monMinutes
    click = clickAt(t, 1.2) || clickAt(t, 3.8)
  } else if (step === 6) {
    cursor = t < 2.4 ? P.satHours : P.satMinutes
    click = clickAt(t, 0.8) || clickAt(t, 2.8)
  } else if (step === 7) {
    cursor = t < 2.6 ? P.date : P.addHoliday
    click = clickAt(t, 0.5) || clickAt(t, 3.0)
  } else if (step === 8) {
    cursor = P.save
    click = clickAt(t, 0.9)
  }

  const onSettings = !(step === 1 && t < 1.0)
  return (
    <div className="relative h-[540px] w-[960px] overflow-hidden bg-background text-foreground select-none">
      <Shell active={onSettings && step >= 1 ? 'Settings' : 'Dashboard'}>
        {onSettings && step >= 1 && (
          <>
            <p className="text-[18px] font-semibold">Settings</p>
            <p className="mb-3 text-[11px] text-muted-foreground">Manage your profile, workspace and preferences.</p>
            <Tabs tabs={TABS} active={step === 1 && t < 2.1 ? 'Profile' : 'Workspace'} />
            {step <= 2 ? <ProfileCard step={step} t={t} /> : <ScheduleCard step={step} t={t} />}
          </>
        )}
      </Shell>
      {step === 2 && t >= 7.8 && <Toast title="Workspace updated" />}
      {step === 8 && t >= 1.1 && <Toast title="Work schedule updated" text="Attendance compares active time with the required hours." />}
      {step === 0 && <TitleCard icon={CalendarCheck2} title="Workspace setup" text="Time zone, working days, required hours and holidays." />}
      {step === 9 && <TitleCard icon={Check} title="Schedule saved" text="Next: choose what WorkPulse monitors, in Monitoring & privacy." />}
      {step !== 0 && step !== 9 && <Cursor at={cursor} click={click} />}
    </div>
  )
}

function Card({ top, height, title, children }: { top: number; height: number; title: string; children: React.ReactNode }) {
  return (
    <div className="absolute rounded-xl border bg-card duration-300 animate-in fade-in-0" style={{ left: 20, top, width: 700, height }}>
      <p className="absolute top-4 left-5 text-[14px] font-semibold">{title}</p>
      {children}
    </div>
  )
}

function ProfileCard({ step, t }: { step: number; t: number }) {
  const tzOpen = step === 2 && t >= 3.3 && t < 5.2
  return (
    <Card top={100} height={170} title="Workspace profile">
      <div className="absolute" style={{ left: 20, top: 46, width: 320 }}>
        <Field label="Workspace name" value="Osaka Travels" />
      </div>
      <div className="absolute" style={{ left: 360, top: 46, width: 320 }}>
        <Field label="Default timezone" value="Asia/Kolkata" select focused={step === 2 && t >= 1.6 && t < 5.6} />
      </div>
      <p className="absolute text-[11px] text-primary" style={{ left: 360, top: 100, opacity: step === 2 ? ramp(t, 1.8) : 0 }}>
        Days and hours are counted in this time zone.
      </p>
      {tzOpen && (
        <div className="absolute z-10 w-[320px] rounded-lg border bg-popover p-1 text-[12px] shadow-lg duration-200 animate-in fade-in-0" style={{ left: 360, top: 96 }}>
          {['Asia/Dubai', 'Asia/Kolkata', 'Europe/London'].map((z) => (
            <div key={z} className={cn('rounded px-2 py-1.5', z === 'Asia/Kolkata' && 'bg-accent font-medium')}>
              {z}
            </div>
          ))}
        </div>
      )}
      <div className="absolute" style={{ right: 20, top: 128 }}>
        <Btn primary focused={step === 2 && t >= 7}>Save changes</Btn>
      </div>
    </Card>
  )
}

function ScheduleCard({ step, t }: { step: number; t: number }) {
  const satOn = step > 3 || (step === 3 && t >= 2.5)
  const work = (i: number) => i < 5 || (i === 5 && satOn)
  // Required minutes shown per weekday (Mon–Sat).
  const mon = step < 5 ? null : step === 5 ? { h: t >= 1.6 ? '7' : '0', m: typed('50', t, 4.2, 4.8) || '0' } : { h: '7', m: '50' }
  const others = step > 5 || (step === 5 && t >= 6.2)
  const sat = step < 6 ? (others ? { h: '7', m: '50' } : { h: '0', m: '0' }) : step === 6 ? { h: t >= 1.2 ? '5' : '7', m: t >= 3.2 ? '20' : '50' } : { h: '5', m: '20' }
  const req = (i: number) => (i === 5 ? sat : i === 0 ? (mon ?? { h: '0', m: '0' }) : others ? { h: '7', m: '50' } : { h: '0', m: '0' })
  const date = step === 7 ? typed('25-12-2026', t, 0.9, 2.2) : ''
  const holidayAdded = step > 7 || (step === 7 && t >= 3.1)
  return (
    <Card top={100} height={364} title="Working days & holidays">
      {/* Working days */}
      <p className="absolute text-[11px] font-medium" style={{ left: 20, top: 50 }}>
        Working days
      </p>
      {DAYS.map((d, i) => (
        <div
          key={d}
          className={cn(
            'absolute flex h-7 items-center gap-1.5 rounded-md border px-2 text-[12px] transition-colors duration-300',
            work(i) ? 'border-primary/50 bg-primary/10 font-medium' : 'text-muted-foreground',
            step === 4 && i === 6 && 'ring-[3px] ring-primary/25',
          )}
          style={{ left: 20 + i * 78, top: 68, width: 70 }}
        >
          <span className={cn('flex size-3.5 items-center justify-center rounded-sm border', work(i) && 'border-primary bg-primary text-primary-foreground')}>
            {work(i) && <Check className="size-2.5" />}
          </span>
          {d}
        </div>
      ))}
      {step === 4 && (
        <p className="absolute rounded-md bg-primary/10 px-2 py-1 text-[11px] whitespace-nowrap text-primary" style={{ left: 420, top: 104, opacity: ramp(t, 0.8) }}>
          Sunday → shown as a holiday, not absence
        </p>
      )}

      {/* Required hours */}
      <p className="absolute text-[11px] font-medium" style={{ left: 20, top: 130, opacity: step >= 5 ? 1 : 0.35 }}>
        Required hours per day
      </p>
      {step === 5 && (
        <p className="absolute rounded-md bg-primary/10 px-2 py-1 text-[11px] text-primary tabular" style={{ left: 200, top: 126, opacity: ramp(t, 2) }}>
          9:30 – 6:00 − 40 min break = 7h 50m
        </p>
      )}
      {step === 6 && (
        <p className="absolute text-[11px] text-muted-foreground" style={{ left: 200, top: 130, opacity: ramp(t, 3.4) }}>
          Leave 0 for no requirement.
        </p>
      )}
      {DAYS.slice(0, 6).map((d, i) => {
        const box = hoursBox(i)
        const r = req(i)
        const focusH = (step === 5 && i === 0 && t >= 1.2 && t < 3.6) || (step === 6 && i === 5 && t < 2.6)
        const focusM = (step === 5 && i === 0 && t >= 3.6) || (step === 6 && i === 5 && t >= 2.6)
        return (
          <div
            key={d}
            className={cn('absolute flex items-center gap-1.5 rounded-md border px-2 text-[12px]', step < 5 && 'opacity-35')}
            style={{ left: box.left, top: box.top, width: 210, height: 34 }}
          >
            <span className="w-8 font-medium">{d}</span>
            <span className={cn('flex h-6 w-11 items-center rounded border bg-card px-1.5 tabular', focusH && 'border-primary ring-2 ring-primary/25')}>{r.h}</span>
            <span className="text-muted-foreground">h</span>
            <span className={cn('flex h-6 w-11 items-center rounded border bg-card px-1.5 tabular', focusM && 'border-primary ring-2 ring-primary/25')}>{r.m}</span>
            <span className="text-muted-foreground">m</span>
          </div>
        )
      })}

      {/* Holidays */}
      <p className="absolute text-[11px] font-medium" style={{ left: 20, top: 240 }}>
        Holidays
      </p>
      <div className="absolute" style={{ left: 20, top: 258, width: 150 }}>
        <Field value={date} placeholder="dd-mm-yyyy" focused={step === 7 && t >= 0.5 && t < 2.8} />
      </div>
      <div className="absolute" style={{ left: 180, top: 258 }}>
        <Btn focused={step === 7 && t >= 2.6 && t < 3.4}>Add holiday</Btn>
      </div>
      {holidayAdded ? (
        <span className="absolute rounded-full border bg-subtle px-2.5 py-1 text-[11px] tabular duration-300 animate-in fade-in-0 zoom-in-95" style={{ left: 300, top: 262 }}>
          25 Dec 2026 ×
        </span>
      ) : (
        <span className="absolute text-[11px] text-muted-foreground" style={{ left: 300, top: 266 }}>
          No holidays added.
        </span>
      )}

      <div className="absolute" style={{ right: 20, top: 318 }}>
        <Btn primary focused={step === 8 && t < 1.4}>Save schedule</Btn>
      </div>
    </Card>
  )
}
