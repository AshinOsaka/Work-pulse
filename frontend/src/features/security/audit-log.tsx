import { Fragment, useState } from 'react'
import { ChevronDown, ScrollText } from 'lucide-react'

import { EmptyState } from '@/components/common/empty-state'
import { FilterSelect } from '@/components/common/filter-select'
import { Pagination } from '@/components/common/pagination'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/misc'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { WidgetError } from '@/features/dashboard/components/widget'
import { EmployeePicker } from '@/features/people/components/employee-picker'
import { useAuditCategories, useAuditLog, type AuditEntry } from '@/features/security/api'
import { formatDateTime } from '@/lib/format'
import { cn } from '@/lib/utils'

const ALL = '__all__'

function detailText(value: unknown): string {
  if (Array.isArray(value)) return value.join(', ')
  if (value === null || value === undefined || value === '') return '—'
  return String(value)
}

function Details({ entry }: { entry: AuditEntry }) {
  const rows: [string, string][] = [
    ['Event', entry.action],
    ...(entry.target_type ? ([['Target', `${entry.target_type} ${entry.target_id ?? ''}`.trim()]] as [string, string][]) : []),
    ['IP address', entry.ip_address ?? '—'],
    ['Browser or app', entry.device ?? '—'],
    ...Object.entries(entry.details).map(([k, v]) => [k.replace(/_/g, ' '), detailText(v)] as [string, string]),
  ]
  return (
    <dl className="grid gap-x-6 gap-y-1 text-[12px] sm:grid-cols-[10rem_1fr]">
      {rows.map(([k, v]) => (
        <Fragment key={k}>
          <dt className="text-muted-foreground capitalize">{k}</dt>
          <dd className="font-mono break-all">{v}</dd>
        </Fragment>
      ))}
    </dl>
  )
}

export function AuditLog() {
  const categories = useAuditCategories()
  const [category, setCategory] = useState(ALL)
  const [employee, setEmployee] = useState<string | null>(null)
  const [start, setStart] = useState('')
  const [end, setEnd] = useState('')
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(50)
  const [open, setOpen] = useState<string | null>(null)
  const log = useAuditLog({
    category: category === ALL ? undefined : category,
    employee_id: employee ?? undefined,
    start: start || undefined,
    end: end || undefined,
    page,
    page_size: pageSize,
  })
  const label = (key: string | null) => categories.data?.find((c) => c.key === key)?.label ?? 'Other'
  const filtered = category !== ALL || employee || start || end

  return (
    <Card className="overflow-hidden">
      <CardHeader className="pb-4">
        <CardTitle>Audit log</CardTitle>
        <CardDescription>
          Sign-ins, access to screenshots and live screens, report exports, and changes to roles, policies and people. Entries can't be
          edited or deleted.
        </CardDescription>
      </CardHeader>
      <div className="grid gap-3 border-t px-5 py-3 sm:grid-cols-2 lg:grid-cols-[14rem_14rem_9.5rem_9.5rem_auto] lg:items-end">
        <div className="space-y-1">
          <Label htmlFor="audit-category" className="text-[12px]">
            Type
          </Label>
          <FilterSelect
            id="audit-category"
            label="Category"
            value={category === ALL ? null : category}
            onChange={(v) => {
              setCategory(v ?? ALL)
              setPage(1)
            }}
            options={(categories.data ?? []).map((c) => ({ value: c.key, label: c.label }))}
            allLabel="All events"
            className="sm:w-full"
          />
        </div>
        <div className="space-y-1">
          <Label htmlFor="audit-person" className="text-[12px]">
            About
          </Label>
          <EmployeePicker
            id="audit-person"
            value={employee}
            onChange={(v) => {
              setEmployee(v)
              setPage(1)
            }}
            placeholder="Anyone"
          />
        </div>
        <div className="space-y-1">
          <Label htmlFor="audit-from" className="text-[12px]">
            From
          </Label>
          <Input id="audit-from" type="date" value={start} max={end || undefined} onChange={(e) => {
              setStart(e.target.value)
              setPage(1)
            }} className="h-8 text-[13px]" />
        </div>
        <div className="space-y-1">
          <Label htmlFor="audit-to" className="text-[12px]">
            To
          </Label>
          <Input id="audit-to" type="date" value={end} min={start || undefined} onChange={(e) => {
              setEnd(e.target.value)
              setPage(1)
            }} className="h-8 text-[13px]" />
        </div>
        {filtered && (
          <Button
            size="sm"
            variant="ghost"
            onClick={() => {
              setCategory(ALL)
              setEmployee(null)
              setStart('')
              setEnd('')
              setPage(1)
            }}
          >
            Clear filters
          </Button>
        )}
      </div>
      {log.isPending ? (
        <div className="space-y-2 p-5">
          {Array.from({ length: 6 }, (_, i) => (
            <Skeleton key={i} className="h-9" />
          ))}
        </div>
      ) : log.isError ? (
        <WidgetError error={log.error} onRetry={() => void log.refetch()} />
      ) : log.data.total === 0 ? (
        <EmptyState icon={ScrollText} title="No events" description={filtered ? 'Nothing matches these filters.' : 'Nothing has been recorded yet.'} />
      ) : (
        <>
          <div className="relative overflow-x-auto">
            <Table className="text-[13px]">
              <TableHeader>
                <TableRow className="hover:bg-transparent">
                  <TableHead className="pl-5 whitespace-nowrap">When</TableHead>
                  <TableHead>Event</TableHead>
                  <TableHead>By</TableHead>
                  <TableHead>About</TableHead>
                  <TableHead className="w-10">
                    <span className="sr-only">Details</span>
                  </TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {log.data.items.map((entry) => {
                  const expanded = open === entry.id
                  return (
                    <Fragment key={entry.id}>
                      <TableRow>
                        <TableCell className="pl-5 whitespace-nowrap text-muted-foreground tabular">{formatDateTime(entry.at)}</TableCell>
                        <TableCell>
                          <p className="font-medium">{entry.label}</p>
                          <Badge variant="outline" className="mt-0.5 text-[11px]">
                            {label(entry.category)}
                          </Badge>
                        </TableCell>
                        <TableCell>{entry.actor ? <span title={entry.actor.email ?? undefined}>{entry.actor.name}</span> : <span className="text-muted-foreground">System</span>}</TableCell>
                        <TableCell>{entry.subject?.name ?? <span className="text-muted-foreground">—</span>}</TableCell>
                        <TableCell>
                          <Button
                            size="icon-sm"
                            variant="ghost"
                            aria-expanded={expanded}
                            aria-label={`${expanded ? 'Hide' : 'Show'} details for ${entry.label}`}
                            onClick={() => setOpen(expanded ? null : entry.id)}
                          >
                            <ChevronDown className={cn('transition-transform', expanded && 'rotate-180')} />
                          </Button>
                        </TableCell>
                      </TableRow>
                      {expanded && (
                        <TableRow className="bg-muted/30 hover:bg-muted/30">
                          <TableCell colSpan={5} className="px-5 py-3">
                            <Details entry={entry} />
                          </TableCell>
                        </TableRow>
                      )}
                    </Fragment>
                  )
                })}
              </TableBody>
            </Table>
          </div>
          <div className="border-t">
            <Pagination
              page={log.data.page}
              pages={log.data.pages}
              pageSize={log.data.page_size}
              total={log.data.total}
              onPageChange={setPage}
              onPageSizeChange={(size) => {
                setPageSize(size)
                setPage(1)
              }}
            />
          </div>
        </>
      )}
    </Card>
  )
}
