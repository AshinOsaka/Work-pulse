import { Activity, AppWindow, Check, ChevronDown, ChevronLeft, ChevronRight, Clock, Globe, MousePointerClick } from 'lucide-react'

import { cn } from '@/lib/utils'
import { Cursor, Shell, Tabs, TitleCard, clickAt, navPoint, ramp, rise, type Point } from './parts'

/**
 * The "Activity" tutorial: the Activity page (period, team, person; tracked / active / applications tiles;
 * application and website usage with share and active %), then one person's day timeline on their profile's
 * Activity tab. Example data only.
 */

export const CAPTIONS = [
  'Activity: which applications and websites your team uses, and how much of that time is active.',
  'Choose a period — Today, Yesterday, 7 or 30 days — then filter by team or pick one person.',
  'Tiles: tracked time, active time and applications used. Active time = time with keyboard or mouse input.',
  'Application usage: each app with its time, its share of tracked time, and how much was active.',
  'Websites shows the domains visited — only the domain, never the full address, and only when website tracking is on.',
  'With no person selected, the People column shows how many people used each application.',
  "For one person's day, open their profile → Activity tab. The arrows move between days.",
  'The timeline lists each application in order: time, duration and active share. Hover a block for the window title.',
  'Activity shows what was used, not whether it was productive — your productivity rules decide that.',
  'Done. You have now seen every part of WorkPulse.',
]

const O = { x: 200, y: 44 }
const at = (x: number, y: number): Point => ({ x: O.x + x, y: O.y + y })
// The usage card sits at content (20, 182) → scene (220, 226).
const usage = (x: number, y: number): Point => ({ x: 220 + x, y: 226 + y })
// The profile's day card sits at content (20, 110) → scene (220, 154).
const day = (x: number, y: number): Point => ({ x: 220 + x, y: 154 + y })

const P: Record<string, Point> = {
  activity: navPoint('Activity'),
  sevenDays: at(197, 78),
  team: at(381, 78),
  people: at(546, 78),
  websites: usage(654, 29),
  peopleCol: usage(668, 100),
  peopleNav: navPoint('People'),
  activityTab: at(194, 78),
  prevDay: day(654, 28),
  block: day(250, 106),
  rest: { x: 640, y: 480 },
}

const APPS = [
  { name: 'Google Chrome', time: '18h 40m', share: 41, active: 78, people: 5 },
  { name: 'Visual Studio Code', time: '9h 15m', share: 20, active: 86, people: 2 },
  { name: 'Microsoft Excel', time: '6h 05m', share: 13, active: 64, people: 4 },
  { name: 'Microsoft Teams', time: '4h 30m', share: 10, active: 52, people: 5 },
  { name: 'Outlook', time: '3h 10m', share: 7, active: 70, people: 5 },
]
const SITES = [
  { name: 'claude.ai', time: '7h 20m', share: 39, active: 81, people: 3 },
  { name: 'osakaconnect.com', time: '5h 05m', share: 27, active: 62, people: 4 },
  { name: 'chatgpt.com', time: '2h 40m', share: 14, active: 85, people: 3 },
  { name: 'web.whatsapp.com', time: '1h 50m', share: 10, active: 58, people: 5 },
  { name: 'mail.google.com', time: '1h 15m', share: 7, active: 66, people: 5 },
]
const SEGMENTS = [
  { time: '9:32 am', app: 'Google Chrome', win: 'osakaconnect.com — Visa file 2231', dur: '0:42:10', active: 64, w: 15, c: 'bg-violet-500' },
  { time: '10:14 am', app: 'Microsoft Excel', win: 'Visa tracker November.xlsx', dur: '0:35:40', active: 72, w: 12, c: 'bg-emerald-500' },
  { time: '10:50 am', app: 'Google Chrome', win: 'claude.ai — Visa fee table cleanup', dur: '1:05:20', active: 88, w: 22, c: 'bg-violet-500' },
  { time: '11:56 am', app: 'Microsoft Teams', win: 'Daily stand-up', dur: '0:20:05', active: 35, w: 7, c: 'bg-sky-500' },
  { time: '12:16 pm', app: 'Outlook', win: 'Inbox', dur: '0:18:30', active: 70, w: 6, c: 'bg-amber-500' },
]

export function ActivityScene({ step, t }: { step: number; t: number }) {
  let cursor: Point = P.rest
  let click = false
  if (step === 1) {
    cursor = t < 1.4 ? P.activity : t < 3.4 ? P.sevenDays : t < 5.4 ? P.team : P.people
    click = clickAt(t, 0.8) || clickAt(t, 2.6) || clickAt(t, 4.6) || clickAt(t, 6.6)
  } else if (step === 4) {
    cursor = P.websites
    click = clickAt(t, 0.9)
  } else if (step === 5) {
    cursor = P.peopleCol
  } else if (step === 6) {
    cursor = t < 1.6 ? P.peopleNav : t < 3.6 ? P.rest : t < 5 ? P.activityTab : P.prevDay
    click = clickAt(t, 0.9) || clickAt(t, 4.2) || clickAt(t, 5.8)
  } else if (step === 7) {
    cursor = P.block
  }

  const onActivity = step >= 1 && step <= 5 && !(step === 1 && t < 1)
  const profile = step >= 6 && !(step === 6 && t < 1.1)
  return (
    <div className="relative h-[540px] w-[960px] overflow-hidden bg-background text-foreground select-none">
      <Shell active={profile ? 'People' : step >= 1 && !(step === 1 && t < 1) ? 'Activity' : 'Dashboard'}>
        {onActivity && <ActivityPage step={step} t={t} />}
        {profile && <ProfileActivity step={step} t={t} />}
      </Shell>
      {step === 8 && <RulesNote t={t} />}
      {step === 0 && <TitleCard icon={Activity} title="Activity" text="Which applications and websites are used — and how actively." />}
      {step === 9 && <TitleCard icon={Check} title="That's WorkPulse" text="You have now seen every part of WorkPulse." />}
      {step !== 0 && step !== 9 && step !== 8 && step !== 2 && step !== 3 && <Cursor at={cursor} click={click} />}
    </div>
  )
}

function ActivityPage({ step, t }: { step: number; t: number }) {
  const range = step === 1 && t < 2.7 ? 'Today' : '7 days'
  const sites = step === 4 && t >= 1
  const rows = sites ? SITES : APPS
  return (
    <>
      <p className="absolute flex items-center gap-2 text-[18px] font-semibold" style={{ left: 20, top: 8 }}>
        <Activity className="size-5 text-primary" /> Activity
      </p>
      <p className="absolute text-[11px] text-muted-foreground" style={{ left: 20, top: 36 }}>
        Application usage and active time, recorded by the desktop agent.
      </p>
      <div className="absolute flex rounded-lg bg-muted p-0.5" style={{ left: 20, top: 62 }}>
        {['Today', 'Yesterday', '7 days', '30 days'].map((r) => (
          <span key={r} className={cn('flex h-7 w-[70px] items-center justify-center rounded-md text-[11.5px] transition-colors', r === range ? 'bg-background font-medium shadow-sm' : 'text-muted-foreground')}>
            {r}
          </span>
        ))}
      </div>
      <span className={cn('absolute flex h-8 items-center justify-between rounded-md border px-2.5 text-[12px]', step === 1 && t >= 4.4 && t < 5.6 && 'border-primary ring-[3px] ring-primary/25')} style={{ left: 316, top: 62, width: 130 }}>
        All teams <ChevronDown className="size-3.5 opacity-60" />
      </span>
      <span className={cn('absolute flex h-8 items-center justify-between rounded-md border px-2.5 text-[12px] text-muted-foreground', step === 1 && t >= 6.4 && 'border-primary ring-[3px] ring-primary/25')} style={{ left: 456, top: 62, width: 180 }}>
        All people <ChevronDown className="size-3.5 opacity-60" />
      </span>

      {[
        { icon: Clock, label: 'Tracked time', value: '45h 10m', hint: 'In applications · 1 Nov – 7 Nov' },
        { icon: MousePointerClick, label: 'Active time', value: '34h 25m', hint: '76% of tracked time had keyboard or mouse input' },
        { icon: AppWindow, label: 'Applications', value: '14', hint: 'Distinct applications used' },
      ].map((tile, i) => (
        <div
          key={tile.label}
          className={cn('absolute rounded-xl border bg-card px-3 py-2.5 transition-shadow', step === 2 && t >= 0.6 + i * 1.6 && t < 2 + i * 1.6 && 'border-primary shadow-[0_0_0_3px] shadow-primary/20')}
          style={{ left: 20 + i * 243, top: 104, width: 233, height: 66 }}
        >
          <p className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
            <tile.icon className="size-3" /> {tile.label}
          </p>
          <p className="text-[19px] font-semibold tabular">{tile.value}</p>
          <p className="truncate text-[10px] text-muted-foreground">{tile.hint}</p>
        </div>
      ))}

      <div className="absolute rounded-xl border bg-card" style={{ left: 20, top: 182, width: 720, height: 310 }}>
        <p className="absolute text-[14px] font-semibold" style={{ left: 16, top: 12 }}>
          {sites ? 'Website usage' : 'Application usage'}
        </p>
        <p className="absolute text-[11px] text-muted-foreground" style={{ left: 16, top: 32 }}>
          1 Nov – 7 Nov{sites ? ' · domains only' : ''}
        </p>
        <div className="absolute flex rounded-lg bg-muted p-0.5" style={{ right: 16, top: 14 }}>
          {[
            ['Applications', AppWindow],
            ['Websites', Globe],
          ].map(([l, I]) => {
            const Icon = I as typeof Globe
            const on = (l === 'Websites') === sites
            return (
              <span key={l as string} className={cn('flex h-7 w-[100px] items-center justify-center gap-1.5 rounded-md text-[11.5px]', on ? 'bg-background font-medium shadow-sm' : 'text-muted-foreground')}>
                <Icon className="size-3.5" /> {l as string}
              </span>
            )
          })}
        </div>
        <div className="absolute" style={{ left: 0, right: 0, top: 58 }}>
          <div className="grid h-7 grid-cols-[1.4fr_1.2fr_0.6fr_0.5fr_0.5fr_0.5fr] items-center border-y bg-subtle/60 px-4 text-[10px] font-medium tracking-wide text-muted-foreground uppercase">
            <span>{sites ? 'Website' : 'Application'}</span>
            <span />
            <span className="text-right">Time</span>
            <span className={cn('text-right', step === 3 && t >= 2.4 && 'text-primary')}>Share</span>
            <span className={cn('text-right', step === 3 && t >= 4 && 'text-primary')}>Active</span>
            <span className={cn('text-right', step === 5 && 'text-primary')}>People</span>
          </div>
          {rows.map((r, i) => (
            <div key={r.name} className="grid h-[42px] grid-cols-[1.4fr_1.2fr_0.6fr_0.5fr_0.5fr_0.5fr] items-center border-b px-4 text-[12px] last:border-0" style={rise(step === 4 ? t - 1 : 9, 0.1 + i * 0.08)}>
              <span className="font-medium">{r.name}</span>
              <span className="mr-4 h-1.5 rounded-full bg-muted">
                <span className="block h-full rounded-full bg-primary" style={{ width: `${(r.share / rows[0].share) * 100}%` }} />
              </span>
              <span className="text-right tabular">{r.time}</span>
              <span className={cn('text-right text-muted-foreground tabular', step === 3 && t >= 2.4 && 'text-primary')}>{r.share}%</span>
              <span className={cn('text-right text-muted-foreground tabular', step === 3 && t >= 4 && 'text-primary')}>{r.active}%</span>
              <span className={cn('text-right tabular', step === 5 && 'font-semibold text-primary')}>{r.people}</span>
            </div>
          ))}
        </div>
        {sites && step === 4 && (
          <p className="absolute rounded-md bg-primary/10 px-2 py-1 text-[11px] text-primary" style={{ left: 180, top: 32, opacity: ramp(t, 3) }}>
            Domain only — never the full address
          </p>
        )}
      </div>
    </>
  )
}

function ProfileActivity({ step, t }: { step: number; t: number }) {
  const onTab = step > 6 || (step === 6 && t >= 4.3)
  const label = step > 6 || (step === 6 && t >= 5.9) ? 'Yesterday' : 'Today'
  const hovered = step === 7 && t >= 2.2 ? SEGMENTS[2] : null
  return (
    <>
      <div className="absolute flex items-center gap-3" style={{ left: 20, top: 10 }}>
        <span className="size-11 rounded-full bg-gradient-to-br from-amber-400 to-rose-500" />
        <span>
          <span className="block text-[17px] font-semibold">Jamsheed K P</span>
          <span className="block text-[11px] text-muted-foreground">Travel consultant · Visa</span>
        </span>
      </div>
      <div className="absolute" style={{ left: 20, top: 62, width: 720 }}>
        <Tabs tabs={['Overview', 'Attendance', 'Activity', 'Productivity', 'Screenshots', 'Tasks', 'Devices', 'Permissions']} active={onTab ? 'Activity' : 'Overview'} />
      </div>
      {onTab && (
        <div className="absolute rounded-xl border bg-card duration-300 animate-in fade-in-0" style={{ left: 20, top: 110, width: 720, height: 382 }}>
          <p className="absolute text-[14px] font-semibold" style={{ left: 16, top: 14 }}>
            {label}
          </p>
          <span className={cn('absolute flex size-7 items-center justify-center rounded-md border', step === 6 && t >= 5.4 && 'border-primary text-primary ring-[3px] ring-primary/25')} style={{ left: 640, top: 14 }}>
            <ChevronLeft className="size-3.5" />
          </span>
          <span className="absolute flex size-7 items-center justify-center rounded-md border" style={{ left: 676, top: 14 }}>
            <ChevronRight className="size-3.5" />
          </span>
          <div className="absolute grid grid-cols-3 gap-6 text-[12px]" style={{ left: 16, top: 48 }}>
            <span>
              <span className="block text-muted-foreground">Tracked time</span>
              <span className="font-semibold tabular">7h 42m</span>
            </span>
            <span>
              <span className="block text-muted-foreground">Active time</span>
              <span className="font-semibold tabular">6h 05m</span>
            </span>
            <span>
              <span className="block text-muted-foreground">Applications</span>
              <span className="font-semibold tabular">9</span>
            </span>
          </div>
          {/* Timeline strip */}
          <div className="absolute flex h-7 gap-0.5 overflow-hidden rounded-md bg-muted" style={{ left: 16, right: 16, top: 92 }}>
            {SEGMENTS.map((s, i) => (
              <div key={i} className={cn('h-full origin-left transition-opacity', s.c, hovered && hovered !== s && 'opacity-40')} style={{ width: `${s.w}%`, transform: `scaleX(${ramp(step === 6 ? t - 4.3 : 9, i * 0.15, 0.5)})` }} />
            ))}
          </div>
          <p className="absolute text-[11px] text-muted-foreground" style={{ left: 16, top: 126 }}>
            {hovered ? (
              <span className="text-foreground">
                <strong>{hovered.app}</strong> · {hovered.win} · 10:50–11:56 am
              </span>
            ) : (
              'Hover the timeline to see each application.'
            )}
          </p>
          <div className="absolute" style={{ left: 0, right: 0, top: 150 }}>
            <div className="grid h-7 grid-cols-[0.7fr_1fr_1.8fr_0.6fr_0.5fr] items-center border-y bg-subtle/60 px-4 text-[10px] font-medium tracking-wide text-muted-foreground uppercase">
              <span>Time</span>
              <span>Application</span>
              <span>Window</span>
              <span className="text-right">Duration</span>
              <span className="text-right">Active</span>
            </div>
            {SEGMENTS.map((s, i) => (
              <div key={i} className={cn('grid h-[38px] grid-cols-[0.7fr_1fr_1.8fr_0.6fr_0.5fr] items-center border-b px-4 text-[11.5px] last:border-0', hovered === s && 'bg-primary/5')} style={rise(step === 6 ? t - 4.6 : 9, i * 0.08)}>
                <span className="text-muted-foreground tabular">{s.time}</span>
                <span className="flex items-center gap-1.5 font-medium">
                  <span className={cn('size-2 rounded-full', s.c)} />
                  {s.app}
                </span>
                <span className="truncate pr-3 text-muted-foreground">{s.win}</span>
                <span className="text-right tabular">{s.dur}</span>
                <span className="text-right tabular">{s.active}%</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </>
  )
}

function RulesNote({ t }: { t: number }) {
  return (
    <div className="absolute z-20 flex items-center gap-4 rounded-xl border bg-card p-5 shadow-xl" style={{ left: 250, top: 190, width: 520, ...rise(t, 0.3) }}>
      <span className="flex size-12 shrink-0 items-center justify-center rounded-xl bg-primary/10 text-primary">
        <Activity className="size-6" />
      </span>
      <div className="text-[13px]">
        <p>
          <strong>Activity</strong> = what was used, and how actively.
        </p>
        <p className="mt-1 text-muted-foreground" style={{ opacity: ramp(t, 2.5) }}>
          Whether it was <strong className="text-cat-productive">productive</strong> is decided by your <strong>Productivity rules</strong>.
        </p>
      </div>
    </div>
  )
}
