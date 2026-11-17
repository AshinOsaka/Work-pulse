import { useMemo, useState } from 'react'
import { ArrowDown, ArrowUp, History } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/misc'
import { SegmentedControl } from '@/components/ui/segmented-control'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { shiftDay, todayIn } from '@/features/activity/format'
import { useUnproductiveAlerts } from '@/features/settings/api'
import { formatDateTime } from '@/lib/format'
import { cn } from '@/lib/utils'
import { useAuthStore } from '@/stores/auth-store'
import type { UnproductiveAlertRow } from '@/types/api'

type Range = 'today' | '7d' | '30d'
type SortKey = 'at' | 'employee' | 'department' | 'team' | 'manager' | 'minutes'
const ALL = '__all__'

const COLUMNS: { key: SortKey; label: string; align?: 'right' }[] = [
  { key: 'at', label: 'When' },
  { key: 'employee', label: 'Employee' },
  { key: 'department', label: 'Department' },
  { key: 'team', label: 'Team' },
  { key: 'manager', label: 'Manager told' },
  { key: 'minutes', label: 'Minutes', align: 'right' },
]

function compare(a: UnproductiveAlertRow, b: UnproductiveAlertRow, key: SortKey): number {
  if (key === 'minutes') return (a.minutes ?? -1) - (b.minutes ?? -1)
  if (key === 'at') return a.at.localeCompare(b.at)
  return (a[key] || '￿').localeCompare(b[key] || '￿', undefined, { sensitivity: 'base' })
}

/** Unproductive alerts sent: who, their department, team and manager, sortable and filtered by date. */
export function UnproductiveHistory() {
  const timeZone = useAuthStore((s) => s.company?.timezone ?? 'UTC')
  const today = todayIn(timeZone)
  const [range, setRange] = useState<Range>('7d')
  const [department, setDepartment] = useState(ALL)
  const [sort, setSort] = useState<{ key: SortKey; desc: boolean }>({ key: 'at', desc: true })
  const start = range === 'today' ? today : shiftDay(today, range === '7d' ? -6 : -29)
  const query = useUnproductiveAlerts(start, today)
  const rows = useMemo(() => query.data ?? [], [query.data])
  const departments = useMemo(
    () => [...new Set(rows.map((r) => r.department || 'No department'))].sort((a, b) => a.localeCompare(b)),
    [rows],
  )
  const shown = useMemo(() => {
    const list = rows.filter((r) => department === ALL || (r.department || 'No department') === department)
    return [...list].sort((a, b) => (sort.desc ? -1 : 1) * compare(a, b, sort.key))
  }, [rows, department, sort])
  const sortBy = (key: SortKey) => setSort((s) => ({ key, desc: s.key === key ? !s.desc : key === 'at' || key === 'minutes' }))

  return (
    <div className="space-y-3 border-t pt-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="flex items-center gap-2 text-[13px] font-medium">
          <History className="size-4 text-muted-foreground" /> Alert history
          {query.data && <span className="text-[12px] font-normal text-muted-foreground">· {shown.length}</span>}
        </p>
        <div className="flex flex-wrap items-center gap-2">
          <Select value={department} onValueChange={setDepartment}>
            <SelectTrigger size="sm" className="w-44" aria-label="Department">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={ALL}>All departments</SelectItem>
              {departments.map((d) => (
                <SelectItem key={d} value={d}>
                  {d}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <SegmentedControl<Range>
            size="sm"
            label="Period"
            value={range}
            onChange={setRange}
            options={[
              { value: 'today', label: 'Today' },
              { value: '7d', label: '7 days' },
              { value: '30d', label: '30 days' },
            ]}
          />
        </div>
      </div>
      {!query.data ? (
        <Skeleton className="h-24" />
      ) : shown.length === 0 ? (
        <p className="rounded-md border border-dashed px-3 py-6 text-center text-[13px] text-muted-foreground">No alerts in this period.</p>
      ) : (
        <div className="max-h-96 overflow-auto rounded-md border">
          <table className="w-full text-[13px]">
            <thead className="sticky top-0 bg-subtle text-left text-[11.5px] text-muted-foreground uppercase">
              <tr>
                {COLUMNS.map((c) => (
                  <th key={c.key} className={cn('px-3 py-2 font-medium', c.align === 'right' && 'text-right')}>
                    <button
                      type="button"
                      onClick={() => sortBy(c.key)}
                      className={cn('inline-flex items-center gap-1 uppercase hover:text-foreground', sort.key === c.key && 'text-foreground')}
                    >
                      {c.label}
                      {sort.key === c.key && (sort.desc ? <ArrowDown className="size-3" /> : <ArrowUp className="size-3" />)}
                    </button>
                  </th>
                ))}
                <th className="px-3 py-2 font-medium">Type</th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {shown.map((r, i) => (
                <tr key={`${r.at}-${r.employee_id}-${i}`} className="align-top">
                  <td className="px-3 py-2 whitespace-nowrap text-muted-foreground">{formatDateTime(r.at)}</td>
                  <td className="px-3 py-2">
                    <p className="font-medium">{r.employee}</p>
                    {r.where && <p className="text-[11.5px] text-muted-foreground">{r.where}</p>}
                  </td>
                  <td className="px-3 py-2">{r.department || <span className="text-muted-foreground">—</span>}</td>
                  <td className="px-3 py-2">{r.team || <span className="text-muted-foreground">—</span>}</td>
                  <td className="px-3 py-2">{r.manager || <span className="text-muted-foreground">—</span>}</td>
                  <td className="px-3 py-2 text-right tabular">{r.minutes ?? '—'}</td>
                  <td className="px-3 py-2 whitespace-nowrap">
                    {r.kind === 'continuous' ? (
                      <Badge variant="destructive">No break{r.span ? ` · ${r.span}` : ''}</Badge>
                    ) : (
                      <Badge variant="warning">Daily total</Badge>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
