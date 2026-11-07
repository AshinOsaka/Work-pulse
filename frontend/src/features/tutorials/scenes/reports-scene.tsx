import { Check, Download, Eye, FileChartColumn, FileSpreadsheet, FileText, Trash2 } from 'lucide-react'

import { cn } from '@/lib/utils'
import { Btn, Cursor, Field, Shell, TitleCard, Toast, clickAt, navPoint, ramp, rise, type Point } from './parts'

/**
 * The "Reports" tutorial: New report in four steps (report, period, filters, format), Preview, Generate, and
 * Your reports → Download. Report names and descriptions match the server's catalogue. Example data only.
 */

export const CAPTIONS = [
  'Reports: export your workforce data as CSV, Excel or PDF.',
  'Step 1 — choose a report: Attendance, Work hours, Productivity, Applications, Websites, Customer time and more.',
  'Step 2 — the period: Daily, Weekly, Monthly or a Custom range.',
  'Step 3 — filters: people, department or team. Leave them empty for everyone you are allowed to see.',
  'Step 4 — the format: CSV (plain data), Excel (filterable sheet + “About” tab) or PDF (for sharing and printing).',
  'Click Preview to check the first rows on screen before you export.',
  'Click Generate. The report is prepared in the background and appears under Your reports.',
  'When it shows “Ready for download”, click Download.',
  'Reports only include people and projects you may see. Screenshot reports list captures — images are never exported.',
  'Done. Next: roles and dashboard access.',
]

const TYPES = ['Attendance', 'Work hours', 'Activity', 'Applications', 'Websites', 'Screenshots', 'Projects', 'Tasks', 'Productivity', 'Customer time', 'Live sessions']
const DESCRIPTIONS: Record<string, string> = {
  Attendance: 'Per person and day: first start, last end and hours, from desktop-agent work sessions.',
}
const FORMATS = [
  { label: 'CSV', hint: 'Plain data for any tool', icon: FileText },
  { label: 'Excel', hint: 'Filterable sheet + an "About" tab', icon: FileSpreadsheet },
  { label: 'PDF', hint: 'For sharing and printing', icon: FileChartColumn },
]

// The New report card sits at content (20, 62) → scene (220, 106).
const card = (x: number, y: number): Point => ({ x: 220 + x, y: 106 + y })
const P: Record<string, Point> = {
  reports: navPoint('Reports'),
  attendance: card(82, 93),
  monthly: card(258, 224),
  department: card(340, 304),
  excel: card(352, 371),
  preview: card(530, 416),
  generate: card(642, 416),
  download: { x: 856, y: 330 },
  rest: { x: 640, y: 480 },
}

export function ReportsScene({ step, t }: { step: number; t: number }) {
  let cursor: Point = P.rest
  let click = false
  if (step === 1) {
    cursor = t < 2 ? P.reports : P.attendance
    click = clickAt(t, 1.2) || clickAt(t, 3.2)
  } else if (step === 2) {
    cursor = P.monthly
    click = clickAt(t, 1.4)
  } else if (step === 3) {
    cursor = P.department
    click = clickAt(t, 1.4) || clickAt(t, 3)
  } else if (step === 4) {
    cursor = P.excel
    click = clickAt(t, 2.2)
  } else if (step === 5) {
    cursor = P.preview
    click = clickAt(t, 0.9)
  } else if (step === 6) {
    cursor = P.generate
    click = clickAt(t, 0.9)
  } else if (step === 7) {
    cursor = P.download
    click = clickAt(t, 2)
  }

  const onPage = step >= 1 && !(step === 1 && t < 1.4)
  const type = step > 1 || (step === 1 && t >= 3.3) ? 'Attendance' : ''
  const period = step > 2 || (step === 2 && t >= 1.5) ? 'Monthly' : 'Daily'
  const dept = step > 3 || (step === 3 && t >= 3.1) ? 'Visa' : ''
  const format = step > 4 || (step === 4 && t >= 2.3) ? 'Excel' : 'CSV'
  const showReports = (step === 6 && t >= 1.1) || step === 7 || step === 8

  return (
    <div className="relative h-[540px] w-[960px] overflow-hidden bg-background text-foreground select-none">
      <Shell active={onPage ? 'Reports' : 'Dashboard'}>
        {onPage && (
          <>
            <p className="absolute flex items-center gap-2 text-[18px] font-semibold" style={{ left: 20, top: 8 }}>
              <FileChartColumn className="size-5 text-primary" /> Reports
            </p>
            <p className="absolute text-[11px] text-muted-foreground" style={{ left: 20, top: 36 }}>
              Export your workforce data as CSV, Excel or PDF.
            </p>
            <NewReport step={step} t={t} type={type} period={period} dept={dept} format={format} />
            {step === 5 && t >= 1.1 && <PreviewPanel t={t - 1.1} />}
            {showReports && <YourReports step={step} t={step === 6 ? t - 1.1 : 9 + t} />}
            {step === 8 && <Notes t={t} />}
          </>
        )}
      </Shell>
      {step === 6 && t >= 1.1 && <Toast title="Preparing report… it will appear under Your reports when ready." />}
      {step === 7 && t >= 2.2 && <Toast title="Downloaded" text="attendance-2026-11.xlsx" />}
      {step === 0 && <TitleCard icon={FileChartColumn} title="Reports" text="Export your workforce data as CSV, Excel or PDF." />}
      {step === 9 && <TitleCard icon={Check} title="Reports ready" text="Next: roles and dashboard access." />}
      {step !== 0 && step !== 9 && step !== 8 && <Cursor at={cursor} click={click} />}
    </div>
  )
}

function StepTitle({ n, title, y, lit }: { n: number; title: string; y: number; lit: boolean }) {
  return (
    <p className={cn('absolute flex items-center gap-2 text-[12px] font-semibold transition-colors', lit && 'text-primary')} style={{ left: 16, top: y }}>
      <span className={cn('flex size-5 items-center justify-center rounded-full text-[10.5px]', lit ? 'bg-primary text-primary-foreground' : 'bg-muted')}>{n}</span>
      {title}
    </p>
  )
}

function NewReport({ step, t, type, period, dept, format }: { step: number; t: number; type: string; period: string; dept: string; format: string }) {
  return (
    <div className="absolute rounded-xl border bg-card" style={{ left: 20, top: 62, width: 720, height: 430 }}>
      <p className="absolute text-[14px] font-semibold" style={{ left: 16, top: 12 }}>
        New report
      </p>
      <p className="absolute text-[11px] text-muted-foreground" style={{ left: 16, top: 32 }}>
        Reports only include people and projects you are allowed to see.
      </p>

      <StepTitle n={1} title="Report" y={56} lit={step === 1} />
      {TYPES.map((name, i) => (
        <span
          key={name}
          className={cn('absolute flex h-[30px] items-center rounded-lg border px-2.5 text-[11.5px] font-medium transition', name === type && 'border-primary bg-primary/10 ring-1 ring-primary')}
          style={{ left: 16 + (i % 5) * 138, top: 78 + Math.floor(i / 5) * 36, width: 132 }}
        >
          {name}
        </span>
      ))}
      {step === 1 && type && (
        <p className="absolute text-[10.5px] text-muted-foreground" style={{ left: 154, top: 158, opacity: ramp(t, 3.6) }}>
          {DESCRIPTIONS.Attendance}
        </p>
      )}

      <StepTitle n={2} title="Period" y={190} lit={step === 2} />
      <div className="absolute flex rounded-lg bg-muted p-0.5" style={{ left: 16, top: 210 }}>
        {['Daily', 'Weekly', 'Monthly', 'Custom range'].map((p) => (
          <span key={p} className={cn('flex h-7 w-24 items-center justify-center rounded-md text-[11.5px] transition-colors', p === period ? 'bg-background font-medium shadow-sm' : 'text-muted-foreground')}>
            {p}
          </span>
        ))}
      </div>
      <div className="absolute" style={{ left: 420, top: 196, width: 150 }}>
        <Field label={period === 'Monthly' ? 'Month' : 'Day'} value={period === 'Monthly' ? 'November 2026' : '06-11-2026'} />
      </div>

      <StepTitle n={3} title="Filters" y={256} lit={step === 3} />
      <div className="absolute" style={{ left: 16, top: 274, width: 210 }}>
        <Field label="People" value="" placeholder="Everyone you can see" />
      </div>
      <div className="absolute" style={{ left: 240, top: 274, width: 200 }}>
        <Field label="Department" value={dept} placeholder="All departments" select focused={step === 3 && t >= 1.2 && t < 3.4} />
      </div>
      <div className="absolute" style={{ left: 454, top: 274, width: 200 }}>
        <Field label="Team" value="" placeholder="All teams" select />
      </div>
      {step === 3 && t >= 1.5 && t < 3 && (
        <div className="absolute z-10 w-[200px] rounded-lg border bg-popover p-1 text-[12px] shadow-lg" style={{ left: 240, top: 326 }}>
          {['All departments', 'Visa', 'Ticketing', 'Accounts'].map((d) => (
            <p key={d} className={cn('rounded px-2 py-1', d === 'Visa' && 'bg-accent font-medium')}>
              {d}
            </p>
          ))}
        </div>
      )}

      <StepTitle n={4} title="Format" y={330} lit={step === 4} />
      {FORMATS.map((f, i) => (
        <span
          key={f.label}
          className={cn('absolute flex h-[46px] items-center gap-2.5 rounded-lg border px-3 transition', f.label === format && 'border-primary bg-primary/10 ring-1 ring-primary')}
          style={{ left: 16 + i * 226, top: 348, width: 220 }}
        >
          <f.icon className="size-4 text-muted-foreground" />
          <span>
            <span className="block text-[12px] font-semibold">{f.label}</span>
            <span className="block text-[10px] whitespace-nowrap text-muted-foreground">{f.hint}</span>
          </span>
        </span>
      ))}

      <div className="absolute flex gap-2" style={{ right: 16, top: 400 }}>
        <Btn focused={step === 5 && t < 1.2}>
          <Eye className="size-3.5" /> Preview
        </Btn>
        <Btn primary focused={step === 6 && t < 1.2}>
          <Download className="size-3.5" /> Generate {format}
        </Btn>
      </div>
    </div>
  )
}

function PreviewPanel({ t }: { t: number }) {
  const rows = [
    ['Abdul Basith', 'Visa', '2026-11-02', '9:28 am', '6:14 pm', '7:58'],
    ['Abdul Basith', 'Visa', '2026-11-03', '9:31 am', '6:05 pm', '7:52'],
    ['Jamsheed K P', 'Visa', '2026-11-02', '9:40 am', '5:58 pm', '7:31'],
    ['Jamsheed K P', 'Visa', '2026-11-03', '9:35 am', '6:20 pm', '7:10'],
  ]
  return (
    <div className="absolute z-10 rounded-xl border bg-card shadow-xl" style={{ left: 20, top: 250, width: 720, ...rise(t, 0) }}>
      <p className="px-4 pt-3 pb-2 text-[12px] font-semibold">Preview · first rows</p>
      <div className="grid h-7 grid-cols-[1.3fr_0.7fr_1fr_0.8fr_0.8fr_0.6fr] items-center border-y bg-subtle/60 px-4 text-[10px] font-medium tracking-wide text-muted-foreground uppercase">
        <span>Employee</span>
        <span>Department</span>
        <span>Day</span>
        <span>First start</span>
        <span>Last end</span>
        <span className="text-right">Hours</span>
      </div>
      {rows.map((r, i) => (
        <div key={i} className="grid h-8 grid-cols-[1.3fr_0.7fr_1fr_0.8fr_0.8fr_0.6fr] items-center border-b px-4 text-[11.5px] last:border-0" style={rise(t, 0.2 + i * 0.12)}>
          {r.map((c, j) => (
            <span key={j} className={cn(j === 5 && 'text-right tabular', j > 1 && j < 5 && 'text-muted-foreground')}>
              {c}
            </span>
          ))}
        </div>
      ))}
    </div>
  )
}

function YourReports({ step, t }: { step: number; t: number }) {
  const stage = t < 1.4 ? 'Preparing report…' : t < 2.8 ? 'Generating…' : 'Ready for download'
  const ready = stage === 'Ready for download'
  return (
    <div className="absolute z-10 rounded-xl border bg-card shadow-xl" style={{ left: 380, top: 230, width: 360, ...rise(t, 0) }}>
      <p className="px-4 pt-3 pb-2 text-[13px] font-semibold">Your reports</p>
      <div className="flex items-center gap-3 border-t px-4 py-3 text-[12px]">
        <FileSpreadsheet className="size-4 text-muted-foreground" />
        <span className="flex-1">
          <span className="block font-medium">Attendance · November 2026</span>
          <span className={cn('block text-[10.5px]', ready ? 'text-cat-productive' : 'text-muted-foreground')}>{stage}</span>
        </span>
        {ready && (
          <span className={cn('flex h-7 items-center gap-1 rounded-md border px-2.5 text-[11px] font-medium duration-300 animate-in fade-in-0', step === 7 && t >= 9 && 'border-primary ring-[3px] ring-primary/25')}>
            <Download className="size-3.5" /> Download
          </span>
        )}
        <Trash2 className="size-3.5 text-muted-foreground" />
      </div>
    </div>
  )
}

function Notes({ t }: { t: number }) {
  return (
    <div className="absolute z-20 space-y-2 rounded-xl border bg-card p-4 shadow-xl" style={{ left: 120, top: 150, width: 520 }}>
      <p className="flex gap-2 text-[12.5px]" style={rise(t, 0.3)}>
        <Check className="mt-0.5 size-4 shrink-0 text-cat-productive" /> Only people and projects you are allowed to see.
      </p>
      <p className="flex gap-2 text-[12.5px]" style={rise(t, 4)}>
        <Check className="mt-0.5 size-4 shrink-0 text-cat-productive" /> Screenshots report: when screenshots were captured, for whom and on which device. Images are never exported.
      </p>
    </div>
  )
}
