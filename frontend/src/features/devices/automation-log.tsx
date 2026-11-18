import { useMemo, useState } from 'react'
import { Bot } from 'lucide-react'

import { EmptyState } from '@/components/common/empty-state'
import { Badge } from '@/components/ui/badge'
import { Card } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/misc'
import { SegmentedControl } from '@/components/ui/segmented-control'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { WidgetError } from '@/features/dashboard/components/widget'
import { useAutomationChecks } from '@/features/devices/api'
import { minutesText, useRange, type Range } from '@/features/devices/device-log'
import { formatDateTime, formatTime } from '@/lib/format'
import type { AutomationCheckRow } from '@/types/api'

const ALL = '__all__'

const STATUS: Record<AutomationCheckRow['status'], { label: string; variant: 'destructive' | 'warning' | 'success' | 'secondary' | 'info'; help: string }> = {
  unanswered: {
    label: 'Not answered',
    variant: 'destructive',
    help: 'The mouse kept moving with no click or typing, and nobody answered “Are you still working?”.',
  },
  software: {
    label: 'Software input',
    variant: 'warning',
    help: 'Only software-made input (a mouse-mover app or remote control). This time already counts as idle.',
  },
  answered: { label: 'Answered', variant: 'success', help: 'The person confirmed they were working.' },
  stopped: { label: 'Stopped by itself', variant: 'secondary', help: 'The movement stopped before the question was answered or reported.' },
  asking: { label: 'Asking now', variant: 'info', help: 'The question is on the person’s screen right now.' },
}

/** Possible automated input: mouse jigglers, a mouse on a watch or fan, and mouse-mover apps. */
export function AutomationLog() {
  const [range, setRange] = useState<Range>('7d')
  const [status, setStatus] = useState<string>(ALL)
  const [department, setDepartment] = useState(ALL)
  const query = useAutomationChecks(useRange(range))
  const rows = useMemo(() => query.data ?? [], [query.data])
  const departments = useMemo(() => [...new Set(rows.map((r) => r.department || 'No department'))].sort(), [rows])
  const shown = rows.filter(
    (r) => (status === ALL || r.status === status) && (department === ALL || (r.department || 'No department') === department),
  )
  const flagged = rows.filter((r) => r.status === 'unanswered' || r.status === 'software').length

  return (
    <Card className="overflow-hidden">
      <div className="flex flex-wrap items-center gap-2 border-b px-4 py-3">
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
        <Select value={status} onValueChange={setStatus}>
          <SelectTrigger size="sm" className="w-44" aria-label="Result">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>All results</SelectItem>
            {(Object.keys(STATUS) as AutomationCheckRow['status'][]).map((s) => (
              <SelectItem key={s} value={s}>
                {STATUS[s].label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
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
        {query.data && (
          <p className="ml-auto text-[12.5px] text-muted-foreground">
            <b className="text-foreground tabular">{flagged}</b> reported · <b className="text-foreground tabular">{rows.length}</b> checks
          </p>
        )}
      </div>
      {query.isError ? (
        <div className="p-4">
          <WidgetError error={query.error} onRetry={() => void query.refetch()} />
        </div>
      ) : !query.data ? (
        <div className="space-y-2 p-4">
          <Skeleton className="h-10" />
          <Skeleton className="h-10" />
        </div>
      ) : shown.length === 0 ? (
        <EmptyState
          icon={Bot}
          title={rows.length ? 'Nothing matches these filters' : 'No automated activity'}
          description="When the mouse moves for a long time with no click or typing, WorkPulse asks “Are you still working?”. Unanswered checks and mouse-mover apps appear here (WorkPulse 1.0.2 or later)."
          size="sm"
        />
      ) : (
        <div className="max-h-[70vh] overflow-auto">
          <table className="w-full text-[13px]">
            <thead className="sticky top-0 z-10 bg-subtle text-left text-[11.5px] text-muted-foreground uppercase">
              <tr>
                <th className="px-3 py-2 font-medium">When</th>
                <th className="px-3 py-2 font-medium">Employee</th>
                <th className="px-3 py-2 font-medium">Computer</th>
                <th className="px-3 py-2 font-medium">Result</th>
                <th className="px-3 py-2 font-medium">How long</th>
                <th className="px-3 py-2 font-medium">Details</th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {shown.map((r) => {
                const meta = STATUS[r.status]
                return (
                  <tr key={r.id} className="align-top">
                    <td className="px-3 py-2.5 whitespace-nowrap">
                      <p className="tabular">{formatDateTime(r.started_at)}</p>
                      <p className="text-[11.5px] text-muted-foreground">{r.ended_at ? `until ${formatTime(r.ended_at)}` : 'still going'}</p>
                    </td>
                    <td className="px-3 py-2.5">
                      <p className="font-medium">{r.employee}</p>
                      <p className="text-[11.5px] text-muted-foreground">{[r.department, r.team].filter(Boolean).join(' · ') || '—'}</p>
                    </td>
                    <td className="px-3 py-2.5 whitespace-nowrap text-muted-foreground">{r.laptop}</td>
                    <td className="px-3 py-2.5">
                      <Badge variant={meta.variant} title={meta.help}>
                        {meta.label}
                      </Badge>
                      <p className="mt-1 max-w-56 text-[11.5px] text-muted-foreground">{meta.help}</p>
                    </td>
                    <td className="px-3 py-2.5 whitespace-nowrap tabular">{minutesText(r.minutes)}</td>
                    <td className="px-3 py-2.5 text-[12.5px] text-muted-foreground">
                      {r.kind === 'hardware' ? (
                        <>
                          <p>No click, scroll or typing · moved within {r.max_span_px} px</p>
                          {r.asked_at && <p>Asked at {formatTime(r.asked_at)}</p>}
                        </>
                      ) : (
                        <p>No real keyboard or mouse use</p>
                      )}
                      {r.apps.length > 0 && <p>Open: {r.apps.join(', ')}</p>}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  )
}
