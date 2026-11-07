import { Activity, AppWindow, Ban, Camera, Check, ChevronDown, Clock, MonitorPlay, ShieldCheck } from 'lucide-react'

import { cn } from '@/lib/utils'
import { Btn, Cursor, Menu, Shell, Tabs, TitleCard, Toast, clickAt, navPoint, rise, type Point } from './parts'

/**
 * The "Monitoring & privacy" tutorial: the policy switches on Settings → Workspace (activity, keyboard & mouse,
 * screenshots, live view), then the Monitoring & privacy page every employee can read. Labels match the app.
 */

export const CAPTIONS = [
  'Monitoring & privacy: you choose exactly what WorkPulse records, and every employee can see it.',
  'Open Settings → Workspace and scroll down to Activity tracking.',
  'Turn on Track application usage, and if needed Record websites (domain only) and Record window titles.',
  'Measure keyboard & mouse activity counts key presses and clicks, never which keys. Then click Save policy.',
  'Screenshots: turn on Capture screenshots and choose how often — one at a random moment per interval, only during a work session.',
  'Employees see a red badge on the tray icon whenever screenshots can be taken. Click Save policy.',
  'Live screen viewing: turn on Allow live viewing, set the maximum stream length, and Save policy.',
  'The Monitoring & privacy tab shows everyone what is recorded, when, why, for how long and who can see it.',
  'It also lists what is never collected: typed text, passwords, the content of e-mails and chats, and more.',
  'Done. Monitoring is set up, openly and fairly.',
]

const TABS = ['Profile', 'Workspace', 'Desktop agent', 'Monitoring & privacy', 'Customer systems', 'Appearance']

// Card sits at (20, 100) in the content box (200, 44): card point (x, y) = scene (220 + x, 144 + y).
const at = (x: number, y: number): Point => ({ x: 220 + x, y: 144 + y })
const ROW_TOP = 50
const ROW_H = 50
const switchAt = (i: number) => at(660, ROW_TOP + ROW_H * i + ROW_H / 2)

const P: Record<string, Point> = {
  settings: navPoint('Settings'),
  workspaceTab: { x: 307, y: 129 },
  privacyTab: { x: 522, y: 129 },
  save: at(640, 334),
  frequency: at(590, ROW_TOP + ROW_H * 1 + ROW_H / 2),
  length: at(590, ROW_TOP + ROW_H * 1 + ROW_H / 2),
  rest: { x: 640, y: 470 },
}

type CardKind = 'activity' | 'screenshots' | 'live'

export function MonitoringPrivacyScene({ step, t }: { step: number; t: number }) {
  let cursor: Point = P.rest
  let click = false
  if (step === 1) {
    cursor = t < 1.4 ? P.settings : P.workspaceTab
    click = clickAt(t, 0.8) || clickAt(t, 2.0)
  } else if (step === 2) {
    cursor = t < 2 ? switchAt(0) : t < 4.6 ? switchAt(1) : switchAt(2)
    click = clickAt(t, 1.0) || clickAt(t, 3.4) || clickAt(t, 6.0)
  } else if (step === 3) {
    cursor = t < 6 ? switchAt(3) : P.save
    click = clickAt(t, 1.2) || clickAt(t, 8.0)
  } else if (step === 4) {
    cursor = t < 3 ? switchAt(0) : P.frequency
    click = clickAt(t, 1.6) || clickAt(t, 3.6) || clickAt(t, 5.6)
  } else if (step === 5) {
    cursor = t < 3.8 ? P.rest : P.save
    click = clickAt(t, 4.6)
  } else if (step === 6) {
    cursor = t < 2.2 ? switchAt(0) : t < 4.4 ? P.length : P.save
    click = clickAt(t, 1.4) || clickAt(t, 3.2) || clickAt(t, 5.4)
  } else if (step === 7) {
    cursor = t < 1.6 ? P.privacyTab : P.rest
    click = clickAt(t, 0.9)
  }

  const onSettings = !(step === 1 && t < 1.0)
  const privacy = step >= 8 || (step === 7 && t >= 1.0)
  const card: CardKind = step <= 3 ? 'activity' : step <= 5 ? 'screenshots' : 'live'
  return (
    <div className="relative h-[540px] w-[960px] overflow-hidden bg-background text-foreground select-none">
      <Shell active={onSettings && step >= 1 ? 'Settings' : 'Dashboard'}>
        {onSettings && step >= 1 && (
          <>
            <p className="text-[18px] font-semibold">Settings</p>
            <p className="mb-3 text-[11px] text-muted-foreground">Manage your profile, workspace and preferences.</p>
            <Tabs tabs={TABS} active={privacy ? 'Monitoring & privacy' : step === 1 && t < 2.1 ? 'Profile' : 'Workspace'} />
            {privacy ? <PrivacyPage step={step} t={t} /> : step === 1 && t < 2.8 ? null : <PolicyCard key={card} kind={card} step={step} t={t} />}
          </>
        )}
      </Shell>
      {step === 3 && t >= 8.2 && <Toast title="Activity policy updated" />}
      {step === 5 && t >= 4.8 && <Toast title="Screenshot policy updated" />}
      {step === 6 && t >= 5.6 && <Toast title="Live view policy updated" />}
      {step === 5 && <TrayBadge t={t} />}
      {step === 0 && <TitleCard icon={ShieldCheck} title="Monitoring & privacy" text="Choose what is recorded — and show everyone exactly what that is." />}
      {step === 9 && <TitleCard icon={Check} title="Monitoring set up" text="Openly and fairly: everyone can see what is recorded." />}
      {step !== 0 && step !== 9 && <Cursor at={cursor} click={click} />}
    </div>
  )
}

function Toggle({ on }: { on: boolean }) {
  return (
    <span className={cn('relative block h-5 w-9 rounded-full transition-colors duration-300', on ? 'bg-primary' : 'bg-muted-foreground/30')}>
      <span className={cn('absolute top-0.5 size-4 rounded-full bg-white shadow transition-all duration-300', on ? 'left-[18px]' : 'left-0.5')} />
    </span>
  )
}

function Select({ value, focused }: { value: string; focused?: boolean }) {
  return (
    <span className={cn('flex h-8 w-40 items-center justify-between rounded-md border bg-card px-2.5 text-[12px]', focused && 'border-primary ring-[3px] ring-primary/25')}>
      {value}
      <ChevronDown className="size-3.5 opacity-60" />
    </span>
  )
}

interface RowDef {
  title: string
  text: string
  control: 'switch' | 'select'
  on?: boolean
  value?: string
  focused?: boolean
}

function PolicyCard({ kind, step, t }: { kind: CardKind; step: number; t: number }) {
  let title = ''
  let rows: RowDef[] = []
  let saveFocus = false
  if (kind === 'activity') {
    title = 'Activity tracking'
    const appsOn = step > 2 || (step === 2 && t >= 1.1)
    const sitesOn = step > 2 || (step === 2 && t >= 3.5)
    const titlesOn = step > 2 || (step === 2 && t >= 6.1)
    const keysOn = step === 3 && t >= 1.3
    saveFocus = step === 3 && t >= 7
    rows = [
      { title: 'Track application usage', text: 'Which applications are in the foreground, and for how long.', control: 'switch', on: appsOn },
      { title: 'Record websites (domain only)', text: 'The site, e.g. github.com — never the full address.', control: 'switch', on: sitesOn },
      { title: 'Record window titles', text: 'Never for password managers, private windows, messaging or e-mail.', control: 'switch', on: titlesOn },
      { title: 'Measure keyboard & mouse activity', text: 'Counts only — never which keys, your text, or where you click.', control: 'switch', on: keysOn },
      { title: 'Managed company devices', text: 'Use only on devices your organisation owns.', control: 'switch', on: false },
    ]
  } else if (kind === 'screenshots') {
    title = 'Screenshots'
    const on = step > 4 || (step === 4 && t >= 1.7)
    saveFocus = step === 5 && t >= 4
    rows = [
      { title: 'Capture screenshots', text: 'Employees see a red badge on the tray icon whenever screenshots can be taken.', control: 'switch', on },
      {
        title: 'Frequency',
        text: 'One screenshot at a random moment within each interval, only during an active work session.',
        control: 'select',
        value: step === 4 && t < 5.7 ? 'Every 30 minutes' : 'Every 10 minutes',
        focused: step === 4 && t >= 3.6 && t < 6,
      },
      { title: 'Working hours only', text: "Never capture outside these hours, in each employee's own timezone.", control: 'switch', on: false },
      { title: 'Keep screenshots for', text: 'Deleted automatically afterwards.', control: 'select', value: '30 days' },
    ]
  } else {
    title = 'Live screen viewing'
    const on = step === 6 && t >= 1.5
    saveFocus = step === 6 && t >= 4.6
    rows = [
      { title: 'Allow live viewing', text: 'On-demand live view of an employee’s screen during a work session.', control: 'switch', on },
      { title: 'Maximum stream length', text: 'A viewing session stops automatically after this time.', control: 'select', value: step === 6 && t >= 3.4 ? '15 minutes' : '10 minutes', focused: step === 6 && t >= 2.6 && t < 4.6 },
    ]
  }
  const Icon = kind === 'activity' ? AppWindow : kind === 'screenshots' ? Camera : MonitorPlay
  return (
    <div className="absolute rounded-xl border bg-card duration-500 animate-in fade-in-0 slide-in-from-bottom-4" style={{ left: 20, top: 100, width: 700, height: 364 }}>
      <p className="absolute top-4 left-5 flex items-center gap-2 text-[14px] font-semibold">
        <Icon className="size-4 text-muted-foreground" /> {title}
      </p>
      {rows.map((r, i) => (
        <div key={r.title} className="absolute flex items-center justify-between gap-4 border-b px-5" style={{ left: 0, right: 0, top: ROW_TOP + ROW_H * i, height: ROW_H }}>
          <div className="min-w-0">
            <p className="text-[12px] font-medium">{r.title}</p>
            <p className="truncate text-[11px] text-muted-foreground">{r.text}</p>
          </div>
          {r.control === 'switch' ? (
            <span className="mr-[11px] shrink-0">
              <Toggle on={Boolean(r.on)} />
            </span>
          ) : (
            <span className="shrink-0">
              <Select value={r.value ?? ''} focused={r.focused} />
            </span>
          )}
        </div>
      ))}
      {kind === 'screenshots' && step === 4 && t >= 3.8 && t < 5.7 && (
        <Menu items={['Every 5 minutes', 'Every 10 minutes', 'Every 15 minutes', 'Every 30 minutes']} active={t >= 5 ? 'Every 10 minutes' : 'Every 30 minutes'} style={{ left: 520, top: 128 }} />
      )}
      {kind === 'live' && step === 6 && t >= 2.7 && t < 3.5 && <Menu items={['5 minutes', '10 minutes', '15 minutes', '30 minutes']} active="15 minutes" style={{ left: 520, top: 128 }} />}
      <div className="absolute" style={{ right: 20, top: 318 }}>
        <Btn primary focused={saveFocus}>
          Save policy
        </Btn>
      </div>
    </div>
  )
}

/** Inset: the employee's taskbar with the red screenshot badge on the tray icon. */
function TrayBadge({ t }: { t: number }) {
  return (
    <div className="absolute z-30 rounded-xl border bg-card p-3 shadow-xl" style={{ left: 250, top: 400, ...rise(t, 0.4) }}>
      <p className="mb-2 text-[11px] text-muted-foreground">On the employee&apos;s computer</p>
      <div className="flex items-center gap-3 rounded-lg bg-[#111827] px-3 py-2 text-[11px] text-white/80">
        <span className="relative flex size-7 items-center justify-center rounded bg-[linear-gradient(135deg,#7c3aed,#6366f1)] text-white">
          <Activity className="size-4" />
          <span className="absolute -top-1 -right-1 size-3 animate-pulse rounded-full border-2 border-[#111827] bg-red-500" />
        </span>
        <span className="tabular">9:30</span>
      </div>
    </div>
  )
}

function PrivacyPage({ step, t }: { step: number; t: number }) {
  const local = step === 7 ? t - 1.0 : 9
  const sections = [
    { icon: Clock, title: 'Work time', status: 'Collected', tone: 'on' },
    { icon: AppWindow, title: 'Applications & websites', status: 'Collected', tone: 'on' },
    { icon: Camera, title: 'Screenshots', status: 'Collected', tone: 'on' },
    { icon: MonitorPlay, title: 'Live view', status: 'Only on request', tone: 'req' },
  ]
  const facts = ['What', 'When', 'Why', 'Kept for', 'Who can see it']
  const never = ['What you type — keys, words and messages', 'Passwords or other credentials', 'Clipboard contents', 'Microphone, camera or audio', 'The content of e-mails, chats, documents or files', 'Full web addresses (domain only)']
  if (step >= 8) {
    return (
      <div className="absolute rounded-xl border border-cat-productive/40 bg-cat-productive/5 p-5 duration-500 animate-in fade-in-0" style={{ left: 20, top: 108, width: 700 }}>
        <p className="mb-3 flex items-center gap-2 text-[15px] font-semibold">
          <Ban className="size-4 text-cat-productive" /> Never collected
        </p>
        <ul className="grid grid-cols-2 gap-x-6 gap-y-2.5 text-[12px]">
          {never.map((n, i) => (
            <li key={n} className="flex gap-2" style={rise(step === 8 ? t : 9, 0.4 + i * 0.5)}>
              <ShieldCheck className="mt-0.5 size-3.5 shrink-0 text-cat-productive" />
              {n}
            </li>
          ))}
        </ul>
      </div>
    )
  }
  return (
    <div className="absolute grid grid-cols-2 gap-3" style={{ left: 20, top: 108, width: 700 }}>
      {sections.map((s, i) => (
        <div key={s.title} className="rounded-xl border bg-card p-4" style={rise(local, 0.2 + i * 0.4)}>
          <div className="flex items-center justify-between">
            <p className="flex items-center gap-2 text-[13px] font-semibold">
              <s.icon className="size-4 text-muted-foreground" /> {s.title}
            </p>
            <span className={cn('rounded-full px-2 py-0.5 text-[10px] font-medium', s.tone === 'on' ? 'bg-cat-productive/15 text-cat-productive' : 'bg-primary/15 text-primary')}>{s.status}</span>
          </div>
          <div className="mt-2.5 space-y-1">
            {facts.map((f, j) => (
              <p key={f} className={cn('flex gap-3 text-[11px] transition-colors duration-300', i === 0 && local > 2 + j * 0.6 && local < 2.6 + j * 0.6 && 'text-primary')}>
                <span className="w-20 text-muted-foreground">{f}</span>
                <span className="h-2 w-28 translate-y-1 rounded bg-muted" />
              </p>
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}
