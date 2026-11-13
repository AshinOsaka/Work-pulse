import { AppWindow, Check, ChevronDown, Globe, Layers, ListFilter, Plus, Sparkles } from 'lucide-react'

import { cn } from '@/lib/utils'
import { Btn, Cursor, Field, Shell, Tabs, TitleCard, Toast, clickAt, navPoint, ramp, rise, typed, type Point } from './parts'

/**
 * The "Productivity rules" tutorial: Productivity → Rules & work profiles — starter rules, classifying what was
 * used, adding a rule with a scope, which rule wins, bulk add, and the productive-share formula (as the engine
 * computes it: productive ÷ classified, unclassified excluded). Example data only.
 */

export const CAPTIONS = [
  'Productivity rules decide which apps and websites are productive, neutral or unproductive. Without rules, time stays unclassified.',
  'Open Productivity → Rules & work profiles.',
  'Quick start: click Starter rules to add common rules in one go.',
  'Open “Not classified yet” — what people used in the last 30 days — then Classify → Productive, Neutral or Unproductive.',
  'Or click Add rule: choose Application or Website and enter the program or domain (a domain includes its subdomains).',
  'Pick the category and the scope — whole company, department, team, role or work profile — then Add rule.',
  'The most specific rule wins: work profile → team → department → role → whole company.',
  'Bulk add: paste many apps or websites at once, e.g. social media sites as Unproductive.',
  'Productive share = Productive ÷ (Productive + Neutral + Unproductive) × 100. Unclassified time is left out.',
  "Done. Next: each person's productivity and activity details.",
]

const TABS = ['People', 'Breakdown', 'Departments & teams', 'Trends', 'Rules & work profiles']
const O = { x: 200, y: 44 }
const at = (x: number, y: number): Point => ({ x: O.x + x, y: O.y + y })
// The Rules card sits at (20, 96) in the content box.
const card = (x: number, y: number) => at(20 + x, 96 + y)
// Dialogs sit at scene (300, 110).
const dlg = (x: number, y: number): Point => ({ x: 300 + x, y: 110 + y })

const P: Record<string, Point> = {
  productivity: navPoint('Productivity'),
  rulesTab: at(418, 70),
  starter: card(438, 30),
  bulk: card(552, 30),
  add: card(655, 30),
  notClassified: card(464, 75),
  classify: card(643, 120),
  classifyProductive: { x: 800, y: 330 },
  website: dlg(260, 110),
  domain: dlg(180, 174),
  productive: dlg(73, 236),
  scope: dlg(95, 296),
  target: dlg(265, 296),
  addRule: dlg(310, 346),
  bulkText: dlg(180, 210),
  bulkAdd: dlg(300, 346),
  rest: { x: 640, y: 480 },
}

const RULES = [
  { name: 'code.exe', kind: 'app', scope: 'Whole company', cat: 'productive' },
  { name: 'Microsoft Excel', kind: 'app', scope: 'Whole company', cat: 'productive' },
  { name: 'mail.google.com', kind: 'website', scope: 'Whole company', cat: 'neutral' },
  { name: 'youtube.com', kind: 'website', scope: 'Whole company', cat: 'unproductive' },
  { name: 'Microsoft Teams', kind: 'app', scope: 'Whole company', cat: 'neutral' },
]
const UNCLASSIFIED = [
  { name: 'osakaconnect.com', info: '12h 40m · 6 people' },
  { name: 'web.whatsapp.com', info: '3h 05m · 5 people' },
  { name: 'emergent.sh', info: '1h 50m · 2 people' },
]
const CAT_STYLE: Record<string, string> = {
  productive: 'bg-cat-productive/15 text-cat-productive',
  neutral: 'bg-cat-neutral/15 text-cat-neutral',
  unproductive: 'bg-cat-unproductive/15 text-cat-unproductive',
}

export function ProductivityRulesScene({ step, t }: { step: number; t: number }) {
  let cursor: Point = P.rest
  let click = false
  if (step === 1) {
    cursor = t < 1.4 ? P.productivity : P.rulesTab
    click = clickAt(t, 0.8) || clickAt(t, 2.2)
  } else if (step === 2) {
    cursor = P.starter
    click = clickAt(t, 1.2)
  } else if (step === 3) {
    cursor = t < 2.4 ? P.notClassified : t < 5.6 ? P.classify : P.classifyProductive
    click = clickAt(t, 1.4) || clickAt(t, 4.8) || clickAt(t, 6.6)
  } else if (step === 4) {
    cursor = t < 1.6 ? P.add : t < 3.6 ? P.website : P.domain
    click = clickAt(t, 0.8) || clickAt(t, 2.6) || clickAt(t, 4.2)
  } else if (step === 5) {
    cursor = t < 1.8 ? P.productive : t < 4.2 ? P.scope : t < 6.2 ? P.target : P.addRule
    click = clickAt(t, 1) || clickAt(t, 2.6) || clickAt(t, 3.6) || clickAt(t, 5) || clickAt(t, 7.2)
  } else if (step === 7) {
    cursor = t < 1.4 ? P.bulk : t < 5.4 ? P.bulkText : P.bulkAdd
    click = clickAt(t, 0.8) || clickAt(t, 6.4)
  }

  const onProductivity = !(step === 1 && t < 1.0)
  const onRules = step >= 2 || (step === 1 && t >= 2.3)
  const starterAdded = step > 2 || (step === 2 && t >= 1.4)
  const showUnclassified = step === 3 && t >= 1.5
  const classified = step === 3 && t >= 6.8
  const addOpen = (step === 4 && t >= 1.0) || (step === 5 && t < 7.4)
  const bulkOpen = step === 7 && t >= 1.0 && t < 6.6
  return (
    <div className="relative h-[540px] w-[960px] overflow-hidden bg-background text-foreground select-none">
      <Shell active={onProductivity && step >= 1 ? 'Productivity' : 'Dashboard'}>
        {onProductivity && step >= 1 && (
          <>
            <p className="absolute text-[18px] font-semibold" style={{ left: 20, top: 12 }}>
              Productivity
            </p>
            <p className="absolute text-[11px] text-muted-foreground" style={{ left: 20, top: 38 }}>
              Time by category under your rules.
            </p>
            <div className="absolute" style={{ left: 20, top: 62, width: 720 }}>
              <Tabs tabs={TABS} active={onRules ? 'Rules & work profiles' : 'People'} />
            </div>
            {onRules && step <= 5 && <RulesCard step={step} t={t} starterAdded={starterAdded} showUnclassified={showUnclassified} classified={classified} />}
            {onRules && step === 7 && <RulesCard step={step} t={t} starterAdded showUnclassified={false} classified />}
            {step === 6 && <Precedence t={t} />}
            {step === 8 && <Formula t={t} />}
          </>
        )}
      </Shell>
      {step === 3 && t >= 4.9 && t < 6.7 && (
        <div className="absolute z-20 w-52 rounded-lg border bg-popover p-1 text-[12px] shadow-lg duration-200 animate-in fade-in-0" style={{ left: 740, top: 276 }}>
          <p className="px-2 py-1 text-[10.5px] text-muted-foreground">Company-wide rule for osakaconnect.com</p>
          {['productive', 'neutral', 'unproductive'].map((c) => (
            <p key={c} className={cn('flex items-center gap-2 rounded px-2 py-1.5 capitalize', c === 'productive' && t > 5.8 && 'bg-accent')}>
              <span className={cn('size-2.5 rounded-sm', c === 'productive' ? 'bg-cat-productive' : c === 'neutral' ? 'bg-cat-neutral' : 'bg-cat-unproductive')} />
              {c}
            </p>
          ))}
        </div>
      )}
      {addOpen && <AddRuleDialog step={step} t={t} />}
      {bulkOpen && <BulkDialog t={t} />}
      {step === 2 && t >= 1.5 && <Toast title="Added 24 starter rules" />}
      {step === 3 && t >= 6.9 && <Toast title="osakaconnect.com is now productive for the whole company" />}
      {step === 5 && t >= 7.5 && <Toast title="Rule added" text="booking.com · Productive · Department · Visa" />}
      {step === 7 && t >= 6.6 && <Toast title="Added 3 rules" />}
      {step === 0 && <TitleCard icon={ListFilter} title="Productivity rules" text="Decide what counts as productive, neutral or unproductive." />}
      {step === 9 && <TitleCard icon={Check} title="Rules in place" text="Next: each person's productivity and activity details." />}
      {step !== 0 && step !== 9 && step !== 6 && step !== 8 && <Cursor at={cursor} click={click} />}
    </div>
  )
}

function RulesCard({ step, t, starterAdded, showUnclassified, classified }: { step: number; t: number; starterAdded: boolean; showUnclassified: boolean; classified: boolean }) {
  const rules = starterAdded ? RULES : []
  const unclassified = classified ? UNCLASSIFIED.slice(1) : UNCLASSIFIED
  const chips = [
    { label: 'All', count: rules.length, w: 60 },
    { label: 'Productive', count: rules.filter((r) => r.cat === 'productive').length, w: 100 },
    { label: 'Neutral', count: rules.filter((r) => r.cat === 'neutral').length, w: 84 },
    { label: 'Unproductive', count: rules.filter((r) => r.cat === 'unproductive').length, w: 110 },
    { label: 'Not classified yet', count: unclassified.length, w: 140 },
  ]
  let left = 16
  return (
    <div className="absolute rounded-xl border bg-card" style={{ left: 20, top: 96, width: 720, height: 396 }}>
      <p className="absolute text-[14px] font-semibold" style={{ left: 16, top: 12 }}>
        Rules
      </p>
      <p className="absolute text-[11px] leading-snug text-muted-foreground" style={{ left: 16, top: 32, right: 370 }}>
        Classify apps and websites for the company, a department, team, role or work profile.
      </p>
      <div className="absolute flex gap-2" style={{ right: 16, top: 14 }}>
        <Btn focused={step === 2 && t < 1.6}>
          <Sparkles className="size-3.5" /> Starter rules
        </Btn>
        <Btn focused={step === 7 && t < 1.2}>
          <Layers className="size-3.5" /> Bulk add
        </Btn>
        <Btn primary focused={step === 4 && t < 1.2}>
          <Plus className="size-3.5" /> Add rule
        </Btn>
      </div>
      {chips.map((c) => {
        const x = left
        left += c.w + 6
        const active = showUnclassified ? c.label === 'Not classified yet' : c.label === 'All'
        return (
          <span
            key={c.label}
            className={cn('absolute flex h-[26px] items-center justify-center gap-1.5 rounded-full border text-[11px] transition-colors', active ? 'border-primary bg-primary/10 font-medium text-primary' : 'text-muted-foreground')}
            style={{ left: x, top: 62, width: c.w }}
          >
            {c.label} <span className="tabular opacity-70">{c.count}</span>
          </span>
        )
      })}
      <div className="absolute overflow-hidden rounded-lg border" style={{ left: 16, right: 16, top: 100 }}>
        {showUnclassified ? (
          unclassified.map((u) => (
            <div key={u.name} className="flex h-9 items-center gap-3 border-b px-3 text-[12px] last:border-0">
              <Globe className="size-3.5 text-muted-foreground" />
              <span className="flex-1">
                <span className="font-medium">{u.name}</span> <span className="text-muted-foreground">· {u.info}</span>
              </span>
              <span className="flex h-7 items-center gap-1 rounded-md border px-2.5 text-[11px] font-medium">
                Classify <ChevronDown className="size-3" />
              </span>
            </div>
          ))
        ) : (
          <>
            <div className="grid h-7 grid-cols-[1.6fr_1fr_0.8fr] items-center border-b bg-subtle/60 px-3 text-[10px] font-medium tracking-wide text-muted-foreground uppercase">
              <span>Application or website</span>
              <span>Applies to</span>
              <span>Category</span>
            </div>
            {rules.length === 0 ? (
              <p className="px-3 py-4 text-[12px] text-muted-foreground">No rules yet — without rules everything is unclassified.</p>
            ) : (
              rules.map((r, i) => (
                <div key={r.name} className="grid h-9 grid-cols-[1.6fr_1fr_0.8fr] items-center border-b px-3 text-[12px] last:border-0" style={rise(step === 2 ? t : 9, 1.5 + i * 0.12)}>
                  <span className="flex items-center gap-2 font-medium">
                    {r.kind === 'app' ? <AppWindow className="size-3.5 text-muted-foreground" /> : <Globe className="size-3.5 text-muted-foreground" />}
                    {r.name}
                  </span>
                  <span className="text-muted-foreground">{r.scope}</span>
                  <span>
                    <span className={cn('rounded-full px-2 py-0.5 text-[10.5px] font-medium capitalize', CAT_STYLE[r.cat])}>{r.cat}</span>
                  </span>
                </div>
              ))
            )}
          </>
        )}
      </div>
    </div>
  )
}

function Seg({ items, active, focused }: { items: string[]; active: string; focused?: boolean }) {
  return (
    <div className={cn('flex rounded-lg bg-muted p-0.5', focused && 'ring-[3px] ring-primary/25')}>
      {items.map((i) => (
        <span key={i} className={cn('flex h-7 flex-1 items-center justify-center rounded-md text-[11.5px] transition-colors duration-300', i === active ? 'bg-background font-medium shadow-sm' : 'text-muted-foreground')}>
          {i}
        </span>
      ))}
    </div>
  )
}

function Dialog({ title, text, height, children }: { title: string; text: string; height: number; children: React.ReactNode }) {
  return (
    <div className="absolute inset-0 z-20 bg-black/30 duration-300 animate-in fade-in-0">
      <div className="absolute rounded-xl border bg-card shadow-xl duration-300 animate-in zoom-in-95" style={{ left: 300, top: 110, width: 360, height }}>
        <p className="absolute text-[14px] font-semibold" style={{ left: 20, top: 16 }}>
          {title}
        </p>
        <p className="absolute text-[10.5px] leading-snug text-muted-foreground" style={{ left: 20, right: 20, top: 40 }}>
          {text}
        </p>
        {children}
      </div>
    </div>
  )
}

function AddRuleDialog({ step, t }: { step: number; t: number }) {
  const s4 = step === 4
  const website = !s4 || t >= 2.7
  const domain = s4 ? typed('booking.com', t, 4.6, 5.8) : 'booking.com'
  const productive = step === 5 && t >= 1.1
  const scope = step === 5 && t >= 3.7 ? 'Department' : 'Whole company'
  const target = step === 5 && t >= 5.1 ? 'Visa' : ''
  return (
    <Dialog title="Add a productivity rule" text="The most specific rule wins for each person: work profile, then team, department, role, and finally company-wide." height={382}>
      <p className="absolute text-[11px] font-medium" style={{ left: 20, top: 80 }}>
        Applies to
      </p>
      <div className="absolute" style={{ left: 20, top: 96, width: 320 }}>
        <Seg items={['Application', 'Website']} active={website ? 'Website' : 'Application'} />
      </div>
      <div className="absolute" style={{ left: 20, top: 140, width: 320 }}>
        <Field label={website ? 'Domain' : 'Executable or application name'} value={domain} placeholder="e.g. github.com (includes subdomains)" focused={s4 && t >= 4.2} />
      </div>
      <p className="absolute text-[11px] font-medium" style={{ left: 20, top: 206 }}>
        Category
      </p>
      <div className="absolute" style={{ left: 20, top: 222, width: 320 }}>
        <Seg items={['Productive', 'Neutral', 'Unproductive']} active={productive ? 'Productive' : 'Neutral'} />
      </div>
      <div className="absolute" style={{ left: 20, top: 262, width: 150 }}>
        <Field label="Scope" value={scope} select focused={step === 5 && t >= 2.4 && t < 4.2} />
      </div>
      <div className="absolute" style={{ left: 190, top: 262, width: 150 }}>
        <Field label="Department" value={target} placeholder="Choose a department" select focused={step === 5 && t >= 4.2 && t < 6.2} />
      </div>
      {step === 5 && t >= 2.7 && t < 3.7 && (
        <div className="absolute z-10 w-40 rounded-lg border bg-popover p-1 text-[12px] shadow-lg" style={{ left: 20, top: 314 }}>
          {['Whole company', 'Department', 'Team', 'Role', 'Work profile'].map((s) => (
            <p key={s} className={cn('rounded px-2 py-1', s === 'Department' && 'bg-accent font-medium')}>
              {s}
            </p>
          ))}
        </div>
      )}
      <div className="absolute flex gap-2" style={{ right: 20, top: 330 }}>
        <Btn>Cancel</Btn>
        <Btn primary focused={step === 5 && t >= 6.4}>
          Add rule
        </Btn>
      </div>
    </Dialog>
  )
}

function BulkDialog({ t }: { t: number }) {
  const lines = typed('youtube.com\nfacebook.com\ninstagram.com', t, 1.8, 5)
  const count = lines.split('\n').filter((l) => l.includes('.com')).length
  return (
    <Dialog title="Add rules in bulk" text="Add many applications or websites at once, for the whole company. One per line." height={382}>
      <div className="absolute" style={{ left: 20, top: 84, width: 320 }}>
        <Seg items={['Applications', 'Websites']} active="Websites" />
      </div>
      <div className="absolute" style={{ left: 20, top: 122, width: 320 }}>
        <Field label="Category" value="Unproductive" select />
      </div>
      <div className="absolute rounded-md border bg-card px-2.5 py-2 font-mono text-[12px] leading-5 whitespace-pre" style={{ left: 20, top: 178, width: 320, height: 120 }}>
        {lines}
        <span className="inline-block h-3.5 w-px translate-y-0.5 animate-pulse bg-foreground" />
      </div>
      <div className="absolute flex gap-2" style={{ right: 20, top: 330 }}>
        <Btn>Cancel</Btn>
        <Btn primary focused={t >= 5.6}>
          Add {count || ''} rule{count !== 1 ? 's' : ''}
        </Btn>
      </div>
    </Dialog>
  )
}

/** Which rule wins: the ladder from most to least specific, with an example. */
function Precedence({ t }: { t: number }) {
  const levels = ['Work profile', 'Team', 'Department', 'Role', 'Whole company']
  return (
    <div className="absolute flex gap-8" style={{ left: 20, top: 100, width: 720 }}>
      <div className="w-64 space-y-2">
        <p className="text-[13px] font-semibold">The most specific rule wins</p>
        {levels.map((l, i) => (
          <div key={l} className="flex items-center gap-2" style={rise(t, 0.4 + i * 0.6)}>
            <span className="flex size-6 items-center justify-center rounded-full bg-primary text-[11px] font-semibold text-primary-foreground" style={{ opacity: 1 - i * 0.15 }}>
              {i + 1}
            </span>
            <span className="flex-1 rounded-md border bg-card px-3 py-1.5 text-[12px] font-medium">{l}</span>
          </div>
        ))}
      </div>
      <div className="flex-1 rounded-xl border bg-card p-4" style={{ opacity: ramp(t, 4.5) }}>
        <p className="mb-3 text-[13px] font-semibold">Example: booking.com</p>
        <div className="space-y-2 text-[12px]">
          <p className="flex justify-between rounded-md border px-3 py-2">
            <span>Department · Visa</span>
            <span className="rounded-full bg-cat-productive/15 px-2 font-medium text-cat-productive">Productive</span>
          </p>
          <p className="flex justify-between rounded-md border px-3 py-2">
            <span>Whole company</span>
            <span className="rounded-full bg-cat-neutral/15 px-2 font-medium text-cat-neutral">Neutral</span>
          </p>
        </div>
        <div className="mt-4 grid grid-cols-2 gap-2 text-[12px]" style={{ opacity: ramp(t, 7.5) }}>
          <p className="rounded-md bg-cat-productive/10 px-3 py-2">
            Visa staff → <strong className="text-cat-productive">Productive</strong>
          </p>
          <p className="rounded-md bg-cat-neutral/10 px-3 py-2">
            Everyone else → <strong className="text-cat-neutral">Neutral</strong>
          </p>
        </div>
      </div>
    </div>
  )
}

/** The productive-share formula with a worked example (5h 40m ÷ 7h 40m ≈ 74%). */
function Formula({ t }: { t: number }) {
  const parts = [
    { label: 'Productive', value: '5h 40m', cls: 'bg-cat-productive', w: 340 },
    { label: 'Neutral', value: '1h 20m', cls: 'bg-cat-neutral', w: 80 },
    { label: 'Unproductive', value: '0h 40m', cls: 'bg-cat-unproductive', w: 40 },
  ]
  const total = 460
  return (
    <div className="absolute rounded-xl border bg-card p-5" style={{ left: 20, top: 100, width: 720 }}>
      <p className="text-[11px] font-medium tracking-wide text-muted-foreground uppercase">How it is calculated</p>
      <p className="mt-1 font-mono text-[14px]">Productive time ÷ (Productive + Neutral + Unproductive time) × 100</p>
      <div className="mt-5 flex h-7 overflow-hidden rounded-md">
        {parts.map((p, i) => (
          <div key={p.label} className={cn('h-full origin-left', p.cls)} style={{ width: `${(100 * p.w) / total}%`, transform: `scaleX(${ramp(t, 1 + i * 0.5, 0.8)})` }} />
        ))}
      </div>
      <div className="mt-3 grid grid-cols-4 gap-3 text-[12px]">
        {parts.map((p) => (
          <p key={p.label}>
            <span className="block text-muted-foreground">{p.label}</span>
            <span className="font-semibold tabular">{p.value}</span>
          </p>
        ))}
        <p style={{ opacity: ramp(t, 5) }}>
          <span className="block text-muted-foreground">Unclassified (excluded)</span>
          <span className="font-semibold text-muted-foreground tabular line-through">0h 30m</span>
        </p>
      </div>
      <div className="mt-5 flex items-baseline gap-3 border-t pt-4" style={{ opacity: ramp(t, 3) }}>
        <span className="text-[13px] text-muted-foreground">5h 40m ÷ 7h 40m × 100 =</span>
        <span className="text-[30px] font-semibold text-cat-productive tabular">74%</span>
        <span className="text-[13px] text-muted-foreground">productive share</span>
      </div>
    </div>
  )
}
