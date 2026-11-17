import { useMemo, useState } from 'react'
import { ArrowDown, ArrowUp, Plus, Search, Settings2, Users } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Switch } from '@/components/ui/form-controls'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/misc'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { SegmentedControl } from '@/components/ui/segmented-control'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { useAutoReportOverview } from '@/features/settings/api'
import { ContentChips, MANAGER_ONLY } from '@/features/settings/report-content'
import { cn } from '@/lib/utils'
import type { AutoReports, ReportSection } from '@/types/api'

type Sends = 'both' | 'midday' | 'evening'
type SortKey = 'name' | 'department' | 'team' | 'reports_to'
const ALL = '__all__'
const NONE = '__none__'

/** Settings → Automatic reports → Employee reports: each employee's own report, with per-person exceptions. */
export function EmployeeReportsCard({
  form,
  set,
  editable,
}: {
  form: AutoReports
  set: (patch: Partial<AutoReports>) => void
  editable: boolean
}) {
  const overview = useAutoReportOverview()
  const people = useMemo(() => overview.data?.employees ?? [], [overview.data])
  const [search, setSearch] = useState('')
  const [department, setDepartment] = useState(ALL)
  const [team, setTeam] = useState(ALL)
  const [sort, setSort] = useState<{ key: SortKey; desc: boolean }>({ key: 'department', desc: false })
  const off = !editable || !form.employee_reports_enabled
  const settings = useMemo(() => new Map(form.employee_settings.map((s) => [s.employee_id, s])), [form.employee_settings])

  const departments = useMemo(() => [...new Set(people.map((p) => p.department || NONE))].sort(), [people])
  const teams = useMemo(
    () =>
      [...new Set(people.filter((p) => department === ALL || (p.department || NONE) === department).map((p) => p.team || NONE))].sort(),
    [people, department],
  )
  const rows = useMemo(() => {
    const q = search.trim().toLowerCase()
    const value = (p: (typeof people)[number], key: SortKey) =>
      key === 'name' ? p.name : key === 'reports_to' ? (p.report_to?.name ?? '') : p[key]
    return people
      .filter(
        (p) =>
          (department === ALL || (p.department || NONE) === department) &&
          (team === ALL || (p.team || NONE) === team) &&
          (!q || p.name.toLowerCase().includes(q) || (p.report_to?.name ?? '').toLowerCase().includes(q)),
      )
      .sort((a, b) => {
        const primary = (value(a, sort.key) || '￿').localeCompare(value(b, sort.key) || '￿', undefined, { sensitivity: 'base' })
        return (sort.desc ? -1 : 1) * (primary || a.name.localeCompare(b.name))
      })
  }, [people, department, team, search, sort])

  const enabledFor = (id: string) => settings.get(id)?.enabled ?? true
  const update = (id: string, patch: { enabled?: boolean; sections?: ReportSection[] | null }) => {
    const current = settings.get(id) ?? { employee_id: id, enabled: true, sections: null }
    const next = { ...current, ...patch }
    const rest = form.employee_settings.filter((s) => s.employee_id !== id)
    const meaningful = !next.enabled || next.sections !== null
    set({ employee_settings: meaningful ? [...rest, next] : rest })
  }
  const sends: Sends = form.employee_midday && form.employee_evening ? 'both' : form.employee_midday ? 'midday' : 'evening'
  const receiving = people.filter((p) => enabledFor(p.id)).length
  const perDay = form.employee_reports_enabled ? receiving * (sends === 'both' ? 2 : 1) : 0
  const sortBy = (key: SortKey) => setSort((s) => ({ key, desc: s.key === key ? !s.desc : false }))
  const head = (key: SortKey, label: string) => (
    <button
      type="button"
      onClick={() => sortBy(key)}
      className={cn('inline-flex items-center gap-1 uppercase hover:text-foreground', sort.key === key && 'text-foreground')}
    >
      {label}
      {sort.key === key && (sort.desc ? <ArrowDown className="size-3" /> : <ArrowUp className="size-3" />)}
    </button>
  )

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2.5">
          <span className="flex size-8 items-center justify-center rounded-lg bg-success-soft text-success">
            <Users className="size-4" />
          </span>
          Employee reports
        </CardTitle>
        <CardDescription>Each employee gets their own report.</CardDescription>
        <CardAction>
          <Switch
            checked={form.employee_reports_enabled}
            onCheckedChange={(employee_reports_enabled) => set({ employee_reports_enabled })}
            disabled={!editable}
            aria-label="Employee reports"
          />
        </CardAction>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className={cn('divide-y', !form.employee_reports_enabled && 'opacity-70')}>
          <div className="grid gap-3 pb-4 sm:grid-cols-[13rem_minmax(0,1fr)] sm:gap-6">
            <div>
              <p className="text-[13px] font-medium">Schedule</p>
              <p className="mt-0.5 text-[12px] text-muted-foreground">Same times as above</p>
            </div>
            <div className="flex flex-wrap items-center gap-3">
              <div className={cn(off && 'pointer-events-none opacity-60')}>
                <SegmentedControl<Sends>
                  size="sm"
                  label="Employee report schedule"
                  value={sends}
                  onChange={(v) => set({ employee_midday: v !== 'evening', employee_evening: v !== 'midday' })}
                  options={[
                    { value: 'both', label: 'Twice daily' },
                    { value: 'evening', label: 'Evening' },
                    { value: 'midday', label: 'Mid-day' },
                  ]}
                />
              </div>
              {form.employee_reports_enabled && (
                <span className={cn('text-[12px]', perDay > 150 ? 'text-warning' : 'text-muted-foreground')}>
                  ≈ {perDay} e-mails a day{perDay > 150 ? ' · consider Evening only' : ''}
                </span>
              )}
            </div>
          </div>
          <div className="grid gap-3 py-4 sm:grid-cols-[13rem_minmax(0,1fr)] sm:gap-6">
            <div>
              <p className="text-[13px] font-medium">Default content</p>
              <p className="mt-0.5 text-[12px] text-muted-foreground">Summary is never AI here</p>
            </div>
            <ContentChips value={form.employee_sections} onChange={(employee_sections) => set({ employee_sections })} disabled={off} exclude={MANAGER_ONLY} />
          </div>
        </div>

        <div className="space-y-3 border-t pt-4">
          <div className="flex flex-wrap items-center gap-2">
            <div className="relative w-full sm:w-60">
              <Search className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
              <Input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search people…"
                aria-label="Search people"
                className="h-8 pl-8 text-[13px]"
              />
            </div>
            <Select
              value={department}
              onValueChange={(v) => {
                setDepartment(v)
                setTeam(ALL)
              }}
            >
              <SelectTrigger size="sm" className="w-44" aria-label="Department">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={ALL}>All departments</SelectItem>
                {departments.map((d) => (
                  <SelectItem key={d} value={d}>
                    {d === NONE ? 'No department' : d}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Select value={team} onValueChange={setTeam}>
              <SelectTrigger size="sm" className="w-40" aria-label="Team">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={ALL}>All teams</SelectItem>
                {teams.map((t) => (
                  <SelectItem key={t} value={t}>
                    {t === NONE ? 'No team' : t}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <span className="ml-auto text-[12px] text-muted-foreground">
              {receiving} of {people.length} receive
            </span>
          </div>

          {!overview.data ? (
            <Skeleton className="h-32" />
          ) : (
            <div className="max-h-[28rem] overflow-auto rounded-md border">
              <table className="w-full text-[13px]">
                <thead className="sticky top-0 z-10 bg-subtle text-left text-[11.5px] text-muted-foreground">
                  <tr>
                    <th className="px-3 py-2 font-medium">{head('name', 'Employee')}</th>
                    <th className="px-3 py-2 font-medium">{head('department', 'Department')}</th>
                    <th className="px-3 py-2 font-medium">{head('team', 'Team')}</th>
                    <th className="px-3 py-2 font-medium">{head('reports_to', 'Reports to')}</th>
                    <th className="px-3 py-2 font-medium uppercase">Content</th>
                    <th className="px-3 py-2 text-right font-medium uppercase">Own report</th>
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {rows.map((p) => {
                    const own = settings.get(p.id)
                    const on = own?.enabled ?? true
                    const custom = own?.sections ?? null
                    return (
                      <tr key={p.id} className={cn(!on && 'text-muted-foreground')}>
                        <td className="px-3 py-2 font-medium">{p.name}</td>
                        <td className="px-3 py-2">{p.department || <span className="text-muted-foreground">—</span>}</td>
                        <td className="px-3 py-2">{p.team || <span className="text-muted-foreground">—</span>}</td>
                        <td className="px-3 py-2">{p.report_to?.name ?? <span className="text-muted-foreground">—</span>}</td>
                        <td className="px-3 py-2" aria-label={`Report content for ${p.name}`}>
                          <Popover>
                            <PopoverTrigger asChild disabled={off || !on}>
                              <Button
                                type="button"
                                size="sm"
                                variant="ghost"
                                className="h-7 gap-1.5 px-2 text-[12px]"
                                aria-label={`Content for ${p.name}`}
                              >
                                {custom ? <Settings2 className="size-3.5" /> : <Plus className="size-3.5" />}
                                {custom ? `${custom.length} items` : 'Default'}
                              </Button>
                            </PopoverTrigger>
                            <PopoverContent align="start" className="w-[26rem] space-y-3">
                              <p className="text-[13px] font-medium">Content for {p.name}</p>
                              <ContentChips
                                value={custom ?? form.employee_sections}
                                onChange={(sections) => update(p.id, { sections: sections.length ? sections : null })}
                                exclude={MANAGER_ONLY}
                              />
                              <div className="flex justify-end">
                                <Button type="button" size="sm" variant="outline" onClick={() => update(p.id, { sections: null })} disabled={!custom}>
                                  Use default
                                </Button>
                              </div>
                            </PopoverContent>
                          </Popover>
                        </td>
                        <td className="px-3 py-2 text-right">
                          <Switch
                            checked={on}
                            onCheckedChange={(enabled) => update(p.id, { enabled })}
                            disabled={off}
                            aria-label={`Own report for ${p.name}`}
                          />
                        </td>
                      </tr>
                    )
                  })}
                  {rows.length === 0 && (
                    <tr>
                      <td colSpan={6} className="px-3 py-6 text-center text-muted-foreground">
                        No one matches.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  )
}
