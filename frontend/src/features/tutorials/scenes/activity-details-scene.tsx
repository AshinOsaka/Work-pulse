import { BarChart3, Check, Download, Gauge, List, TextSearch, UserRound, Users } from 'lucide-react'

import { cn } from '@/lib/utils'
import { Btn, Cursor, Shell, Tabs, TitleCard, Toast, clickAt, navPoint, ramp, rise, type Point } from './parts'

/**
 * The "Productivity & activity details" tutorial: Productivity → Breakdown (graph and list), the per-day details
 * window (category tabs, Idle, Keyboard & Mouse, date box), View more for window titles, and Export. Example data.
 */

export const CAPTIONS = [
  'Productivity & activity details: see exactly how each person spends the working day.',
  'Open Productivity → Breakdown. Pick Individual View or Team View, and a range.',
  'View by graph: productive, unproductive, neutral and idle time as stacked bars, day by day. Hover for exact hours.',
  'View by list: productive time and a bar with each category’s share. Click Details to open one day.',
  'The details window lists the productive, unproductive and neutral apps and websites, with the time in each.',
  'The Idle tab shows when an application stayed open with no keyboard or mouse input.',
  'Keyboard & Mouse counts key presses and mouse actions per 10 minutes — never what is typed. The Date box picks another day.',
  'On a person’s productivity page, Applications and websites shows which rule decided each category. View more shows window titles (when capture is on).',
  'Use Export to download the breakdown as a CSV file.',
  'Done. Next: check attendance against the required hours.',
]

const TABS = ['People', 'Breakdown', 'Departments & teams', 'Trends', 'Rules & work profiles']
const O = { x: 200, y: 44 }
const at = (x: number, y: number): Point => ({ x: O.x + x, y: O.y + y })
// The breakdown card starts at content (20, 140) → scene (220, 184).
const card = (x: number, y: number): Point => ({ x: 220 + x, y: 184 + y })
const DETAIL_TABS = [
  { label: 'Productive', count: 16, w: 100 },
  { label: 'Unproductive', count: 0, w: 110 },
  { label: 'Neutral', count: 7, w: 90 },
  { label: 'Idle', count: 2, w: 64 },
  { label: 'Keyboard & Mouse', count: -1, w: 130 },
]
const tabLeft = (i: number) => 226 + DETAIL_TABS.slice(0, i).reduce((s, x) => s + x.w + 4, 0)
const tabPoint = (i: number): Point => ({ x: tabLeft(i) + DETAIL_TABS[i].w / 2, y: 122 })

const P: Record<string, Point> = {
  productivity: navPoint('Productivity'),
  breakdownTab: at(110, 70),
  individual: at(75, 112),
  sevenDays: at(496, 112),
  graphBar: card(420, 200),
  listToggle: card(211, 30),
  details: card(660, 110),
  idleTab: tabPoint(3),
  keysTab: tabPoint(4),
  dateBox: { x: 690, y: 68 },
  viewMore: { x: 880, y: 258 },
  export: at(680, 112),
  rest: { x: 640, y: 480 },
}

const DAYS = ['Fri 31', 'Sat 1', 'Mon 3', 'Tue 4', 'Wed 5', 'Thu 6', 'Fri 7']
const BARS = DAYS.map((_, i) => ({ p: [5.6, 3.9, 6.1, 5.2, 6.4, 5.8, 6.0][i], u: [0.4, 0.2, 0.3, 0.6, 0.2, 0.3, 0.4][i], n: [1.1, 0.6, 0.9, 1.2, 0.8, 1.0, 0.9][i], idle: [0.6, 0.4, 0.5, 0.7, 0.4, 0.6, 0.5][i] }))

export function ActivityDetailsScene({ step, t }: { step: number; t: number }) {
  let cursor: Point = P.rest
  let click = false
  if (step === 1) {
    cursor = t < 1.4 ? P.productivity : t < 2.8 ? P.breakdownTab : t < 4.2 ? P.individual : P.sevenDays
    click = clickAt(t, 0.8) || clickAt(t, 2.2) || clickAt(t, 3.6) || clickAt(t, 5)
  } else if (step === 2) {
    cursor = t < 3 ? P.rest : P.graphBar
  } else if (step === 3) {
    cursor = t < 3 ? P.listToggle : P.details
    click = clickAt(t, 1.2) || clickAt(t, 6.6)
  } else if (step === 5) {
    cursor = P.idleTab
    click = clickAt(t, 1)
  } else if (step === 6) {
    cursor = t < 5.4 ? P.keysTab : P.dateBox
    click = clickAt(t, 0.8) || clickAt(t, 6.2)
  } else if (step === 7) {
    cursor = t < 4.6 ? P.rest : P.viewMore
    click = clickAt(t, 5.8)
  } else if (step === 8) {
    cursor = P.export
    click = clickAt(t, 1)
  }

  const onProductivity = !(step === 1 && t < 1.0)
  const onBreakdown = step >= 2 || (step === 1 && t >= 2.3)
  const list = step === 3 ? t >= 1.3 : step >= 4 && step !== 7
  const detailsOpen = (step === 3 && t >= 6.8) || step === 4 || step === 5 || step === 6
  const detailTab = step === 5 ? (t >= 1.1 ? 3 : 0) : step === 6 ? (t >= 0.9 ? 4 : 3) : 0
  const personPage = step === 7

  return (
    <div className="relative h-[540px] w-[960px] overflow-hidden bg-background text-foreground select-none">
      <Shell active={onProductivity && step >= 1 ? 'Productivity' : 'Dashboard'}>
        {onProductivity && step >= 1 && (
          <>
            <p className="absolute text-[18px] font-semibold" style={{ left: 20, top: 12 }}>
              {personPage ? 'Productivity · Jamsheed K P' : 'Productivity Breakdown'}
            </p>
            <p className="absolute text-[11px] text-muted-foreground" style={{ left: 20, top: 38 }}>
              {personPage ? 'Last 7 days' : 'Active working hours compared to idle time, to measure efficiency and productivity.'}
            </p>
            <div className="absolute" style={{ left: 20, top: 62, width: 720 }}>
              <Tabs tabs={TABS} active={personPage ? 'People' : onBreakdown ? 'Breakdown' : 'People'} />
            </div>
            {personPage ? <PersonPage t={t} /> : onBreakdown && <Breakdown step={step} t={t} list={list} />}
          </>
        )}
      </Shell>
      {detailsOpen && <DetailsDialog tab={detailTab} step={step} t={t} />}
      {step === 7 && t >= 6 && <TitlesDialog t={t - 6} />}
      {step === 8 && t >= 1.2 && <Toast title="Downloaded" text="productivity-breakdown-2026-11-01_2026-11-07.csv" />}
      {step === 0 && <TitleCard icon={Gauge} title="Productivity & activity details" text="How each person spends the working day — down to each app and window." />}
      {step === 9 && <TitleCard icon={Check} title="You know the details" text="Next: check attendance against the required hours." />}
      {step !== 0 && step !== 9 && step !== 4 && <Cursor at={cursor} click={click} />}
    </div>
  )
}

function Seg({ items, active, width }: { items: { label: string; icon?: typeof List }[]; active: string; width: number }) {
  return (
    <div className="flex rounded-lg bg-muted p-0.5">
      {items.map((i) => (
        <span key={i.label} className={cn('flex h-7 items-center justify-center gap-1.5 rounded-md text-[11.5px] transition-colors duration-300', i.label === active ? 'bg-background font-medium shadow-sm' : 'text-muted-foreground')} style={{ width }}>
          {i.icon && <i.icon className="size-3.5" />}
          {i.label}
        </span>
      ))}
    </div>
  )
}

function Breakdown({ step, t, list }: { step: number; t: number; list: boolean }) {
  const range = step === 1 && t < 5.1 ? 'Today' : '7 days'
  const max = 9
  return (
    <>
      <div className="absolute" style={{ left: 20, top: 96 }}>
        <Seg items={[{ label: 'Individual View', icon: UserRound }, { label: 'Team View', icon: Users }]} active="Individual View" width={108} />
      </div>
      <div className="absolute flex items-center gap-3" style={{ right: 20, top: 96 }}>
        <Seg items={['Today', '7 days', '14 days', '30 days'].map((label) => ({ label }))} active={range} width={52} />
        <Btn focused={step === 8 && t < 1.4}>
          <Download className="size-3.5" /> Export
        </Btn>
      </div>
      <div className="absolute rounded-xl border bg-card" style={{ left: 20, top: 140, width: 720, height: 352 }}>
        <div className="absolute" style={{ left: 16, top: 14 }}>
          <Seg items={[{ label: 'View by graph', icon: BarChart3 }, { label: 'View by list', icon: List }]} active={list ? 'View by list' : 'View by graph'} width={128} />
        </div>
        <span className="absolute flex h-8 items-center gap-2 rounded-md border px-2.5 text-[12px]" style={{ right: 16, top: 12, width: 220 }}>
          <span className="size-5 rounded-full bg-gradient-to-br from-amber-400 to-rose-500" /> Jamsheed K P
        </span>
        {list ? (
          <div className="absolute" style={{ left: 16, right: 16, top: 60 }}>
            <div className="grid h-7 grid-cols-[1.3fr_0.8fr_1.6fr_0.6fr] items-center border-b text-[10px] font-medium tracking-wide text-muted-foreground uppercase">
              <span>Name</span>
              <span>Productive</span>
              <span>Productivity %</span>
              <span className="text-right">Action</span>
            </div>
            {BARS.slice(-6).reverse().map((b, i) => {
              const total = b.p + b.u + b.n
              return (
                <div key={i} className="grid h-11 grid-cols-[1.3fr_0.8fr_1.6fr_0.6fr] items-center border-b text-[12px]" style={rise(step === 3 ? t : 9, 1.4 + i * 0.1)}>
                  <span>
                    <span className="block font-medium">Jamsheed K P</span>
                    <span className="block text-[10.5px] text-muted-foreground">{DAYS.slice(-6).reverse()[i]} Nov</span>
                  </span>
                  <span className="font-semibold text-cat-productive tabular">
                    {Math.floor(b.p)}:{String(Math.round((b.p % 1) * 60)).padStart(2, '0')}:00
                  </span>
                  <span className="mr-6 flex h-2 overflow-hidden rounded-full bg-muted">
                    <span className="bg-cat-productive" style={{ width: `${(100 * b.p) / total}%` }} />
                    <span className="bg-cat-neutral" style={{ width: `${(100 * b.n) / total}%` }} />
                    <span className="bg-cat-unproductive" style={{ width: `${(100 * b.u) / total}%` }} />
                  </span>
                  <span className="text-right">
                    <span className={cn('inline-flex h-7 items-center rounded-md border px-2.5 text-[11px] font-medium', step === 3 && i === 0 && t >= 5.6 && 'border-primary ring-[3px] ring-primary/25')}>Details</span>
                  </span>
                </div>
              )
            })}
          </div>
        ) : (
          <div className="absolute flex items-end gap-6" style={{ left: 50, right: 30, top: 70, height: 240 }}>
            {BARS.map((b, i) => (
              <div key={i} className="relative flex h-full flex-1 flex-col items-center justify-end">
                <div className="flex w-full max-w-12 origin-bottom flex-col justify-end" style={{ height: `${(100 * (b.p + b.u + b.n + b.idle)) / max}%`, transform: `scaleY(${ramp(step === 2 ? t : 9, 0.4 + i * 0.12, 0.7)})` }}>
                  <div className="rounded-t bg-muted-foreground/70" style={{ flex: b.idle }} />
                  <div className="bg-cat-neutral" style={{ flex: b.n }} />
                  <div className="bg-cat-unproductive" style={{ flex: b.u }} />
                  <div className="bg-cat-productive" style={{ flex: b.p }} />
                </div>
                <span className="absolute -bottom-5 text-[10px] text-muted-foreground">{DAYS[i]}</span>
                {step === 2 && i === 4 && t >= 3.6 && (
                  <div className="absolute bottom-full z-10 mb-2 w-36 rounded-lg border bg-popover p-2 text-[10.5px] shadow-lg">
                    <p className="mb-1 font-semibold">Wed 5 Nov</p>
                    <p className="flex justify-between"><span className="text-cat-productive">Productive</span> 6:24:00</p>
                    <p className="flex justify-between"><span className="text-cat-unproductive">Unproductive</span> 0:12:00</p>
                    <p className="flex justify-between"><span className="text-cat-neutral">Neutral</span> 0:48:00</p>
                    <p className="flex justify-between"><span className="text-muted-foreground">Idle</span> 0:24:00</p>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </>
  )
}

function DetailsDialog({ tab, step, t }: { tab: number; step: number; t: number }) {
  const date = step === 6 && t >= 6.4 ? '05-11-2026' : '06-11-2026'
  const dayLabel = step === 6 && t >= 6.4 ? 'Thursday, 5 November' : 'Friday, 6 November'
  return (
    <div className="absolute inset-0 z-20 bg-black/30 duration-300 animate-in fade-in-0">
      <div className="absolute rounded-xl border bg-card shadow-xl duration-300 animate-in zoom-in-95" style={{ left: 210, top: 40, width: 540, height: 460 }}>
        <p className="absolute text-[16px] font-semibold" style={{ left: 20, top: 16 }}>
          Jamsheed K P
        </p>
        <p className="absolute text-[11px] text-muted-foreground" style={{ left: 20, top: 40 }}>
          Activity details for {dayLabel}
        </p>
        <span className={cn('absolute flex h-8 items-center rounded-md border bg-card px-2.5 text-[12px] tabular', step === 6 && t >= 5.6 && 'border-primary ring-[3px] ring-primary/25')} style={{ right: 40, top: 12 }}>
          <span className="mr-2 text-[11px] text-muted-foreground">Date</span> {date}
        </span>
        <div className="absolute flex gap-1 border-b" style={{ left: 16, right: 16, top: 66 }}>
          {DETAIL_TABS.map((d, i) => (
            <span key={d.label} className={cn('-mb-px flex h-8 items-center justify-center gap-1.5 border-b-2 text-[11.5px] font-medium', i === tab ? 'border-primary text-foreground' : 'border-transparent text-muted-foreground')} style={{ width: d.w }}>
              {d.label}
              {d.count >= 0 && <span className="rounded-full bg-muted px-1.5 text-[10px]">{d.count}</span>}
            </span>
          ))}
        </div>
        <div className="absolute" style={{ left: 20, right: 20, top: 116, bottom: 16 }}>
          {tab === 0 && <UsageList step={step} t={t} />}
          {tab === 3 && <IdleList />}
          {tab === 4 && <InputChart t={step === 6 ? t - 0.9 : 9} />}
        </div>
      </div>
    </div>
  )
}

function UsageList({ step, t }: { step: number; t: number }) {
  const rows = [
    ['claude.ai', '2:41:10'],
    ['osakaconnect.com', '1:58:30'],
    ['Visual Studio Code', '1:12:45'],
    ['Microsoft Excel', '0:46:20'],
    ['chatgpt.com', '0:31:05'],
  ]
  const groups = step === 4 ? ['Productive', 'Neutral'] : ['Productive']
  return (
    <div>
      <p className="mb-2 text-[12px] font-semibold">Productive activities · 16 total</p>
      {rows.map(([name, time], i) => (
        <div key={name} className="flex items-center justify-between border-b py-2 text-[12px]" style={rise(step === 4 ? t : 9, 0.2 + i * 0.15)}>
          <span className="flex items-center gap-2">
            <span className="size-2 rounded-full bg-cat-productive" />
            {name}
          </span>
          <span className="font-medium text-cat-productive tabular">{time}</span>
        </div>
      ))}
      {groups.length > 1 && (
        <p className="mt-3 text-[11px] text-muted-foreground" style={{ opacity: ramp(t, 4) }}>
          Unproductive and Neutral tabs list their apps and websites the same way.
        </p>
      )}
    </div>
  )
}

function IdleList() {
  return (
    <table className="w-full text-[12px]">
      <thead>
        <tr className="border-b text-left text-[10px] tracking-wide text-muted-foreground uppercase">
          <th className="pb-2 font-medium">Application/Website</th>
          <th className="pb-2 font-medium">Idle start</th>
          <th className="pb-2 font-medium">Idle end</th>
          <th className="pb-2 text-right font-medium">Duration</th>
        </tr>
      </thead>
      <tbody>
        {[
          ['Microsoft Excel', '11:42 am', '11:58 am', '0:16:00'],
          ['osakaconnect.com', '3:05 pm', '3:13 pm', '0:08:00'],
        ].map((r) => (
          <tr key={r[0]} className="border-b duration-300 animate-in fade-in-0">
            <td className="py-2.5 font-medium">{r[0]}</td>
            <td className="py-2.5 text-muted-foreground">{r[1]}</td>
            <td className="py-2.5 text-muted-foreground">{r[2]}</td>
            <td className="py-2.5 text-right text-cat-neutral tabular">{r[3]}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

/** Keyboard (green) and mouse (blue) strokes per 10 minutes, drawn as two smooth areas. */
function InputChart({ t }: { t: number }) {
  const keys = [120, 380, 520, 300, 610, 450, 220, 480, 560, 330, 150, 400]
  const mouse = [60, 140, 190, 120, 210, 160, 90, 170, 200, 130, 70, 150]
  const W = 500
  const H = 190
  const pts = (arr: number[]) => arr.map((v, i) => [(i / (arr.length - 1)) * W, H - (v / 650) * H] as const)
  const path = (arr: number[]) => {
    const p = pts(arr)
    return p.reduce((d, [x, y], i) => {
      if (i === 0) return `M${x},${y}`
      const [px, py] = p[i - 1]
      const cx = (px + x) / 2
      return `${d} C${cx},${py} ${cx},${y} ${x},${y}`
    }, '')
  }
  return (
    <div>
      <p className="text-[12px] font-semibold">Keyboard &amp; mouse activity</p>
      <p className="mb-2 text-[10.5px] text-muted-foreground">Key presses and mouse actions in every 10 minutes. WorkPulse only counts them and never records what is typed.</p>
      <div className="mb-2 grid grid-cols-2 gap-2">
        <div className="rounded-lg border p-2">
          <p className="text-[15px] font-semibold tabular">4,520</p>
          <p className="text-[10.5px] text-muted-foreground">Keyboard strokes</p>
        </div>
        <div className="rounded-lg border p-2">
          <p className="text-[15px] font-semibold tabular">1,700</p>
          <p className="text-[10.5px] text-muted-foreground">Mouse strokes</p>
        </div>
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} className="h-[150px] w-full" preserveAspectRatio="none" style={{ clipPath: `inset(0 ${100 - 100 * ramp(t, 0.3, 1.6)}% 0 0)` }}>
        <path d={`${path(keys)} L${W},${H} L0,${H} Z`} fill="var(--cat-productive)" fillOpacity={0.15} />
        <path d={path(keys)} fill="none" stroke="var(--cat-productive)" strokeWidth={2.5} />
        <path d={`${path(mouse)} L${W},${H} L0,${H} Z`} fill="#0ea5e9" fillOpacity={0.12} />
        <path d={path(mouse)} fill="none" stroke="#0ea5e9" strokeWidth={2.5} />
      </svg>
    </div>
  )
}

function PersonPage({ t }: { t: number }) {
  const rows = [
    { name: 'claude.ai', cat: 'Productive', rule: 'Whole company rule · claude.ai', time: '11h 20m', sw: 'bg-cat-productive' },
    { name: 'osakaconnect.com', cat: 'Productive', rule: 'Department rule · osakaconnect.com', time: '9h 05m', sw: 'bg-cat-productive' },
    { name: 'mail.google.com', cat: 'Neutral', rule: 'Whole company rule · mail.google.com', time: '3h 40m', sw: 'bg-cat-neutral' },
    { name: 'youtube.com', cat: 'Unproductive', rule: 'Whole company rule · youtube.com', time: '0h 35m', sw: 'bg-cat-unproductive' },
  ]
  return (
    <div className="absolute rounded-xl border bg-card" style={{ left: 20, top: 100, width: 720, height: 300 }}>
      <p className="absolute text-[14px] font-semibold" style={{ left: 16, top: 12 }}>
        Applications and websites
      </p>
      <p className="absolute text-[11px] text-muted-foreground" style={{ left: 16, top: 34 }}>
        Which rule decided each category. Unclassified items count in no score.
      </p>
      <div className="absolute" style={{ left: 16, right: 16, top: 62 }}>
        <div className="grid h-7 grid-cols-[2.2fr_0.9fr_0.6fr_0.7fr] items-center border-b text-[10px] font-medium tracking-wide text-muted-foreground uppercase">
          <span>Application or website</span>
          <span>Category</span>
          <span className="text-right">Time</span>
          <span className="text-right">Action</span>
        </div>
        {rows.map((r, i) => (
          <div key={r.name} className="grid h-12 grid-cols-[2.2fr_0.9fr_0.6fr_0.7fr] items-center border-b text-[12px]" style={rise(t, 0.3 + i * 0.15)}>
            <span>
              <span className="block font-medium">{r.name}</span>
              <span className={cn('block text-[10.5px] text-muted-foreground transition-colors', t >= 2 && t < 4.5 && 'text-primary')}>{r.rule}</span>
            </span>
            <span className="flex items-center gap-1.5">
              <span className={cn('size-2.5 rounded-sm', r.sw)} />
              {r.cat}
            </span>
            <span className="text-right tabular">{r.time}</span>
            <span className="text-right">
              <span className={cn('inline-flex h-7 items-center rounded-md border px-2.5 text-[11px] font-medium', i === 0 && t >= 5 && 'border-primary ring-[3px] ring-primary/25')}>View more</span>
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}

function TitlesDialog({ t }: { t: number }) {
  const titles = [
    ['WMC website data collection - Claude', '3h 05m'],
    ['DoubleTick iframe CRM integration - Claude', '2h 40m'],
    ['Visa fee table cleanup - Claude', '1h 55m'],
    ['Forex rate widget - Claude', '1h 20m'],
  ]
  return (
    <div className="absolute inset-0 z-20 bg-black/30 duration-300 animate-in fade-in-0">
      <div className="absolute rounded-xl border bg-card p-5 shadow-xl duration-300 animate-in zoom-in-95" style={{ left: 250, top: 90, width: 460 }}>
        <p className="text-[15px] font-semibold">claude.ai</p>
        <p className="mb-3 flex items-center gap-1.5 text-[11px] text-muted-foreground">
          11h 20m total · <span className="size-2 rounded-sm bg-cat-productive" /> Productive
          <TextSearch className="ml-auto size-3.5" /> Window titles
        </p>
        {titles.map(([title, time], i) => (
          <div key={title} className="flex justify-between border-b py-2 text-[12px]" style={rise(t, 0.2 + i * 0.15)}>
            <span className="truncate pr-3">{title}</span>
            <span className="shrink-0 font-medium tabular">{time}</span>
          </div>
        ))}
      </div>
    </div>
  )
}
