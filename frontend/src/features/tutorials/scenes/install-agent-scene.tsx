import { Activity, Check, CheckCircle2, Download, FileDown, Folder, Laptop, Monitor, ShieldAlert } from 'lucide-react'

import { cn } from '@/lib/utils'
import { Btn, Cursor, Field, Shell, TitleCard, Toast, clickAt, ramp, typed, type Point } from './parts'

/**
 * The "Install the desktop agent" tutorial: download from the top bar, run the installer (SmartScreen → Run
 * anyway), sign in, accept the permissions and start a work session. Windows screens are simplified drawings.
 */

export const CAPTIONS = [
  "Install the desktop agent: it runs on each employee's Windows computer and records work time.",
  "On the employee's computer, open WorkPulse and click Download agent in the top bar.",
  'Click Windows. The installer downloads and a message confirms when it is complete.',
  'Open the installer from Downloads. If SmartScreen warns, click More info → Run anyway.',
  'No administrator rights needed. Click Install and keep “Start WorkPulse” ticked. It also starts with Windows.',
  'Sign in with the work email and the password from the invitation, or use an enrolment code instead.',
  'Review the monitoring permissions, tick to accept, then click Accept & sign in.',
  'Click Start work session. The tray icon shows the agent is running; activity soon appears in WorkPulse.',
  'At the end of the day, click Stop work session.',
  'Done. Next: set your work schedule in Settings.',
]

const P: Record<string, Point> = {
  download: { x: 884, y: 20 },
  windows: { x: 291, y: 318 },
  file: { x: 420, y: 194 },
  moreInfo: { x: 407, y: 337 },
  runAnyway: { x: 613, y: 395 },
  install: { x: 658, y: 322 },
  finish: { x: 658, y: 363 },
  email: { x: 480, y: 241 },
  password: { x: 480, y: 306 },
  continue: { x: 480, y: 378 },
  accept: { x: 325, y: 337 },
  acceptBtn: { x: 480, y: 373 },
  start: { x: 480, y: 319 },
  tray: { x: 896, y: 522 },
  rest: { x: 640, y: 420 },
}

export function InstallAgentScene({ step, t }: { step: number; t: number }) {
  let cursor: Point = P.rest
  let click = false
  if (step === 1) {
    cursor = P.download
    click = clickAt(t, 2.2)
  } else if (step === 2) {
    cursor = P.windows
    click = clickAt(t, 0.8)
  } else if (step === 3) {
    cursor = t < 2.6 ? P.file : t < 4.4 ? P.moreInfo : P.runAnyway
    click = clickAt(t, 1.4) || clickAt(t, 1.7) || clickAt(t, 3.8) || clickAt(t, 5.6)
  } else if (step === 4) {
    cursor = t < 5.6 ? P.install : P.finish
    click = clickAt(t, 1.4) || clickAt(t, 7.4)
  } else if (step === 5) {
    cursor = t < 2.8 ? P.email : t < 5.2 ? P.password : P.continue
    click = clickAt(t, 0.6) || clickAt(t, 3) || clickAt(t, 7.4)
  } else if (step === 6) {
    cursor = t < 2.8 ? P.accept : P.acceptBtn
    click = clickAt(t, 2) || clickAt(t, 4.4)
  } else if (step === 7) {
    cursor = t < 2.6 ? P.start : P.tray
    click = clickAt(t, 1.2)
  } else if (step === 8) {
    cursor = P.start
    click = clickAt(t, 1.4)
  }

  return (
    <div className="relative h-[540px] w-[960px] overflow-hidden bg-background text-foreground select-none">
      {step <= 2 ? <BrowserPart step={step} t={t} /> : <Desktop step={step} t={t} />}
      {step === 0 && <TitleCard icon={Laptop} title="Install the desktop agent" text="Download, install, sign in and start a work session." />}
      {step === 9 && <TitleCard icon={Check} title="Agent installed" text="Next: set your work schedule in Settings." />}
      {step !== 0 && step !== 9 && <Cursor at={cursor} click={click} />}
    </div>
  )
}

function BrowserPart({ step, t }: { step: number; t: number }) {
  const open = step === 2 || (step === 1 && t >= 2.4)
  const pct = step === 2 ? Math.round(100 * ramp(t, 1.0, 2.2)) : 0
  const done = step === 2 && t >= 3.3
  return (
    <>
      <Shell
        active="Dashboard"
        topRight={
          <span className={cn('flex size-7 items-center justify-center rounded-md text-muted-foreground transition-shadow', step === 1 && t > 1.2 && 'bg-primary/10 text-primary ring-[3px] ring-primary/25')}>
            <Download className="size-4" />
          </span>
        }
      >
        <div className="space-y-3">
          <div className="h-6 w-56 rounded bg-muted" />
          <div className="grid grid-cols-4 gap-3">
            {[0, 1, 2, 3].map((i) => (
              <div key={i} className="h-20 rounded-xl border bg-card" />
            ))}
          </div>
          <div className="h-56 rounded-xl border bg-card" />
        </div>
      </Shell>
      {step === 1 && t > 1.2 && t < 2.4 && (
        <span className="absolute top-12 right-[50px] z-20 rounded-md bg-foreground px-2 py-1 text-[11px] text-background">Download agent</span>
      )}
      {open && (
        <div className="absolute inset-0 z-20 bg-black/35 duration-300 animate-in fade-in-0">
          <div className="absolute top-[90px] left-[180px] w-[600px] overflow-hidden rounded-xl border bg-card shadow-2xl duration-300 animate-in zoom-in-95">
            <div className="flex items-center gap-3 bg-[linear-gradient(135deg,#5b3df5,#2563eb)] px-5 py-4 text-white">
              <span className="flex size-10 items-center justify-center rounded-xl bg-white/15 ring-1 ring-white/25">
                <Monitor className="size-5" />
              </span>
              <div>
                <p className="text-[16px] font-semibold">Desktop agent</p>
                <p className="text-[12px] text-white/80">WorkPulse for Windows · version 0.8.2</p>
              </div>
            </div>
            <div className="grid grid-cols-3 gap-3 p-5">
              {['Windows', 'macOS', 'Linux'].map((os) => (
                <div key={os} className="flex flex-col items-center gap-3 rounded-xl border p-4">
                  <span className={cn('flex size-14 items-center justify-center rounded-xl', os === 'Windows' ? 'bg-[#0078D4]/10 text-[#0078D4]' : 'bg-muted text-muted-foreground')}>
                    <Monitor className="size-7" />
                  </span>
                  <p className="text-[13px] font-semibold">{os}</p>
                  {os === 'Windows' ? (
                    <span className="flex h-8 w-full items-center justify-center gap-1.5 rounded-md bg-foreground text-[12px] font-medium text-background">
                      {done ? (
                        <>
                          <CheckCircle2 className="size-3.5" /> Downloaded
                        </>
                      ) : pct > 0 ? (
                        `${pct}%`
                      ) : (
                        <>
                          <Download className="size-3.5" /> Windows
                        </>
                      )}
                    </span>
                  ) : (
                    <span className="rounded-full bg-muted px-3 py-1 text-[11px] text-muted-foreground">Coming soon</span>
                  )}
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
      {done && <Toast title="Download complete" text="Open WorkPulseAgentSetup-0.8.2.exe from your Downloads folder to install the agent." />}
    </>
  )
}

function Desktop({ step, t }: { step: number; t: number }) {
  const working = (step === 7 && t >= 1.3) || (step === 8 && t < 1.5)
  return (
    <div className="absolute inset-0 bg-[linear-gradient(135deg,#1e3a8a,#4338ca_55%,#0e7490)]">
      {step === 3 && <Downloads t={t} />}
      {step === 4 && <Installer t={t} />}
      {(step === 5 || step === 6) && <AgentSignIn step={step} t={t} />}
      {(step === 7 || step === 8) && <AgentMain working={working} t={step === 7 ? t - 1.3 : 9 + t} />}
      {/* Taskbar */}
      <div className="absolute inset-x-0 bottom-0 flex h-9 items-center justify-end gap-3 bg-black/55 px-4 text-[11px] text-white/80 backdrop-blur">
        {step >= 5 && (
          <span className="relative flex size-6 items-center justify-center rounded bg-[linear-gradient(135deg,#7c3aed,#6366f1)] text-white">
            <Activity className="size-3.5" />
            {step === 7 && t > 2.8 && <span className="absolute -inset-1 animate-ping rounded-md border-2 border-white/80" />}
          </span>
        )}
        <span className="tabular">9:30</span>
      </div>
      {step === 7 && t > 3 && (
        <span className="absolute right-3 bottom-12 rounded-md bg-black/70 px-2 py-1 text-[11px] text-white" style={{ opacity: ramp(t, 3) }}>
          WorkPulse · Working
        </span>
      )}
    </div>
  )
}

function Win({ title, x, y, w, children }: { title: string; x: number; y: number; w: number; children: React.ReactNode }) {
  return (
    <div className="absolute overflow-hidden rounded-lg border bg-card shadow-2xl duration-300 animate-in fade-in-0 zoom-in-95" style={{ left: x, top: y, width: w }}>
      <div className="flex h-8 items-center justify-between border-b bg-subtle px-3 text-[11px] text-muted-foreground">
        <span>{title}</span>
        <span className="tracking-[6px]">–▢✕</span>
      </div>
      {children}
    </div>
  )
}

function Downloads({ t }: { t: number }) {
  const warn = t >= 1.9
  const more = t >= 3.9
  return (
    <>
      <Win title="Downloads" x={200} y={140} w={420}>
        <div className="flex">
          <div className="w-28 space-y-1 border-r p-2 text-[11px] text-muted-foreground">
            <p className="flex items-center gap-1.5 rounded bg-primary/10 px-2 py-1 text-primary">
              <Folder className="size-3.5" /> Downloads
            </p>
            <p className="px-2 py-1">Documents</p>
          </div>
          <div className="flex-1 p-2">
            <p className={cn('flex items-center gap-2 rounded px-2 py-1.5 text-[12px]', t > 1.2 && 'bg-primary/10')}>
              <FileDown className="size-4 text-primary" /> WorkPulseAgentSetup-0.8.2.exe
            </p>
          </div>
        </div>
      </Win>
      {warn && (
        <div className="absolute top-[230px] left-[360px] w-[420px] bg-[#1d5fb8] p-5 text-white shadow-2xl duration-300 animate-in fade-in-0">
          <p className="flex items-center gap-2 text-[18px] font-semibold">
            <ShieldAlert className="size-5" /> Windows protected your PC
          </p>
          <p className="mt-2 text-[12px] text-white/85">Microsoft Defender SmartScreen prevented an unrecognised app from starting.</p>
          {more ? (
            <p className="mt-2 text-[12px] text-white/85">App: WorkPulseAgentSetup-0.8.2.exe</p>
          ) : (
            <p className="mt-2 text-[12px] underline">More info</p>
          )}
          <div className="mt-8 flex justify-end gap-2">
            {more && <span className={cn('border border-white/70 px-4 py-1.5 text-[12px]', t > 4.6 && 'bg-white/20')}>Run anyway</span>}
            <span className="border border-white/70 px-4 py-1.5 text-[12px]">Don&apos;t run</span>
          </div>
        </div>
      )}
    </>
  )
}

function Installer({ t }: { t: number }) {
  const installing = t >= 1.5 && t < 5.5
  const finished = t >= 5.5
  const pct = Math.round(100 * ramp(t, 1.5, 3.8))
  return (
    <Win title="Setup - WorkPulse" x={250} y={110} w={460}>
      <div className="flex">
        <div className="w-28 bg-[linear-gradient(180deg,#5b3df5,#2563eb)]" />
        <div className="flex-1 p-5">
          {!installing && !finished && (
            <>
              <p className="text-[14px] font-semibold">Ready to install</p>
              <p className="mt-2 text-[12px] text-muted-foreground">Setup will install WorkPulse for your Windows account. No administrator rights are needed.</p>
            </>
          )}
          {installing && (
            <>
              <p className="text-[14px] font-semibold">Installing</p>
              <div className="mt-4 h-2.5 rounded bg-muted">
                <div className="h-full rounded bg-[#06b6d4]" style={{ width: `${pct}%` }} />
              </div>
            </>
          )}
          {finished && (
            <>
              <p className="text-[14px] font-semibold">Completing the WorkPulse Setup</p>
              <p className="mt-2 flex items-center gap-2 text-[12px]">
                <span className="flex size-4 items-center justify-center rounded border border-primary bg-primary text-primary-foreground">
                  <Check className="size-3" />
                </span>
                Start WorkPulse
              </p>
              <p className="mt-2 text-[11px] text-muted-foreground" style={{ opacity: ramp(t, 6.2) }}>
                WorkPulse also starts by itself when you sign in to Windows.
              </p>
            </>
          )}
          <div className="mt-24 flex justify-end">
            <Btn primary focused={(t > 0.8 && t < 1.6) || (t > 6.8 && t < 7.6)}>{finished ? 'Finish' : 'Install'}</Btn>
          </div>
        </div>
      </div>
    </Win>
  )
}

function AgentSignIn({ step, t }: { step: number; t: number }) {
  if (step === 5) {
    return (
      <Win title="Sign in to WorkPulse" x={330} y={110} w={300}>
        <div className="space-y-3 p-4">
          <p className="text-[11px] text-muted-foreground">Sign in with your WorkPulse account to register this computer.</p>
          <Field label="Work email" value={typed('jamsheed@company.com', t, 0.9, 2.5)} focused={t < 2.8} />
          <Field label="Password" value={'•'.repeat(Math.round(10 * ramp(t, 3.3, 1.2)))} focused={t >= 2.8 && t < 5.2} />
          <p className={cn('text-[11px] text-primary underline transition-opacity', t > 4.6 && t < 6.8 && 'animate-pulse')}>Use an enrolment code instead</p>
          <Btn primary focused={t > 7} className="w-full justify-center">
            Continue
          </Btn>
        </div>
      </Win>
    )
  }
  const items = ['Work time', 'Applications', 'Websites', 'Screenshots', 'Live view', 'Keyboard & mouse']
  const accepted = t >= 2.1
  return (
    <Win title="Sign in to WorkPulse" x={300} y={60} w={360}>
      <div className="p-4">
        <p className="text-[11px] text-muted-foreground">One more step — your monitoring permissions.</p>
        <ul className="mt-2 space-y-1 text-[11.5px]">
          {items.map((i) => (
            <li key={i} className="rounded border px-2 py-1">
              <span className="font-medium">{i}</span>
            </li>
          ))}
        </ul>
        <p className="mt-3 flex items-center gap-2 text-[11.5px]">
          <span className={cn('flex size-4 items-center justify-center rounded border transition-colors', accepted && 'border-primary bg-primary text-primary-foreground')}>
            {accepted && <Check className="size-3" />}
          </span>
          I accept all of the above and consent to this monitoring.
        </p>
        <Btn primary focused={t > 4.2} className="mt-3 w-full justify-center">
          Accept &amp; sign in
        </Btn>
      </div>
    </Win>
  )
}

function AgentMain({ working, t }: { working: boolean; t: number }) {
  // Shown like the agent's own timer (h:mm:ss); sped up so it visibly runs.
  const secs = working ? Math.floor(Math.max(0, t) * 40) : 0
  const duration = `${Math.floor(secs / 3600)}:${String(Math.floor((secs % 3600) / 60)).padStart(2, '0')}:${String(secs % 60).padStart(2, '0')}`
  return (
    <Win title="WorkPulse" x={330} y={120} w={300}>
      <div className="space-y-3 p-4">
        <p className="text-[12px] font-medium">Jamsheed K P</p>
        <div className="rounded-lg border p-3">
          <p className="text-[10px] font-semibold tracking-wide text-muted-foreground">WORK SESSION</p>
          <p className={cn('mt-1 text-[20px] font-semibold tabular', working ? 'text-cat-productive' : 'text-muted-foreground')}>
            {duration}
          </p>
          <p className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
            <span className={cn('size-2 rounded-full', working ? 'bg-cat-productive' : 'bg-muted-foreground/50')} />
            {working ? 'Working' : 'Not working'}
          </p>
        </div>
        <Btn primary={!working} className={cn('w-full justify-center', working && 'border-destructive text-destructive')}>
          {working ? 'Stop work session' : 'Start work session'}
        </Btn>
      </div>
    </Win>
  )
}
