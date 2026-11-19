import { useMemo, useState } from 'react'
import { ArrowDown, ArrowUp, Copy, MonitorCheck, Search } from 'lucide-react'
import { toast } from 'sonner'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/misc'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { WidgetError } from '@/features/dashboard/components/widget'
import { useAgentVersions } from '@/features/devices/api'
import { formatDateTime, formatRelative } from '@/lib/format'
import { cn } from '@/lib/utils'
import type { AgentVersionRow, AgentVersionStatus } from '@/types/api'

const ALL = '__all__'

const STATUS: Record<AgentVersionStatus, { label: string; help: string; variant: 'success' | 'info' | 'destructive' | 'warning' | 'secondary' | 'outline' }> = {
  latest: { label: 'Latest', help: 'Up to date.', variant: 'success' },
  waiting: { label: 'Update ready', help: 'Downloaded; installs when the person clicks Install now, or by itself soon.', variant: 'info' },
  failed: { label: 'Update failed', help: 'The last attempt failed; it tries again later.', variant: 'destructive' },
  old: { label: 'Old version', help: 'Updates by itself within about 15 minutes of going online.', variant: 'warning' },
  manual: { label: 'Install by hand', help: 'Too old to update itself: run the installer once on this computer.', variant: 'destructive' },
  unknown: { label: 'Unknown', help: 'No version published yet, or the computer hasn’t reported its version.', variant: 'outline' },
}
const ORDER: AgentVersionStatus[] = ['failed', 'manual', 'old', 'waiting', 'unknown', 'latest']

type SortKey = 'employee' | 'department' | 'version' | 'status' | 'last_seen_at'

function compareVersion(a: string | null, b: string | null): number {
  const pa = (a ?? '').split('.').map(Number)
  const pb = (b ?? '').split('.').map(Number)
  for (let i = 0; i < Math.max(pa.length, pb.length); i += 1) {
    const d = (pa[i] || 0) - (pb[i] || 0)
    if (d) return d
  }
  return 0
}

function compare(a: AgentVersionRow, b: AgentVersionRow, key: SortKey): number {
  if (key === 'version') return compareVersion(a.version, b.version)
  if (key === 'status') return ORDER.indexOf(a.status) - ORDER.indexOf(b.status)
  if (key === 'last_seen_at') return (a.last_seen_at ?? '').localeCompare(b.last_seen_at ?? '')
  return (a[key] || '￿').localeCompare(b[key] || '￿', undefined, { sensitivity: 'base' })
}

/** Every computer's WorkPulse version: who is up to date, who is waiting, who needs help. */
export function AgentVersionsCard() {
  const query = useAgentVersions()
  const [status, setStatus] = useState<string>(ALL)
  const [department, setDepartment] = useState(ALL)
  const [search, setSearch] = useState('')
  const [sort, setSort] = useState<{ key: SortKey; desc: boolean }>({ key: 'status', desc: false })
  const rows = useMemo(() => query.data?.computers ?? [], [query.data])
  const departments = useMemo(() => [...new Set(rows.map((r) => r.department || 'No department'))].sort(), [rows])
  const shown = useMemo(() => {
    const needle = search.trim().toLowerCase()
    const list = rows.filter(
      (r) =>
        (status === ALL || r.status === status) &&
        (department === ALL || (r.department || 'No department') === department) &&
        (!needle || [r.employee, r.computer, r.version ?? ''].some((v) => v.toLowerCase().includes(needle))),
    )
    return [...list].sort((a, b) => (sort.desc ? -1 : 1) * compare(a, b, sort.key))
  }, [rows, status, department, search, sort])
  const counts = useMemo(() => {
    const c: Partial<Record<AgentVersionStatus, number>> = {}
    for (const r of rows) c[r.status] = (c[r.status] ?? 0) + 1
    return c
  }, [rows])
  const sortBy = (key: SortKey) => setSort((s) => ({ key, desc: s.key === key ? !s.desc : key === 'last_seen_at' }))
  const data = query.data

  const header = (key: SortKey, label: string) => (
    <th className="px-3 py-2 font-medium">
      <button
        type="button"
        onClick={() => sortBy(key)}
        className={cn('inline-flex items-center gap-1 uppercase hover:text-foreground', sort.key === key && 'text-foreground')}
      >
        {label}
        {sort.key === key && (sort.desc ? <ArrowDown className="size-3" /> : <ArrowUp className="size-3" />)}
      </button>
    </th>
  )

  return (
    <Card className="overflow-hidden">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <MonitorCheck className="size-4 text-muted-foreground" aria-hidden /> Computers &amp; versions
          {data?.latest && <Badge variant="secondary">Latest v{data.latest}</Badge>}
        </CardTitle>
        <CardDescription>
          Which WorkPulse version each computer runs. Computers update by themselves (version 0.8.5 and later); from 1.0.3 the
          person can also click “Install now”.
          {data && !data.auto_update && ' Automatic updates are paused for this workspace (Settings → Workspace → Activity tracking).'}
          {data && !data.latest && ' No version is published for automatic updates yet (AGENT_VERSION, AGENT_DOWNLOAD_URL and AGENT_SHA256 on the server).'}
        </CardDescription>
      </CardHeader>
      {query.isError ? (
        <div className="p-4">
          <WidgetError error={query.error} onRetry={() => void query.refetch()} />
        </div>
      ) : !data ? (
        <div className="space-y-2 p-4">
          <Skeleton className="h-10" />
          <Skeleton className="h-10" />
        </div>
      ) : (
        <>
          <div className="grid grid-cols-2 gap-2 border-y bg-subtle px-4 py-3 sm:grid-cols-4">
            {[
              { label: 'On the latest version', value: `${counts.latest ?? 0} of ${rows.length}`, tone: 'text-success' },
              { label: 'Update ready / updating soon', value: String((counts.waiting ?? 0) + (counts.old ?? 0)), tone: 'text-info' },
              { label: 'Update failed', value: String(counts.failed ?? 0), tone: counts.failed ? 'text-destructive' : '' },
              { label: 'Need a manual install', value: String(counts.manual ?? 0), tone: counts.manual ? 'text-destructive' : '' },
            ].map((t) => (
              <div key={t.label} className="rounded-md border bg-background px-3 py-2">
                <p className="text-[11.5px] text-muted-foreground">{t.label}</p>
                <p className={cn('text-lg font-semibold tabular', t.tone)}>{t.value}</p>
              </div>
            ))}
          </div>
          <div className="flex flex-wrap items-center gap-2 px-4 py-3">
            <Select value={status} onValueChange={setStatus}>
              <SelectTrigger size="sm" className="w-44" aria-label="Status">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={ALL}>All statuses</SelectItem>
                {ORDER.map((s) => (
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
            <div className="relative w-full sm:w-56">
              <Search className="pointer-events-none absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2 text-muted-foreground" aria-hidden />
              <Input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search person, computer…" className="h-8 pl-8 text-[13px]" aria-label="Search" />
            </div>
            {data.download_url && (
              <Button
                variant="outline"
                size="sm"
                className="ml-auto"
                onClick={() =>
                  void navigator.clipboard
                    .writeText(data.download_url ?? '')
                    .then(() => toast.success('Download link copied'))
                    .catch(() => toast.error('Copy failed'))
                }
              >
                <Copy /> Copy download link
              </Button>
            )}
          </div>
          {shown.length === 0 ? (
            <p className="mx-4 mb-4 rounded-md border border-dashed px-3 py-6 text-center text-[13px] text-muted-foreground">
              {rows.length ? 'Nothing matches these filters.' : 'No computers have WorkPulse yet.'}
            </p>
          ) : (
            <div className="max-h-[60vh] overflow-auto border-t">
              <table className="w-full text-[13px]">
                <thead className="sticky top-0 z-10 bg-subtle text-left text-[11.5px] text-muted-foreground uppercase">
                  <tr>
                    {header('employee', 'Employee')}
                    <th className="px-3 py-2 font-medium">Computer</th>
                    {header('version', 'Version')}
                    {header('status', 'Status')}
                    {header('last_seen_at', 'Last seen')}
                    <th className="px-3 py-2 font-medium">Installed / updated</th>
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {shown.map((r) => (
                    <tr key={r.device_id} className="align-top">
                      <td className="px-3 py-2.5">
                        <p className="font-medium">{r.employee}</p>
                        <p className="text-[11.5px] text-muted-foreground">{r.department || '—'}</p>
                      </td>
                      <td className="px-3 py-2.5 text-muted-foreground">{r.computer}</td>
                      <td className="px-3 py-2.5 tabular">{r.version ? `v${r.version}` : '—'}</td>
                      <td className="px-3 py-2.5">
                        <Badge variant={STATUS[r.status].variant}>{STATUS[r.status].label}</Badge>
                        <p className="mt-1 max-w-64 text-[11.5px] text-muted-foreground">{r.update_reason ?? STATUS[r.status].help}</p>
                      </td>
                      <td className="px-3 py-2.5 whitespace-nowrap text-muted-foreground" title={r.last_seen_at ? formatDateTime(r.last_seen_at) : undefined}>
                        {r.last_seen_at ? formatRelative(r.last_seen_at) : 'never'}
                      </td>
                      <td className="px-3 py-2.5 whitespace-nowrap text-muted-foreground">{r.updated_at ? formatDateTime(r.updated_at) : '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </Card>
  )
}
