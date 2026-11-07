import { Activity, BarChart3, Camera, Check, ChevronLeft, ChevronRight, Download, Images, MonitorPlay, Plus, Square } from 'lucide-react'

import { cn } from '@/lib/utils'
import { Btn, Cursor, Field, Shell, TitleCard, Toast, clickAt, navPoint, ramp, rise, type Point } from './parts'

/**
 * The "Screenshots & live view" tutorial: the screenshot gallery by member and day, Raise Request → a ZIP in
 * Download Requests, the Live Stream page, a live view (peer-to-peer, not recorded, audited, tray badge) and the
 * session log. Screens are drawn placeholders, never real captures.
 */

export const CAPTIONS = [
  "Screenshots & live view: an employee's screen, only when your monitoring policy allows it — and always visibly to them.",
  'Live Tracking → Screenshot: choose a member and a date. That day’s screenshots appear in the gallery, by time.',
  'Click a screenshot to see it larger. Use the arrows for the previous or next day.',
  'To download a whole day, click Raise Request, choose the member and date, and Raise request.',
  'Open Download Requests. When the status shows Ready, click Download to save a ZIP file.',
  'Live viewing: open Live Stream to see who is online, active, idle or offline.',
  'Click View live on an online employee. Peer-to-peer, never recorded, and every view is audited.',
  "The employee's tray icon shows a badge while being viewed. The stream ends automatically, or click Stop stream.",
  'The Session log lists every live view: who watched, the device, and how long it lasted.',
  'Done. Next: create reports.',
]

const O = { x: 200, y: 44 }
const at = (x: number, y: number): Point => ({ x: O.x + x, y: O.y + y })

const P: Record<string, Point> = {
  liveTracking: navPoint('Live Tracking'),
  members: at(431, 78),
  thumb: at(105, 206),
  nextDay: at(206, 124),
  raise: at(686, 78),
  raiseSubmit: { x: 590, y: 346 },
  requests: at(279, 78),
  download: { x: 628, y: 220 },
  viewLive: at(106, 310),
  stop: { x: 885, y: 28 },
  rest: { x: 640, y: 480 },
}

const TIMES = ['9:42 am', '10:13 am', '10:48 am', '11:21 am', '12:05 pm', '2:17 pm', '2:52 pm', '3:31 pm']

export function ScreenshotsLiveScene({ step, t }: { step: number; t: number }) {
  let cursor: Point = P.rest
  let click = false
  if (step === 1) {
    cursor = t < 1.6 ? P.liveTracking : P.members
    click = clickAt(t, 0.8) || clickAt(t, 2.6)
  } else if (step === 2) {
    cursor = t < 3 ? P.thumb : P.nextDay
    click = clickAt(t, 0.6) || clickAt(t, 3.6)
  } else if (step === 3) {
    cursor = t < 2.6 ? P.raise : P.raiseSubmit
    click = clickAt(t, 0.8) || clickAt(t, 5.4)
  } else if (step === 4) {
    cursor = t < 1.6 ? P.requests : P.download
    click = clickAt(t, 0.8) || clickAt(t, 5.4)
  } else if (step === 5) {
    cursor = P.liveTracking
    click = clickAt(t, 0.8)
  } else if (step === 6) {
    cursor = P.viewLive
    click = clickAt(t, 1)
  } else if (step === 7) {
    cursor = t < 5 ? P.rest : P.stop
    click = clickAt(t, 6)
  }

  const live = step >= 5
  const viewer = (step === 6 && t >= 1.2) || (step === 7 && t < 6.2)
  return (
    <div className="relative h-[540px] w-[960px] overflow-hidden bg-background text-foreground select-none">
      <Shell active={step >= 1 ? 'Live Tracking' : 'Dashboard'}>
        {step >= 1 && !live && <ScreenshotsPage step={step} t={t} />}
        {live && !viewer && <LivePage step={step} t={t} />}
      </Shell>
      {step === 2 && t >= 0.8 && t < 3.2 && <Enlarged />}
      {step === 3 && t >= 1 && t < 5.6 && <RaiseDialog t={t} />}
      {step === 3 && t >= 5.6 && <Toast title="Request raised" text="Follow it in Download Requests." />}
      {step === 4 && t >= 1 && <RequestsDialog t={t} />}
      {viewer && <Viewer step={step} t={t} />}
      {step === 7 && t < 6 && <TrayBadge t={t} />}
      {step === 0 && <TitleCard icon={Camera} title="Screenshots & live view" text="Only when your policy allows it — and always visible to the employee." />}
      {step === 9 && <TitleCard icon={Check} title="Screens covered" text="Next: create reports." />}
      {step !== 0 && step !== 9 && <Cursor at={cursor} click={click} />}
    </div>
  )
}

function ScreenshotsPage({ step, t }: { step: number; t: number }) {
  const member = step > 1 || (step === 1 && t >= 2.8)
  const day = step === 2 && t >= 3.8 ? 'Thu, 5 November' : 'Fri, 6 November'
  return (
    <>
      <p className="absolute text-[18px] font-semibold" style={{ left: 20, top: 12 }}>
        Screenshots
      </p>
      <p className="absolute text-[11px] text-muted-foreground" style={{ left: 20, top: 38 }}>
        View screenshots by date, and download a day&apos;s captures.
      </p>
      <div className="absolute flex rounded-lg bg-muted p-0.5" style={{ left: 20, top: 62 }}>
        {[
          ['Gallery', Images],
          ['Productivity', BarChart3],
        ].map(([l, I]) => {
          const Icon = I as typeof Images
          return (
            <span key={l as string} className={cn('flex h-7 w-[84px] items-center justify-center gap-1.5 rounded-md text-[11.5px]', l === 'Gallery' ? 'bg-background font-medium shadow-sm' : 'text-muted-foreground')}>
              <Icon className="size-3.5" /> {l as string}
            </span>
          )
        })}
      </div>
      <div className="absolute" style={{ left: 204, top: 62 }}>
        <Btn focused={step === 4 && t < 1.2}>
          <Download className="size-3.5" /> Download Requests
        </Btn>
      </div>
      <div className="absolute" style={{ left: 366, top: 62, width: 130 }}>
        <Field value={member ? 'Jamsheed K P' : ''} placeholder="Members" select focused={step === 1 && t >= 1.8 && t < 3} />
      </div>
      <div className="absolute" style={{ left: 504, top: 62, width: 104 }}>
        <Field value="06-11-2026" />
      </div>
      <div className="absolute" style={{ right: 20, top: 62 }}>
        <Btn primary focused={step === 3 && t < 1.2}>
          <Plus className="size-3.5" /> Raise Request
        </Btn>
      </div>
      {member ? (
        <>
          <div className="absolute flex items-center gap-2" style={{ left: 20, top: 110 }}>
            <span className="flex size-7 items-center justify-center rounded-md border">
              <ChevronLeft className="size-3.5" />
            </span>
            <span className="w-32 text-center text-[12px] font-medium">{day}</span>
            <span className={cn('flex size-7 items-center justify-center rounded-md border', step === 2 && t >= 3.2 && t < 4.2 && 'border-primary text-primary ring-[3px] ring-primary/25')}>
              <ChevronRight className="size-3.5" />
            </span>
          </div>
          <div key={day} className="absolute grid grid-cols-4 gap-3" style={{ left: 20, top: 150, width: 720 }}>
            {TIMES.map((time, i) => (
              <div key={time} style={rise(step === 1 ? t - 2.8 : step === 2 && t >= 3.8 ? t - 3.8 : 9, 0.1 + i * 0.08)}>
                <Shot seed={i} className={cn('h-[112px]', step === 2 && i === 0 && t < 0.8 && 'ring-[3px] ring-primary/40')} />
                <p className="mt-1 text-[10.5px] text-muted-foreground tabular">{time}</p>
              </div>
            ))}
          </div>
        </>
      ) : (
        <p className="absolute text-[12px] text-muted-foreground" style={{ left: 20, top: 140 }}>
          Choose a member above, or use Raise Request to download a day&apos;s screenshots as a ZIP.
        </p>
      )}
    </>
  )
}

/** A drawn stand-in for a screenshot: a window with a few bars. Never a real capture. */
function Shot({ seed, className }: { seed: number; className?: string }) {
  const hues = ['from-violet-500/30', 'from-sky-500/30', 'from-emerald-500/30', 'from-amber-500/30']
  return (
    <div className={cn('overflow-hidden rounded-lg border bg-gradient-to-br to-transparent p-2', hues[seed % hues.length], className)}>
      <div className="h-2 w-1/3 rounded bg-foreground/20" />
      <div className="mt-2 grid grid-cols-3 gap-1.5">
        <div className="col-span-2 h-14 rounded bg-card/80" />
        <div className="h-14 rounded bg-card/60" />
      </div>
      <div className="mt-1.5 h-1.5 w-2/3 rounded bg-foreground/15" />
    </div>
  )
}

function Enlarged() {
  return (
    <div className="absolute inset-0 z-20 bg-black/50 duration-300 animate-in fade-in-0">
      <div className="absolute duration-300 animate-in zoom-in-95" style={{ left: 250, top: 70, width: 520 }}>
        <Shot seed={0} className="h-[300px]" />
        <p className="mt-2 text-center text-[12px] text-white">Jamsheed K P · Fri, 6 November · 9:42 am</p>
      </div>
    </div>
  )
}

function Dialog({ title, text, children }: { title: string; text: string; children: React.ReactNode }) {
  return (
    <div className="absolute inset-0 z-20 bg-black/30 duration-300 animate-in fade-in-0">
      <div className="absolute rounded-xl border bg-card p-5 shadow-xl duration-300 animate-in zoom-in-95" style={{ left: 300, top: 120, width: 360 }}>
        <p className="text-[14px] font-semibold">{title}</p>
        <p className="mb-3 text-[11px] text-muted-foreground">{text}</p>
        {children}
      </div>
    </div>
  )
}

function RaiseDialog({ t }: { t: number }) {
  return (
    <Dialog title="Request a screenshot download" text="We'll package that person's screenshots for the chosen day into a ZIP you can download.">
      <div className="space-y-3">
        <Field label="Member" value="Jamsheed K P" select focused={t >= 1.6 && t < 3.4} />
        <Field label="Date" value="06-11-2026" focused={t >= 3.4 && t < 4.6} />
      </div>
      <div className="mt-4 flex justify-end gap-2">
        <Btn>Cancel</Btn>
        <Btn primary focused={t >= 4.8}>
          Raise request
        </Btn>
      </div>
    </Dialog>
  )
}

function RequestsDialog({ t }: { t: number }) {
  const status = t < 2.4 ? 'Preparing' : t < 3.8 ? 'Packaging' : 'Ready'
  const ready = status === 'Ready'
  return (
    <div className="absolute inset-0 z-20 bg-black/30 duration-300 animate-in fade-in-0">
      <div className="absolute rounded-xl border bg-card p-5 shadow-xl duration-300 animate-in zoom-in-95" style={{ left: 260, top: 140, width: 440 }}>
        <p className="mb-3 text-[14px] font-semibold">Download requests</p>
        <div className="flex items-center gap-3 rounded-lg border p-3 text-[12px]">
          <span className="flex-1">
            <span className="block font-medium">Jamsheed K P · Fri, 6 November</span>
            <span className="text-[10.5px] text-muted-foreground">{ready ? '8 screenshots · ZIP' : `${Math.round(100 * ramp(t, 1, 2.8))}%`}</span>
          </span>
          <span className={cn('rounded-full px-2 py-0.5 text-[10.5px] font-medium', ready ? 'bg-primary text-primary-foreground' : 'bg-muted')}>{status}</span>
          {ready && (
            <span className={cn('flex h-7 items-center gap-1 rounded-md border px-2.5 text-[11px] font-medium duration-300 animate-in fade-in-0', t >= 5 && 'border-primary ring-[3px] ring-primary/25')}>
              <Download className="size-3.5" /> Download
            </span>
          )}
        </div>
        {t >= 5.6 && <p className="mt-2 text-[11px] text-cat-productive">Saved: screenshots-jamsheed-2026-11-06.zip</p>}
      </div>
    </div>
  )
}

const PEOPLE = [
  { name: 'Jamsheed K P', status: 'Active', app: 'osakaconnect.com', on: true },
  { name: 'Abdul Basith', status: 'Active', app: 'Visual Studio Code', on: true },
  { name: 'Snigda', status: 'Idle', app: 'Microsoft Excel', on: true },
  { name: 'Abhinav Krishna', status: 'Offline', app: 'Last seen 6:02 pm', on: false },
]

function LivePage({ step, t }: { step: number; t: number }) {
  const tiles = [
    ['Online employees', '3'],
    ['Active sessions', '2'],
    ['Idle employees', '1'],
    ['Offline employees', '1'],
  ]
  if (step >= 8) return <SessionLog t={t} />
  return (
    <>
      <p className="absolute flex items-center gap-2 text-[18px] font-semibold" style={{ left: 20, top: 12 }}>
        <MonitorPlay className="size-5 text-primary" /> Live Tracking
      </p>
      <p className="absolute text-[11px] text-muted-foreground" style={{ left: 20, top: 40 }}>
        See who&apos;s online and start an authorised live view.
      </p>
      {tiles.map(([l, v], i) => (
        <div key={l} className="absolute rounded-xl border bg-card px-3 py-2" style={{ left: 20 + i * 182, top: 66, width: 172, ...rise(step === 5 ? t : 9, 0.6 + i * 0.25) }}>
          <p className="text-[10.5px] text-muted-foreground">{l}</p>
          <p className="text-[18px] font-semibold tabular">{v}</p>
        </div>
      ))}
      <div className="absolute grid grid-cols-4 gap-2.5" style={{ left: 20, top: 140, width: 720 }}>
        {PEOPLE.map((p, i) => (
          <div key={p.name} className="rounded-xl border bg-card p-3" style={rise(step === 5 ? t : 9, 1.6 + i * 0.2)}>
            <div className="flex items-center gap-2">
              <span className="relative size-8 rounded-full bg-gradient-to-br from-amber-400 to-rose-500">
                <span className={cn('absolute -right-0.5 -bottom-0.5 size-3 rounded-full border-2 border-card', p.status === 'Active' ? 'bg-cat-productive' : p.status === 'Idle' ? 'bg-amber-500' : 'bg-muted-foreground')} />
              </span>
              <span className="min-w-0">
                <span className="block truncate text-[12px] font-medium">{p.name}</span>
                <span className="block text-[10.5px] text-muted-foreground">{p.status}</span>
              </span>
            </div>
            <div className="mt-2 h-24 rounded-md bg-muted/60 p-2 text-[10px] text-muted-foreground">{p.app}</div>
            <span
              className={cn(
                'mt-2 flex h-7 items-center justify-center gap-1 rounded-md border text-[11px] font-medium',
                p.on ? 'border-primary bg-primary text-primary-foreground' : 'text-muted-foreground opacity-50',
                step === 6 && i === 0 && 'ring-[3px] ring-primary/35',
              )}
            >
              <MonitorPlay className="size-3.5" /> View live
            </span>
          </div>
        ))}
      </div>
    </>
  )
}

function Viewer({ step, t }: { step: number; t: number }) {
  return (
    <div className="absolute inset-0 z-20 bg-[#0b0b14] text-white duration-300 animate-in fade-in-0">
      <div className="flex h-14 items-center justify-between border-b border-white/10 px-5">
        <div className="flex items-center gap-2">
          <span className="rounded-full bg-red-500 px-2 py-0.5 text-[10px] font-semibold">Live now</span>
          <span className="text-[13px] font-semibold">Jamsheed K P</span>
          <span className="text-[11px] text-white/50">· JAMSHEED-LAPTOP</span>
        </div>
        <span className={cn('flex h-8 items-center gap-1.5 rounded-md bg-red-600 px-3 text-[12px] font-medium', step === 7 && t >= 5 && 'ring-[3px] ring-red-400/50')}>
          <Square className="size-3 fill-current" /> Stop stream
        </span>
      </div>
      <div className="mx-auto mt-5 w-[640px]" style={{ opacity: ramp(step === 6 ? t - 1.2 : 9, 0.3, 0.8) }}>
        <Shot seed={1} className="h-[340px] border-white/10" />
      </div>
      <div className="absolute inset-x-0 bottom-0 flex h-10 items-center gap-4 border-t border-white/10 px-5 text-[11px] text-white/60">
        <span>Ends automatically at 3:25 pm</span>
        <span className="ml-auto">Peer-to-peer · not recorded · access is audited</span>
      </div>
    </div>
  )
}

function TrayBadge({ t }: { t: number }) {
  return (
    <div className="absolute z-30 rounded-xl border bg-card p-3 text-foreground shadow-xl" style={{ right: 24, bottom: 56, ...rise(t, 0.4) }}>
      <p className="mb-2 text-[11px] text-muted-foreground">On the employee&apos;s computer</p>
      <div className="flex items-center gap-3 rounded-lg bg-[#111827] px-3 py-2 text-[11px] text-white/80">
        <span className="relative flex size-7 items-center justify-center rounded bg-[linear-gradient(135deg,#7c3aed,#6366f1)] text-white">
          <Activity className="size-4" />
          <span className="absolute -top-1 -right-1 size-3 animate-pulse rounded-full border-2 border-[#111827] bg-red-500" />
        </span>
        <span>Viewed by Admin since 3:10 pm</span>
      </div>
    </div>
  )
}

function SessionLog({ t }: { t: number }) {
  const rows = [
    ['Jamsheed K P', 'Admin', 'JAMSHEED-LAPTOP', '3:10 pm', '3:14 pm', '4m 12s'],
    ['Snigda', 'Admin', 'SNIGDA-PC', '11:02 am', '11:05 am', '2m 40s'],
    ['Abdul Basith', 'Team lead', 'BASITH-PC', 'Yesterday 4:30 pm', '4:41 pm', '10m 05s'],
  ]
  return (
    <div className="absolute rounded-xl border bg-card" style={{ left: 20, top: 20, width: 720 }}>
      <div className="flex items-baseline gap-3 px-4 pt-3 pb-2">
        <p className="text-[14px] font-semibold">Session log</p>
        <p className="text-[11px] text-muted-foreground">Every live view of people you manage, newest first. Video is never recorded.</p>
      </div>
      <div className="grid h-7 grid-cols-[1.2fr_0.8fr_1.1fr_1fr_0.7fr_0.6fr] items-center border-y bg-subtle/60 px-4 text-[10px] font-medium tracking-wide text-muted-foreground uppercase">
        <span>Employee</span>
        <span>Viewer</span>
        <span>Device</span>
        <span>Started</span>
        <span>Ended</span>
        <span className="text-right">Watched</span>
      </div>
      {rows.map((r, i) => (
        <div key={r[0]} className="grid h-10 grid-cols-[1.2fr_0.8fr_1.1fr_1fr_0.7fr_0.6fr] items-center border-b px-4 text-[11.5px] last:border-0" style={rise(t, 0.4 + i * 0.3)}>
          <span className="font-medium">{r[0]}</span>
          <span>{r[1]}</span>
          <span className="text-muted-foreground">{r[2]}</span>
          <span className="text-muted-foreground">{r[3]}</span>
          <span className="text-muted-foreground">{r[4]}</span>
          <span className="text-right tabular">{r[5]}</span>
        </div>
      ))}
    </div>
  )
}
