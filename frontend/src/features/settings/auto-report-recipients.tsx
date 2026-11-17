import { useState } from 'react'
import { AlertTriangle, ChevronDown, Mail, Network, Plus, Trash2 } from 'lucide-react'
import { toast } from 'sonner'

import { ConfirmDialog } from '@/components/common/confirm-dialog'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/misc'
import { SegmentedControl } from '@/components/ui/segmented-control'
import { useDepartments, useTeams } from '@/features/people/api'
import { useAutoReportOverview } from '@/features/settings/api'
import { formatDate, formatDateTime } from '@/lib/format'
import { cn } from '@/lib/utils'
import type { AutoReportRun, ExtraRecipient } from '@/types/api'

const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/

/** Pick any number of items; none picked means "all". */
function MultiPick({
  allLabel,
  noun,
  items,
  value,
  onChange,
  disabled,
  empty,
}: {
  allLabel: string
  noun: string
  items: { id: string; name: string; hint?: string }[]
  value: string[]
  onChange: (ids: string[]) => void
  disabled: boolean
  empty: string
}) {
  const names = value.map((id) => items.find((i) => i.id === id)?.name ?? 'Removed')
  const label = value.length === 0 ? allLabel : value.length === 1 ? names[0] : `${value.length} ${noun}`
  const toggle = (id: string, on: boolean) => onChange(on ? [...value, id] : value.filter((v) => v !== id))
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild disabled={disabled}>
        <Button
          type="button"
          variant="outline"
          className={cn('h-8 w-44 justify-between gap-2 px-2.5 text-[12px] font-normal', value.length === 0 && 'text-muted-foreground')}
          title={value.length === 0 ? allLabel : names.join(', ')}
          aria-label={noun}
        >
          <span className="truncate">{label}</span>
          <ChevronDown className="size-3.5 shrink-0 opacity-60" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="max-h-72 w-72 overflow-y-auto">
        <DropdownMenuCheckboxItem checked={value.length === 0} onCheckedChange={() => onChange([])} onSelect={(e) => e.preventDefault()}>
          {allLabel}
        </DropdownMenuCheckboxItem>
        <DropdownMenuSeparator />
        {items.length === 0 ? (
          <p className="px-2 py-1.5 text-[12px] text-muted-foreground">{empty}</p>
        ) : (
          items.map((i) => (
            <DropdownMenuCheckboxItem
              key={i.id}
              checked={value.includes(i.id)}
              onCheckedChange={(on) => toggle(i.id, on === true)}
              onSelect={(e) => e.preventDefault()}
            >
              <span className="truncate">{i.name}</span>
              {i.hint && <span className="ml-auto pl-2 text-[11px] text-muted-foreground">{i.hint}</span>}
            </DropdownMenuCheckboxItem>
          ))
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

type Sends = 'both' | 'midday' | 'evening'
const sendsOf = (r: ExtraRecipient): Sends => (r.midday && r.evening ? 'both' : r.midday ? 'midday' : 'evening')

/** Extra recipients (HR, a director): each with the departments/teams they cover and which reports they get. */
export function ExtraRecipientsEditor({
  value,
  onChange,
  disabled,
}: {
  value: ExtraRecipient[]
  onChange: (next: ExtraRecipient[]) => void
  disabled: boolean
}) {
  const departments = useDepartments()
  const teams = useTeams()
  const [email, setEmail] = useState('')
  const [removing, setRemoving] = useState<string | null>(null)
  const add = () => {
    const address = email.trim().toLowerCase()
    if (!EMAIL.test(address)) {
      toast.error('Enter a valid e-mail address.')
      return
    }
    if (value.some((r) => r.email === address)) {
      toast.error('That address is already in the list.')
      return
    }
    onChange([...value, { email: address, department_ids: [], team_ids: [], midday: true, evening: true }])
    setEmail('')
  }
  const update = (i: number, patch: Partial<ExtraRecipient>) => onChange(value.map((r, j) => (j === i ? { ...r, ...patch } : r)))
  const deptItems = (departments.data ?? []).map((d) => ({ id: d.id, name: d.name, hint: `${d.employee_count}` }))
  const teamsFor = (r: ExtraRecipient) =>
    (teams.data ?? [])
      .filter((t) => r.department_ids.length === 0 || (t.department && r.department_ids.includes(t.department.id)))
      .map((t) => ({ id: t.id, name: t.name, hint: t.department?.name }))

  return (
    <div className="space-y-2">
      {!disabled && (
        <div className="flex max-w-md gap-2">
          <Input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                e.preventDefault()
                add()
              }
            }}
            placeholder="name@company.com"
            aria-label="Add recipient e-mail"
            className="h-8 text-[13px]"
          />
          <Button type="button" size="sm" variant="outline" onClick={add} disabled={!email.trim()}>
            <Plus /> Add
          </Button>
        </div>
      )}
      {value.length === 0 ? (
        <p className="text-[13px] text-muted-foreground">No extra recipients.</p>
      ) : (
        <ul className="divide-y rounded-md border">
          {value.map((r, i) => (
            <li key={r.email} className="space-y-2 px-3 py-2.5">
              <div className="flex items-center justify-between gap-2">
                <span className="flex min-w-0 items-center gap-2 text-[13px] font-medium">
                  <Mail className="size-3.5 shrink-0 text-muted-foreground" aria-hidden />
                  <span className="truncate">{r.email}</span>
                </span>
                {!disabled && (
                  <Button
                    type="button"
                    size="icon-sm"
                    variant="ghost"
                    onClick={() => setRemoving(r.email)}
                    aria-label={`Remove ${r.email}`}
                    className="text-muted-foreground hover:text-destructive"
                  >
                    <Trash2 />
                  </Button>
                )}
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <MultiPick
                  allLabel="All departments"
                  noun="departments"
                  items={deptItems}
                  value={r.department_ids}
                  onChange={(department_ids) =>
                    update(i, {
                      department_ids,
                      // Keep only teams that belong to the chosen departments.
                      team_ids: r.team_ids.filter((id) => {
                        const team = teams.data?.find((t) => t.id === id)
                        return department_ids.length === 0 || (team?.department && department_ids.includes(team.department.id))
                      }),
                    })
                  }
                  disabled={disabled}
                  empty="No departments yet — add them under People."
                />
                <MultiPick
                  allLabel="All teams"
                  noun="teams"
                  items={teamsFor(r)}
                  value={r.team_ids}
                  onChange={(team_ids) => update(i, { team_ids })}
                  disabled={disabled}
                  empty="No teams in these departments."
                />
                <div className={cn(disabled && 'pointer-events-none opacity-60')}>
                  <SegmentedControl<Sends>
                    size="sm"
                    label={`Reports for ${r.email}`}
                    value={sendsOf(r)}
                    onChange={(v) => update(i, { midday: v !== 'evening', evening: v !== 'midday' })}
                    options={[
                      { value: 'both', label: 'Both' },
                      { value: 'midday', label: 'Mid-day' },
                      { value: 'evening', label: 'Evening' },
                    ]}
                  />
                </div>
              </div>
            </li>
          ))}
        </ul>
      )}
      <ConfirmDialog
        open={removing !== null}
        onOpenChange={(open) => !open && setRemoving(null)}
        title="Remove recipient?"
        description={
          <>
            <strong>{removing}</strong> will stop getting report e-mails after you save.
          </>
        }
        confirmLabel="Remove"
        destructive
        onConfirm={() => {
          onChange(value.filter((r) => r.email !== removing))
          setRemoving(null)
        }}
      />
    </div>
  )
}

/** Settings → Automatic reports: who gets which report, the structure behind it, and the e-mails sent. */
export function AutoReportOverviewCard({ runs }: { runs: AutoReportRun[] }) {
  const overview = useAutoReportOverview()
  const [view, setView] = useState<'structure' | 'people' | 'emails'>('people')
  const data = overview.data
  const pct = data && data.email_daily_cap > 0 ? Math.round((100 * data.emails_today) / data.email_daily_cap) : 0
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2.5">
          <span className="flex size-8 items-center justify-center rounded-lg bg-muted text-muted-foreground">
            <Network className="size-4" />
          </span>
          Overview
        </CardTitle>
        <CardDescription>Coverage and delivery, last 7 days.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {!data ? (
          <Skeleton className="h-40" />
        ) : (
          <>
            <div className="grid gap-3 sm:grid-cols-3">
              <div className="rounded-md border px-3 py-2">
                <p className="text-[12px] text-muted-foreground">E-mails today</p>
                <p className={cn('text-lg font-semibold tabular', pct >= 80 && 'text-warning', pct >= 100 && 'text-destructive')}>
                  {data.emails_today} <span className="text-[13px] font-normal text-muted-foreground">of {data.email_daily_cap}</span>
                </p>
                <div className="mt-1 h-1.5 rounded-full bg-muted" aria-hidden>
                  <div
                    className={cn('h-1.5 rounded-full bg-primary', pct >= 80 && 'bg-warning', pct >= 100 && 'bg-destructive')}
                    style={{ width: `${Math.min(100, pct)}%` }}
                  />
                </div>
              </div>
              <div className="rounded-md border px-3 py-2">
                <p className="text-[12px] text-muted-foreground">Departments · Teams</p>
                <p className="text-lg font-semibold tabular">
                  {data.departments.filter((d) => d.id).length} · {data.departments.reduce((n, d) => n + d.teams.length, 0)}
                </p>
              </div>
              <div className="rounded-md border px-3 py-2">
                <p className="text-[12px] text-muted-foreground">Employees</p>
                <p className="text-lg font-semibold tabular">{data.employees.length}</p>
              </div>
            </div>
            {data.not_covered.length > 0 && (
              <p className="flex items-start gap-2 rounded-md border border-warning/40 bg-warning-soft px-3 py-2 text-[13px] text-warning">
                <AlertTriangle className="mt-0.5 size-4 shrink-0" />
                <span>
                  No recipient: {data.not_covered.join(', ')}. Set a manager or add an extra recipient.
                </span>
              </p>
            )}
            <SegmentedControl<'structure' | 'people' | 'emails'>
              size="sm"
              label="Overview view"
              value={view}
              onChange={setView}
              options={[
                { value: 'people', label: 'People' },
                { value: 'structure', label: 'Structure' },
                { value: 'emails', label: 'Delivery' },
              ]}
            />
            {view === 'structure' && (
              <div className="space-y-3">
                {data.departments.length === 0 ? (
                  <p className="text-[13px] text-muted-foreground">No departments yet — add them under People.</p>
                ) : (
                  data.departments.map((d) => (
                    <div key={d.id ?? 'none'} className="rounded-md border">
                      <div className="flex flex-wrap items-center justify-between gap-2 border-b bg-subtle px-3 py-2">
                        <span className="text-[13px] font-semibold">{d.name}</span>
                        <span className="text-[12px] text-muted-foreground">
                          {d.head ? `Head: ${d.head.name}` : d.id ? 'No head set' : ''} · {d.employees} employee{d.employees === 1 ? '' : 's'}
                        </span>
                      </div>
                      {d.teams.length === 0 ? (
                        <p className="px-3 py-2 text-[12px] text-muted-foreground">No teams.</p>
                      ) : (
                        <ul className="divide-y text-[13px]">
                          {d.teams.map((t) => (
                            <li key={t.id} className="flex flex-wrap items-center justify-between gap-2 px-3 py-1.5">
                              <span>{t.name}</span>
                              <span className="text-[12px] text-muted-foreground">
                                {t.lead ? `Lead: ${t.lead.name}` : 'No lead'} · {t.employees}
                              </span>
                            </li>
                          ))}
                        </ul>
                      )}
                    </div>
                  ))
                )}
              </div>
            )}
            {view === 'people' && (
              <div className="overflow-x-auto rounded-md border">
                <table className="w-full text-[13px]">
                  <thead className="bg-subtle text-left text-[11.5px] text-muted-foreground uppercase">
                    <tr>
                      <th className="px-3 py-2 font-medium">Employee</th>
                      <th className="px-3 py-2 font-medium">Department · team</th>
                      <th className="px-3 py-2 font-medium">Reports to</th>
                      <th className="px-3 py-2 text-right font-medium">Reports</th>
                      <th className="px-3 py-2 text-right font-medium">Alerts</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y">
                    {data.employees.map((e) => (
                      <tr key={e.id}>
                        <td className="px-3 py-2 font-medium">{e.name}</td>
                        <td className="px-3 py-2 text-muted-foreground">{[e.department || 'No department', e.team].filter(Boolean).join(' · ')}</td>
                        <td className="px-3 py-2">
                          {e.report_to ? (
                            <>
                              {e.report_to.name}
                              {e.extra_recipients.length > 0 && (
                                <span className="text-muted-foreground"> + {e.extra_recipients.length} extra</span>
                              )}
                            </>
                          ) : e.extra_recipients.length > 0 ? (
                            <span className="text-muted-foreground">Extra only ({e.extra_recipients.length})</span>
                          ) : null}
                          {!e.report_to && e.extra_recipients.length === 0 && (
                            <Badge variant="warning" className="ml-2">
                              Nobody
                            </Badge>
                          )}
                        </td>
                        <td className="px-3 py-2 text-right tabular">{e.reports_7d}</td>
                        <td className="px-3 py-2 text-right tabular">{e.alerts_7d}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            {view === 'emails' && runs.length > 0 && (
              <ul className="divide-y rounded-md border text-[13px]">
                {runs.map((r) => (
                  <li key={`${r.day}-${r.slot}`} className="flex flex-wrap items-center gap-x-4 gap-y-1 px-3 py-2">
                    <span className="w-28 tabular">{formatDate(r.day)}</span>
                    <span className="w-16 text-muted-foreground">{r.slot === 'midday' ? 'Mid-day' : 'Evening'}</span>
                    {r.status === 'done' ? (
                      <span className="text-muted-foreground">
                        {r.sent ?? 0} sent · {r.people ?? 0} people
                        {r.failed ? <span className="text-destructive"> · {r.failed} failed</span> : null}
                        {r.ai ? ' · AI' : ''}
                      </span>
                    ) : (
                      <Badge variant={r.status === 'failed' ? 'destructive' : 'outline'}>{r.status}</Badge>
                    )}
                  </li>
                ))}
              </ul>
            )}
            {view === 'emails' &&
              (data.recipients.length === 0 ? (
                <p className="text-[13px] text-muted-foreground">No e-mails yet.</p>
              ) : (
                <div className="overflow-x-auto rounded-md border">
                  <table className="w-full text-[13px]">
                    <thead className="bg-subtle text-left text-[11.5px] text-muted-foreground uppercase">
                      <tr>
                        <th className="px-3 py-2 font-medium">Recipient</th>
                        <th className="px-3 py-2 text-right font-medium">Reports</th>
                        <th className="px-3 py-2 text-right font-medium">Alerts</th>
                        <th className="px-3 py-2 text-right font-medium">Failed</th>
                        <th className="px-3 py-2 font-medium">Last sent</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y">
                      {data.recipients.map((r) => (
                        <tr key={r.email}>
                          <td className="px-3 py-2">
                            <p className="font-medium">{r.name || r.email}</p>
                            {r.name && <p className="text-[11.5px] text-muted-foreground">{r.email}</p>}
                          </td>
                          <td className="px-3 py-2 text-right tabular">{r.reports}</td>
                          <td className="px-3 py-2 text-right tabular">{r.alerts}</td>
                          <td className={cn('px-3 py-2 text-right tabular', r.failed + r.over_limit > 0 && 'text-destructive')}>
                            {r.failed + r.over_limit}
                          </td>
                          <td className="px-3 py-2 whitespace-nowrap text-muted-foreground">{r.last_sent_at ? formatDateTime(r.last_sent_at) : '—'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ))}
          </>
        )}
      </CardContent>
    </Card>
  )
}

