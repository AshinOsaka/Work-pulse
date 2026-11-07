import { Check, Copy, Mail, MonitorSmartphone, Plus, UserPlus, Users } from 'lucide-react'

import { cn } from '@/lib/utils'
import { Btn, Cursor, Field, Menu, Shell, Tabs, TitleCard, Toast, clickAt, navPoint, ramp, rise, typed, type Point } from './parts'

/**
 * The "Add employees" tutorial: People → Departments → New department, then Employees → Add employee with the
 * invite, the profile tabs, and registering a device for an enrolment code. Example names only.
 */

export const CAPTIONS = [
  'Add employees: everyone you track needs an employee record in WorkPulse.',
  'First create your departments: People → Departments → New department.',
  'Then open the Employees tab and click Add employee.',
  'Enter the full name and work email. Job title and employee ID are optional.',
  'Choose the department, team and manager. Employment type, hire date, time zone and location are optional.',
  'Turn on Invite to WorkPulse: the employee is emailed a link to set a password, used to sign in to the desktop agent.',
  'Click Add & send invite. The new employee appears in the list.',
  'Click a name to open the profile: details, attendance, activity, devices and permissions.',
  "Can't use email? On the profile's Devices tab, Register device and give them the enrolment code.",
  'Done. Next: install the desktop agent on each computer.',
]

const PEOPLE_TABS = ['Overview', 'Employees', 'Departments', 'Teams', 'Job roles']
const PROFILE_TABS = ['Overview', 'Attendance', 'Activity', 'Productivity', 'Screenshots', 'Tasks', 'Devices', 'Permissions']

// Add-employee dialog: origin and field centres (design pixels).
const D = { x: 250, y: 20 }
const col1 = 390
const col2 = 650
const row = (i: number) => 111 + i * 56

const P: Record<string, Point> = {
  people: navPoint('People'),
  tabEmployees: { x: 324, y: 129 },
  tabDepartments: { x: 412, y: 129 },
  topButton: { x: 880, y: 82 },
  deptName: { x: 480, y: 226 },
  deptCreate: { x: 548, y: 272 },
  name: { x: col1, y: row(0) },
  email: { x: col2, y: row(0) },
  title: { x: col1, y: row(1) },
  code: { x: col2, y: row(1) },
  dept: { x: col1, y: row(2) },
  team: { x: col2, y: row(2) },
  manager: { x: col1, y: row(3) },
  invite: { x: 737, y: 378 },
  submit: { x: 714, y: 488 },
  firstRow: { x: 309, y: 218 },
  devicesTab: { x: 696, y: 137 },
  register: { x: 856, y: 206 },
  rest: { x: 640, y: 420 },
}

export function AddEmployeesScene({ step, t }: { step: number; t: number }) {
  // Which page is showing.
  const page = step <= 0 ? 'employees' : step === 1 ? (t < 1.4 ? 'blank' : 'departments') : step <= 6 ? 'employees' : 'profile'
  const deptDialog = step === 1 && t >= 3.2
  const addDialog = (step === 2 && t >= 2.2) || (step >= 3 && step <= 5) || (step === 6 && t < 1.2)
  const added = step >= 6 && !(step === 6 && t < 1.2)

  let cursor: Point = P.rest
  let click = false
  if (step === 1) {
    cursor = t < 1.6 ? P.people : t < 2.6 ? P.tabDepartments : t < 3.4 ? P.topButton : t < 5 ? P.deptName : P.deptCreate
    click = clickAt(t, 0.9) || clickAt(t, 2.2) || clickAt(t, 3.1) || clickAt(t, 3.7) || clickAt(t, 5.4)
  } else if (step === 2) {
    cursor = t < 1.3 ? P.tabEmployees : P.topButton
    click = clickAt(t, 0.9) || clickAt(t, 2.0)
  } else if (step === 3) {
    cursor = t < 1.9 ? P.name : t < 3.4 ? P.email : t < 4.6 ? P.title : P.code
    click = clickAt(t, 0.3) || clickAt(t, 2.0) || clickAt(t, 3.5) || clickAt(t, 4.7)
  } else if (step === 4) {
    cursor = t < 2.4 ? P.dept : t < 4.4 ? P.team : P.manager
    click = clickAt(t, 0.5) || clickAt(t, 1.7) || clickAt(t, 2.6) || clickAt(t, 3.7) || clickAt(t, 4.6) || clickAt(t, 5.8)
  } else if (step === 5) {
    cursor = P.invite
    click = clickAt(t, 1.0)
  } else if (step === 6) {
    cursor = t < 1.4 ? P.submit : P.rest
    click = clickAt(t, 0.7)
  } else if (step === 7) {
    cursor = t < 1.2 ? P.firstRow : P.rest
    click = clickAt(t, 0.8)
  } else if (step === 8) {
    cursor = t < 1.6 ? P.devicesTab : P.register
    click = clickAt(t, 0.9) || clickAt(t, 2.4)
  }

  return (
    <div className="relative h-[540px] w-[960px] overflow-hidden bg-background text-foreground select-none">
      <Shell active={step >= 1 ? 'People' : 'Dashboard'}>
        {page === 'departments' && <DepartmentsPage t={t} created={step === 1 && t >= 5.6} />}
        {page === 'employees' && <EmployeesPage step={step} t={t} added={added} />}
        {page === 'profile' && <ProfilePage step={step} t={t} />}
      </Shell>

      {deptDialog && <DepartmentDialog t={t} />}
      {addDialog && <AddEmployeeDialog step={step} t={t} />}
      {step === 6 && t >= 1.3 && <Toast title="Jamsheed K P added" text="An invitation was sent to jamsheed@company.com." />}
      {step === 8 && t >= 2.6 && <EnrolmentDialog t={t - 2.6} />}

      {step === 0 && <TitleCard icon={UserPlus} title="Add employees" text="Create departments, add people and invite them to WorkPulse." />}
      {step === 9 && <TitleCard icon={Check} title="Employees added" text="Next: install the desktop agent on each computer." />}
      {step !== 0 && step !== 9 && <Cursor at={cursor} click={click} />}
    </div>
  )
}

function PageHead({ title, button, pulse }: { title: string; button: string; pulse?: boolean }) {
  return (
    <div className="mb-3 flex items-start justify-between">
      <div>
        <p className="text-[18px] font-semibold">People</p>
        <p className="text-[11px] text-muted-foreground">{title}</p>
      </div>
      <Btn primary focused={pulse}>
        <Plus className="size-3.5" /> {button}
      </Btn>
    </div>
  )
}

function DepartmentsPage({ t, created }: { t: number; created: boolean }) {
  const rows = [...(created ? [{ name: 'Visa', people: 0, fresh: true }] : []), { name: 'Ticketing', people: 6, fresh: false }, { name: 'Accounts', people: 3, fresh: false }]
  return (
    <div>
      <PageHead title="Departments, teams and reporting lines." button="New department" pulse={t > 2.6 && t < 3.4} />
      <Tabs tabs={PEOPLE_TABS} active="Departments" />
      <ul className="mt-4 divide-y rounded-xl border bg-card">
        {rows.map((r) => (
          <li key={r.name} className={cn('flex items-center justify-between px-4 py-3 text-[12px]', r.fresh && 'bg-primary/5 duration-500 animate-in fade-in-0 slide-in-from-top-1')}>
            <span className="font-medium">{r.name}</span>
            <span className="text-muted-foreground">{r.people} people</span>
          </li>
        ))}
      </ul>
    </div>
  )
}

const EMPLOYEES = [
  { name: 'Abdul Basith', email: 'basith@company.com', dept: 'Visa', role: 'Team lead' },
  { name: 'Snigda', email: 'snigda@company.com', dept: 'Ticketing', role: 'Travel consultant' },
  { name: 'Abhinav Krishna', email: 'abhinav@company.com', dept: 'Ticketing', role: 'Travel consultant' },
]

function EmployeesPage({ step, t, added }: { step: number; t: number; added: boolean }) {
  const list = added ? [{ name: 'Jamsheed K P', email: 'jamsheed@company.com', dept: 'Visa', role: 'Travel consultant' }, ...EMPLOYEES] : EMPLOYEES
  return (
    <div>
      <PageHead title="Employee directory." button="Add employee" pulse={step === 2 && t > 1.6 && t < 2.4} />
      <Tabs tabs={PEOPLE_TABS} active={step === 2 && t < 1.1 ? 'Departments' : 'Employees'} />
      <div className="mt-4 overflow-hidden rounded-xl border bg-card text-[12px]">
        <div className="grid grid-cols-[1.4fr_1.4fr_1fr_1fr] border-b bg-subtle/60 px-4 py-2 text-[10px] font-medium tracking-wide text-muted-foreground uppercase">
          <span>Name</span>
          <span>Email</span>
          <span>Department</span>
          <span>Job title</span>
        </div>
        {list.map((e, i) => (
          <div
            key={e.email}
            className={cn(
              'grid grid-cols-[1.4fr_1.4fr_1fr_1fr] items-center border-b px-4 py-2.5 last:border-0',
              added && i === 0 && 'bg-primary/5 duration-500 animate-in fade-in-0 slide-in-from-top-1',
            )}
          >
            <span className="flex items-center gap-2 font-medium">
              <span className="size-6 rounded-full bg-gradient-to-br from-amber-400 to-rose-500" />
              {e.name}
            </span>
            <span className="text-muted-foreground">{e.email}</span>
            <span>{e.dept}</span>
            <span className="text-muted-foreground">{e.role}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

function DepartmentDialog({ t }: { t: number }) {
  return (
    <div className="absolute inset-0 z-20 bg-black/30 duration-300 animate-in fade-in-0">
      <div className="absolute top-[140px] left-[330px] w-[300px] rounded-xl border bg-card p-4 shadow-xl duration-300 animate-in zoom-in-95">
        <p className="mb-3 text-[14px] font-semibold">New department</p>
        <Field label="Name" value={typed('Visa', t, 3.9, 4.6)} placeholder="e.g. Ticketing" focused={t >= 3.7 && t < 5.2} />
        <div className="mt-3 flex justify-end">
          <Btn primary focused={t >= 5.2}>Create department</Btn>
        </div>
      </div>
    </div>
  )
}

function AddEmployeeDialog({ step, t }: { step: number; t: number }) {
  const s3 = step === 3
  const s4 = step === 4
  const name = s3 ? typed('Jamsheed K P', t, 0.5, 1.6) : step > 3 ? 'Jamsheed K P' : ''
  const email = s3 ? typed('jamsheed@company.com', t, 2.1, 3.2) : step > 3 ? 'jamsheed@company.com' : ''
  const title = s3 ? typed('Travel consultant', t, 3.6, 4.4) : step > 3 ? 'Travel consultant' : ''
  const code = s3 ? typed('EMP-0042', t, 4.8, 5.4) : step > 3 ? 'EMP-0042' : ''
  const dept = s4 ? (t >= 1.7 ? 'Visa' : '') : step > 4 ? 'Visa' : ''
  const team = s4 ? (t >= 3.7 ? 'Visa desk' : '') : step > 4 ? 'Visa desk' : ''
  const manager = s4 ? (t >= 5.8 ? 'Abdul Basith' : '') : step > 4 ? 'Abdul Basith' : ''
  const invite = step === 5 ? t >= 1.1 : step > 5
  const focus = (key: string) => {
    if (s3) return key === (t < 1.9 ? 'name' : t < 3.4 ? 'email' : t < 4.6 ? 'title' : 'code')
    if (s4) return key === (t < 2.4 ? 'dept' : t < 4.4 ? 'team' : 'manager')
    return false
  }
  const at = (col: 0 | 1, r: number) => ({ left: 20 + col * 260, top: 52 + r * 56, width: 240 })
  return (
    <div className="absolute inset-0 z-20 bg-black/30 duration-300 animate-in fade-in-0">
      <div className="absolute rounded-xl border bg-card shadow-xl duration-300 animate-in zoom-in-95" style={{ left: D.x, top: D.y, width: 540, height: 500 }}>
        <p className="absolute top-4 left-5 text-[15px] font-semibold">Add employee</p>
        <div className="absolute" style={at(0, 0)}>
          <Field label="Full name" value={name} focused={focus('name')} />
        </div>
        <div className="absolute" style={at(1, 0)}>
          <Field label="Work email" value={email} focused={focus('email')} />
        </div>
        <div className="absolute" style={at(0, 1)}>
          <Field label="Job title" value={title} placeholder="e.g. Product Designer" focused={focus('title')} />
        </div>
        <div className="absolute" style={at(1, 1)}>
          <Field label="Employee ID" value={code} placeholder="Optional, e.g. EMP-0042" focused={focus('code')} />
        </div>
        <div className="absolute" style={at(0, 2)}>
          <Field label="Department" value={dept} placeholder="No department" focused={focus('dept')} select />
        </div>
        <div className="absolute" style={at(1, 2)}>
          <Field label="Team" value={team} placeholder="No team" focused={focus('team')} select />
        </div>
        <div className="absolute" style={at(0, 3)}>
          <Field label="Manager" value={manager} placeholder="No manager" focused={focus('manager')} select />
        </div>
        <div className="absolute" style={at(1, 3)}>
          <Field label="Employment type" value="Full time" select />
        </div>
        <div className="absolute" style={at(0, 4)}>
          <Field label="Hire date" value="" placeholder="dd-mm-yyyy" />
        </div>
        <div className="absolute" style={at(1, 4)}>
          <Field label="Timezone" value="Asia/Kolkata" select />
        </div>
        {s4 && t >= 0.6 && t < 1.7 && <Menu items={['Visa', 'Ticketing', 'Accounts']} active="Visa" style={{ left: 20, top: 200 }} />}
        {s4 && t >= 2.7 && t < 3.7 && <Menu items={['Visa desk', 'Front office']} active="Visa desk" style={{ left: 280, top: 200 }} />}
        {s4 && t >= 4.7 && t < 5.8 && <Menu items={['Abdul Basith', 'Snigda']} active="Abdul Basith" style={{ left: 20, top: 256 }} />}

        {/* Invite */}
        <div className={cn('absolute right-5 left-5 rounded-lg border bg-subtle p-3 transition-colors duration-300', invite && 'border-primary/50')} style={{ top: 334 }}>
          <div className="flex items-start gap-3">
            <Mail className="mt-0.5 size-4 text-muted-foreground" />
            <div className="flex-1">
              <p className="text-[12px] font-medium">Invite to WorkPulse</p>
              <p className="text-[11px] text-muted-foreground">Create a user account and email an invitation to set a password.</p>
            </div>
            <span className={cn('relative h-5 w-9 rounded-full transition-colors duration-300', invite ? 'bg-primary' : 'bg-muted-foreground/30')}>
              <span className={cn('absolute top-0.5 size-4 rounded-full bg-white shadow transition-all duration-300', invite ? 'left-[18px]' : 'left-0.5')} />
            </span>
          </div>
          {invite && (
            <div className="mt-2 flex items-center gap-3 border-t pt-2 duration-300 animate-in fade-in-0">
              <span className="text-[11px] text-muted-foreground">Role</span>
              <span className="rounded-md border bg-card px-2 py-1 text-[11px]">Employee</span>
              {step === 5 && t > 2 && (
                <span className="ml-auto flex items-center gap-1.5 text-[11px] text-primary" style={{ opacity: ramp(t, 2) }}>
                  <Mail className="size-3.5" /> Link to set a password → desktop agent sign-in
                </span>
              )}
            </div>
          )}
        </div>

        <div className="absolute right-5 flex gap-2" style={{ top: 452 }}>
          <Btn>Cancel</Btn>
          <Btn primary focused={step === 6}>{invite ? 'Add & send invite' : 'Add employee'}</Btn>
        </div>
      </div>
    </div>
  )
}

function ProfilePage({ step, t }: { step: number; t: number }) {
  // Step 7 walks through the tabs; step 8 sits on Devices.
  const tour = PROFILE_TABS.slice(0, 8)
  const lit = step === 7 ? tour[Math.min(tour.length - 1, Math.max(0, Math.floor((t - 1.4) / 0.7)))] : 'Devices'
  const active = step === 7 ? (t < 1.4 ? 'Overview' : lit) : t < 1.1 ? 'Overview' : 'Devices'
  return (
    <div>
      <div className="mb-4 flex items-center gap-3" style={rise(t + (step === 8 ? 9 : 0), 0.9)}>
        <span className="size-12 rounded-full bg-gradient-to-br from-amber-400 to-rose-500" />
        <div>
          <p className="text-[18px] font-semibold">Jamsheed K P</p>
          <p className="text-[11px] text-muted-foreground">Travel consultant · Visa · jamsheed@company.com</p>
        </div>
      </div>
      <Tabs tabs={PROFILE_TABS} active={active} />
      {active === 'Devices' ? (
        <div className="mt-4 rounded-xl border bg-card p-4">
          <div className="flex items-center justify-between">
            <p className="flex items-center gap-2 text-[13px] font-semibold">
              <MonitorSmartphone className="size-4 text-muted-foreground" /> Devices
            </p>
            <Btn primary focused={step === 8 && t > 1.6 && t < 2.6}>
              <Plus className="size-3.5" /> Register device
            </Btn>
          </div>
          <p className="mt-3 text-[12px] text-muted-foreground">Register a device to generate an enrolment code for the desktop agent.</p>
        </div>
      ) : (
        <div key={active} className="mt-4 grid grid-cols-3 gap-3 duration-300 animate-in fade-in-0">
          {[0, 1, 2].map((i) => (
            <div key={i} className="h-24 rounded-xl border bg-card p-3">
              <p className="text-[12px] font-medium">{active}</p>
              <div className="mt-3 h-2 w-2/3 rounded bg-muted" />
              <div className="mt-2 h-2 w-1/2 rounded bg-muted" />
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function EnrolmentDialog({ t }: { t: number }) {
  return (
    <div className="absolute inset-0 z-20 bg-black/30 duration-300 animate-in fade-in-0">
      <div className="absolute top-[150px] left-[320px] w-[380px] rounded-xl border bg-card p-5 shadow-xl duration-300 animate-in zoom-in-95">
        <p className="text-[15px] font-semibold">Enrolment code</p>
        <p className="mt-1 text-[11px] text-muted-foreground">Enter it in the desktop agent under Sign in → Use an enrolment code instead.</p>
        <div className="mt-4 flex items-center justify-between rounded-lg border bg-subtle px-3 py-2.5 font-mono text-[15px] tracking-widest" style={{ opacity: ramp(t, 0.3) }}>
          K7Q4-92XM-3PLA
          <Copy className="size-4 text-muted-foreground" />
        </div>
        <p className="mt-3 flex items-center gap-1.5 text-[11px] text-muted-foreground" style={{ opacity: ramp(t, 1.4) }}>
          <Users className="size-3.5" /> Give this code to the employee.
        </p>
      </div>
    </div>
  )
}
