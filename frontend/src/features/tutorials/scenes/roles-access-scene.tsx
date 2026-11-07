import { Check, ChevronDown, Minus, MoreHorizontal, Search, ShieldCheck } from 'lucide-react'

import { cn } from '@/lib/utils'
import { Btn, Cursor, Shell, TitleCard, Toast, clickAt, navPoint, ramp, rise, type Point } from './parts'

/**
 * The "Roles & dashboard access" tutorial: Settings → Roles & permissions (the permission matrix, with the real
 * role → permission sets from the server, and the Members list) and Settings → Dashboard access (per-person
 * section visibility). Example people only.
 */

export const CAPTIONS = [
  'Roles & dashboard access: decide who can do what, and what each person sees.',
  'Settings → Roles & permissions. The permission matrix shows what each system role can do, from Company Admin to Employee.',
  'Permissions are checked by the server on every request. Data is limited by scope too: managers see their reporting line, team leads their teams.',
  'Under Members, find a person and choose their role. Role changes take effect immediately.',
  'The menu at the end of each row can reset two-step verification or sign the person out everywhere.',
  'Open Dashboard access and choose a person on the left (you can filter by role).',
  'Turn sections on or off — e.g. Screenshots, Reports or Live view — then Save changes.',
  'Hiding a section only hides it for that person. It never changes their role, permissions or what the system records.',
  'The change applies on their next sign-in or refresh.',
  'Done. Next: the Activity page.',
]

const TABS = [
  ['Profile', 38],
  ['Workspace', 60],
  ['Desktop agent', 78],
  ['Monitoring & privacy', 116],
  ['Customer systems', 98],
  ['Roles & permissions', 112],
  ['Dashboard access', 98],
  ['Appearance', 64],
] as const
const tabLeft = (i: number) => 20 + TABS.slice(0, i).reduce((s, [, w]) => s + w + 8, 0)

const O = { x: 200, y: 44 }
const at = (x: number, y: number): Point => ({ x: O.x + x, y: O.y + y })
const rowY = (i: number) => 248 + 40 * i
const personY = (i: number) => 220 + 40 * i
const switchY = (i: number) => 202 + 36 * i

const P: Record<string, Point> = {
  settings: navPoint('Settings'),
  rolesTab: at(tabLeft(5) + TABS[5][1] / 2, 74),
  accessTab: at(tabLeft(6) + TABS[6][1] / 2, 74),
  roleSelect: at(610, rowY(1)),
  roleOption: at(610, rowY(1) + 74),
  dots: at(715, rowY(1)),
  person: at(170, personY(1)),
  screenshotsSwitch: at(710, switchY(3)),
  reportsSwitch: at(710, switchY(5)),
  save: at(680, 462),
  rest: { x: 640, y: 480 },
}

// Real role → permission sets (backend app/auth/permissions.py): Company Admin, Manager, Team Lead, Employee.
const MATRIX: [string, boolean[]][] = [
  ['View employees', [true, true, true, false]],
  ['Manage employees', [true, false, false, false]],
  ['View activity', [true, true, true, false]],
  ['View screenshots', [true, true, true, false]],
  ['View live screens', [true, true, false, false]],
  ['Export reports', [true, true, false, false]],
  ['Manage policies', [true, false, false, false]],
]
const ROLES = ['Company Admin', 'Manager', 'Team Lead', 'Employee']

const MEMBERS = [
  { name: 'Abdul Basith', email: 'basith@company.com', role: 'Team lead' },
  { name: 'Jamsheed K P', email: 'jamsheed@company.com', role: 'Employee' },
  { name: 'Snigda', email: 'snigda@company.com', role: 'Travel consultant' },
  { name: 'Abhinav Krishna', email: 'abhinav@company.com', role: 'Travel consultant' },
]

const SECTIONS = [
  ['Activity', 'Application and website usage.'],
  ['Productivity', 'Time by category, focus and insights.'],
  ['Attendance', 'Sign-in, sign-out and required hours per day.'],
  ['Screenshots', 'Captured screenshots.'],
  ['Live view', 'On-demand live screen viewing.'],
  ['Reports', 'Workforce reports and exports.'],
  ['People', 'Employee directory and org structure.'],
]

export function RolesAccessScene({ step, t }: { step: number; t: number }) {
  let cursor: Point = P.rest
  let click = false
  if (step === 1) {
    cursor = t < 1.4 ? P.settings : P.rolesTab
    click = clickAt(t, 0.8) || clickAt(t, 2.2)
  } else if (step === 3) {
    cursor = t < 2.4 ? P.roleSelect : P.roleOption
    click = clickAt(t, 1.2) || clickAt(t, 3.2)
  } else if (step === 4) {
    cursor = P.dots
    click = clickAt(t, 1)
  } else if (step === 5) {
    cursor = t < 2 ? P.accessTab : P.person
    click = clickAt(t, 1) || clickAt(t, 3.6)
  } else if (step === 6) {
    cursor = t < 2.2 ? P.screenshotsSwitch : t < 4 ? P.reportsSwitch : P.save
    click = clickAt(t, 1) || clickAt(t, 2.8) || clickAt(t, 4.8)
  }

  const onSettings = !(step === 1 && t < 1.0)
  const tab = step >= 5 && !(step === 5 && t < 1.1) ? 'Dashboard access' : step >= 1 && !(step === 1 && t < 2.3) ? 'Roles & permissions' : 'Profile'
  return (
    <div className="relative h-[540px] w-[960px] overflow-hidden bg-background text-foreground select-none">
      <Shell active={onSettings && step >= 1 ? 'Settings' : 'Dashboard'}>
        {onSettings && step >= 1 && (
          <>
            <p className="absolute text-[18px] font-semibold" style={{ left: 20, top: 12 }}>
              Settings
            </p>
            <p className="absolute text-[11px] text-muted-foreground" style={{ left: 20, top: 38 }}>
              Manage your profile, workspace and preferences.
            </p>
            <div className="absolute border-b" style={{ left: 20, top: 64, width: 720, height: 22 }} />
            {TABS.map(([label, w], i) => (
              <span
                key={label}
                className={cn('absolute border-b-2 pb-1 text-center text-[10.5px] whitespace-nowrap transition-colors', label === tab ? 'border-primary font-medium text-foreground' : 'border-transparent text-muted-foreground')}
                style={{ left: tabLeft(i), top: 66, width: w }}
              >
                {label}
              </span>
            ))}
            {tab === 'Roles & permissions' && (step <= 2 ? <Matrix step={step} t={t} /> : <Members step={step} t={t} />)}
            {tab === 'Dashboard access' && <Access step={step} t={t} />}
          </>
        )}
      </Shell>
      {step === 6 && t >= 5 && <Toast title="Dashboard updated for Jamsheed K P" />}
      {step === 0 && <TitleCard icon={ShieldCheck} title="Roles & dashboard access" text="Who can do what — and what each person sees." />}
      {step === 9 && <TitleCard icon={Check} title="Access set up" text="Next: the Activity page." />}
      {step !== 0 && step !== 9 && step !== 2 && step !== 7 && step !== 8 && <Cursor at={cursor} click={click} />}
    </div>
  )
}

function Matrix({ step, t }: { step: number; t: number }) {
  return (
    <div className="absolute rounded-xl border bg-card" style={{ left: 20, top: 100, width: 720 }}>
      <div className="px-4 pt-3 pb-2">
        <p className="text-[14px] font-semibold">Permission matrix</p>
        <p className={cn('text-[11px] text-muted-foreground transition-colors', step === 2 && 'text-primary')}>
          What each system role can do. Permissions are enforced by the API on every request; data access is further limited by scope (managers see their reporting line,
          team leads their teams).
        </p>
      </div>
      <div className="grid h-7 grid-cols-[1.6fr_1fr_1fr_1fr_1fr] items-center border-y bg-subtle/60 px-4 text-[10px] font-medium tracking-wide text-muted-foreground uppercase">
        <span>Permission</span>
        {ROLES.map((r) => (
          <span key={r} className="text-center">
            {r}
          </span>
        ))}
      </div>
      {MATRIX.map(([perm, ticks], i) => (
        <div key={perm} className="grid h-8 grid-cols-[1.6fr_1fr_1fr_1fr_1fr] items-center border-b px-4 text-[12px] last:border-0" style={rise(step === 1 ? t - 2.3 : 9, 0.2 + i * 0.12)}>
          <span className="font-medium">{perm}</span>
          {ticks.map((ok, j) => (
            <span key={j} className="flex justify-center">
              {ok ? <Check className="size-4 text-cat-productive" /> : <Minus className="size-4 text-muted-foreground/40" />}
            </span>
          ))}
        </div>
      ))}
      {step === 2 && (
        <div className="grid grid-cols-2 gap-3 border-t p-3 text-[11.5px]">
          <p className="rounded-lg bg-primary/10 px-3 py-2" style={{ opacity: ramp(t, 0.5) }}>
            🔒 Checked by the server on <strong>every request</strong>
          </p>
          <p className="rounded-lg bg-primary/10 px-3 py-2" style={{ opacity: ramp(t, 3.5) }}>
            Managers → their reporting line · Team leads → their teams
          </p>
        </div>
      )}
    </div>
  )
}

function Members({ step, t }: { step: number; t: number }) {
  const changed = step > 3 || (step === 3 && t >= 3.3)
  return (
    <div className="absolute rounded-xl border bg-card" style={{ left: 20, top: 100, width: 720, height: 392 }}>
      <p className="absolute text-[14px] font-semibold" style={{ left: 16, top: 12 }}>
        Members
      </p>
      <p className="absolute text-[11px] text-muted-foreground" style={{ left: 16, top: 32 }}>
        Everyone with a WorkPulse account. Role changes take effect immediately.
      </p>
      <div className="absolute flex items-center gap-2" style={{ left: 16, top: 60 }}>
        <span className="flex h-8 w-56 items-center gap-2 rounded-md border px-2.5 text-[12px] text-muted-foreground">
          <Search className="size-3.5" /> Search members
        </span>
        <span className="flex h-8 w-40 items-center justify-between rounded-md border px-2.5 text-[12px] text-muted-foreground">
          All roles <ChevronDown className="size-3.5" />
        </span>
      </div>
      <div className="absolute" style={{ left: 0, right: 0, top: 100 }}>
        <div className="grid h-7 grid-cols-[1.8fr_0.7fr_0.9fr_1.3fr_0.3fr] items-center border-y bg-subtle/60 px-4 text-[10px] font-medium tracking-wide text-muted-foreground uppercase">
          <span>Member</span>
          <span>Status</span>
          <span>Last sign-in</span>
          <span>Role</span>
          <span />
        </div>
        {MEMBERS.map((m, i) => {
          const role = i === 1 && changed ? 'Travel consultant' : m.role
          return (
            <div key={m.name} className="grid h-10 grid-cols-[1.8fr_0.7fr_0.9fr_1.3fr_0.3fr] items-center border-b px-4 text-[11.5px]">
              <span>
                <span className="block font-medium">{m.name}</span>
                <span className="block text-[10px] text-muted-foreground">{m.email}</span>
              </span>
              <span>
                <span className="rounded-full bg-cat-productive/15 px-2 py-0.5 text-[10px] font-medium text-cat-productive">Active</span>
              </span>
              <span className="text-muted-foreground">Today</span>
              <span className={cn('flex h-7 w-44 items-center justify-between rounded-md border px-2 text-[11.5px]', step === 3 && i === 1 && t >= 1.2 && t < 3.6 && 'border-primary ring-[3px] ring-primary/25')}>
                {role} <ChevronDown className="size-3.5 opacity-60" />
              </span>
              <span className={cn('flex size-7 items-center justify-center rounded-md', step === 4 && i === 1 && 'bg-accent')}>
                <MoreHorizontal className="size-4" />
              </span>
            </div>
          )
        })}
      </div>
      {step === 3 && t >= 1.3 && t < 3.3 && (
        <div className="absolute z-10 w-44 rounded-lg border bg-popover p-1 text-[12px] shadow-lg" style={{ left: 430, top: rowY(1) - 100 + 20 }}>
          {['Employee', 'Travel consultant', 'Team lead'].map((r) => (
            <p key={r} className={cn('rounded px-2 py-1.5', r === 'Travel consultant' && 'bg-accent font-medium')}>
              {r}
            </p>
          ))}
        </div>
      )}
      {step === 4 && t >= 1.1 && (
        <div className="absolute z-10 w-56 rounded-lg border bg-popover p-1 text-[12px] shadow-lg duration-200 animate-in fade-in-0" style={{ left: 470, top: rowY(1) - 100 + 18 }}>
          <p className="rounded px-2 py-1.5">Reset two-step verification</p>
          <p className="rounded px-2 py-1.5">Sign out everywhere</p>
        </div>
      )}
    </div>
  )
}

function Access({ step, t }: { step: number; t: number }) {
  const picked = step > 5 || (step === 5 && t >= 3.7)
  const shotsOff = step > 6 || (step === 6 && t >= 1.1)
  const reportsOff = step > 6 || (step === 6 && t >= 2.9)
  return (
    <>
      <div className="absolute rounded-xl border bg-card" style={{ left: 20, top: 100, width: 300, height: 392 }}>
        <p className="absolute text-[14px] font-semibold" style={{ left: 16, top: 12 }}>
          Choose a person
        </p>
        <p className="absolute text-[11px] text-muted-foreground" style={{ left: 16, top: 32 }}>
          Filter by role, then pick who to configure.
        </p>
        <span className="absolute flex h-8 items-center justify-between rounded-md border px-2.5 text-[12px] text-muted-foreground" style={{ left: 16, top: 58, width: 268 }}>
          All roles <ChevronDown className="size-3.5" />
        </span>
        {MEMBERS.map((m, i) => (
          <div
            key={m.name}
            className={cn('absolute flex items-center gap-2 rounded-lg px-2 text-[12px] transition-colors', picked && i === 1 && 'bg-primary/10 text-primary')}
            style={{ left: 8, right: 8, top: 100 + 40 * i, height: 36 }}
          >
            <span className="size-6 rounded-full bg-gradient-to-br from-amber-400 to-rose-500" />
            <span>
              <span className="block font-medium">{m.name}</span>
              <span className="block text-[10px] text-muted-foreground">{i === 1 ? 'Travel consultant' : m.role}</span>
            </span>
          </div>
        ))}
      </div>
      <div className="absolute rounded-xl border bg-card" style={{ left: 330, top: 100, width: 410, height: 392 }}>
        <p className="absolute text-[14px] font-semibold" style={{ left: 16, top: 12 }}>
          Dashboard sections
        </p>
        <p className={cn('absolute text-[10.5px] leading-snug text-muted-foreground transition-colors', step === 7 && 'text-primary')} style={{ left: 16, right: 16, top: 32 }}>
          {picked
            ? 'What Jamsheed K P sees on their dashboard. Turning a section off only hides it for them — it never changes their role, permissions or what the system records.'
            : 'Select a person to show or hide sections of their dashboard.'}
        </p>
        {picked &&
          SECTIONS.map(([label, hint], i) => {
            const off = (label === 'Screenshots' && shotsOff) || (label === 'Reports' && reportsOff)
            return (
              <div key={label} className="absolute flex items-center justify-between border-b px-4" style={{ left: 0, right: 0, top: 84 + 36 * i, height: 36, ...rise(step === 5 ? t - 3.7 : 9, i * 0.06) }}>
                <span>
                  <span className={cn('block text-[12px] font-medium', off && 'text-muted-foreground')}>{label}</span>
                  <span className="block text-[10px] text-muted-foreground">{hint}</span>
                </span>
                <span className={cn('relative h-5 w-9 rounded-full transition-colors duration-300', off ? 'bg-muted-foreground/30' : 'bg-primary')}>
                  <span className={cn('absolute top-0.5 size-4 rounded-full bg-white shadow transition-all duration-300', off ? 'left-0.5' : 'left-[18px]')} />
                </span>
              </div>
            )
          })}
        {picked && (
          <>
            <p className={cn('absolute text-[10.5px] text-muted-foreground', step === 8 && 'text-primary')} style={{ left: 16, top: 352 }}>
              Applies on their next sign-in or refresh.
            </p>
            <div className="absolute" style={{ right: 16, top: 346 }}>
              <Btn primary focused={step === 6 && t >= 4.2}>
                Save changes
              </Btn>
            </div>
          </>
        )}
      </div>
    </>
  )
}
