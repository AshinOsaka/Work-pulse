import { useMemo, useState } from 'react'
import {
  ArrowDown,
  ArrowUp,
  FileStack,
  HardDrive,
  Headphones,
  Keyboard,
  Mouse,
  Search,
  ShieldCheck,
  Smartphone,
  Usb,
  Webcam,
  type LucideIcon,
} from 'lucide-react'
import { toast } from 'sonner'

import { EmptyState } from '@/components/common/empty-state'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/misc'
import { SegmentedControl } from '@/components/ui/segmented-control'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { shiftDay, todayIn } from '@/features/activity/format'
import { useActivityPolicy, useUpdateActivityPolicy } from '@/features/activity/api'
import { useConnectionFiles, useDeviceConnections } from '@/features/devices/api'
import { WidgetError } from '@/features/dashboard/components/widget'
import { errorMessage } from '@/lib/api-client'
import { formatDateTime, formatTime } from '@/lib/format'
import { cn } from '@/lib/utils'
import { useAuthStore, usePermissions } from '@/stores/auth-store'
import type { DeviceConnectionRow, DeviceKind, UsbFileRow } from '@/types/api'

export type Range = 'today' | '7d' | '30d'
const ALL = '__all__'

export const KINDS: Record<DeviceKind, { label: string; plural: string; icon: LucideIcon }> = {
  storage: { label: 'USB drive', plural: 'USB drives', icon: HardDrive },
  phone: { label: 'Phone', plural: 'Phones', icon: Smartphone },
  mouse: { label: 'Mouse', plural: 'Mice', icon: Mouse },
  keyboard: { label: 'Keyboard', plural: 'Keyboards', icon: Keyboard },
  camera: { label: 'Camera', plural: 'Cameras', icon: Webcam },
  audio: { label: 'Headset / audio', plural: 'Headsets & audio', icon: Headphones },
}

export function bytes(size: number | null | undefined): string {
  if (!size) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let value = size
  let i = 0
  while (value >= 1000 && i < units.length - 1) {
    value /= 1000
    i += 1
  }
  return `${value >= 10 || i < 2 ? Math.round(value) : value.toFixed(1)} ${units[i]}`
}

export function minutesText(minutes: number): string {
  if (minutes < 1) return 'under a minute'
  const h = Math.floor(minutes / 60)
  const m = Math.round(minutes % 60)
  return h ? `${h}h ${String(m).padStart(2, '0')}m` : `${m} min`
}

export function useRange(range: Range) {
  const timeZone = useAuthStore((s) => s.company?.timezone ?? 'UTC')
  const today = todayIn(timeZone)
  return { start: range === 'today' ? today : shiftDay(today, range === '7d' ? -6 : -29), end: today }
}

const ACTIONS: Record<UsbFileRow['action'], { label: string; variant: 'destructive' | 'warning' | 'secondary' | 'info' | 'outline' }> = {
  added: { label: 'Copied to USB', variant: 'destructive' },
  changed: { label: 'Changed on USB', variant: 'warning' },
  deleted: { label: 'Deleted from USB', variant: 'secondary' },
  renamed: { label: 'Renamed', variant: 'outline' },
  copied_to_computer: { label: 'Copied to computer', variant: 'info' },
  copied_to_phone: { label: 'Copied to phone', variant: 'destructive' },
  copied_from_phone: { label: 'Copied from phone', variant: 'info' },
  more: { label: 'More', variant: 'outline' },
}

function FilesDialog({ row, onClose }: { row: DeviceConnectionRow | null; onClose: () => void }) {
  const files = useConnectionFiles(row?.id ?? null)
  return (
    <Dialog open={!!row} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-3xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <FileStack className="size-4 text-muted-foreground" aria-hidden /> Files · {row?.title}
          </DialogTitle>
          <DialogDescription>
            {row?.employee} on {row?.laptop}, connected {row ? formatDateTime(row.connected_at) : ''}. File names and sizes
            only — no file is ever opened.
          </DialogDescription>
        </DialogHeader>
        {files.isError ? (
          <WidgetError error={files.error} onRetry={() => void files.refetch()} />
        ) : !files.data ? (
          <Skeleton className="h-32" />
        ) : files.data.length === 0 ? (
          <p className="rounded-md border border-dashed px-3 py-6 text-center text-[13px] text-muted-foreground">No file changes recorded.</p>
        ) : (
          <div className="max-h-[60vh] overflow-auto rounded-md border">
            <table className="w-full text-[13px]">
              <thead className="sticky top-0 bg-subtle text-left text-[11.5px] text-muted-foreground uppercase">
                <tr>
                  <th className="px-3 py-2 font-medium">Time</th>
                  <th className="px-3 py-2 font-medium">What</th>
                  <th className="px-3 py-2 font-medium">File</th>
                  <th className="px-3 py-2 text-right font-medium">Size</th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {files.data.map((f, i) => (
                  <tr key={`${f.path}-${i}`} className="align-top">
                    <td className="px-3 py-2 whitespace-nowrap text-muted-foreground tabular">{formatTime(f.at)}</td>
                    <td className="px-3 py-2 whitespace-nowrap">
                      <Badge variant={ACTIONS[f.action].variant}>{ACTIONS[f.action].label}</Badge>
                    </td>
                    <td className="px-3 py-2 break-all">
                      {f.path}
                      {f.previous && <p className="text-[11.5px] text-muted-foreground">was {f.previous}</p>}
                    </td>
                    <td className="px-3 py-2 text-right whitespace-nowrap tabular">{f.size != null ? bytes(f.size) : '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}

type SortKey = 'connected_at' | 'employee' | 'department' | 'kind' | 'laptop'
const COLUMNS: { key: SortKey; label: string }[] = [
  { key: 'connected_at', label: 'Plugged in' },
  { key: 'employee', label: 'Employee' },
  { key: 'laptop', label: 'Computer' },
  { key: 'kind', label: 'Device' },
]

function connectedMinutes(row: DeviceConnectionRow): number | null {
  if (!row.disconnected_at) return null
  return (new Date(row.disconnected_at).getTime() - new Date(row.connected_at).getTime()) / 60_000
}

/** Devices plugged into employees' computers: who, which computer, which device, when, and files copied. */
export function DeviceLog() {
  const { can } = usePermissions()
  const admin = can('POLICY_MANAGE')
  const [range, setRange] = useState<Range>('7d')
  const [kind, setKind] = useState<string>(ALL)
  const [department, setDepartment] = useState(ALL)
  const [search, setSearch] = useState('')
  const [sort, setSort] = useState<{ key: SortKey; desc: boolean }>({ key: 'connected_at', desc: true })
  const [open, setOpen] = useState<DeviceConnectionRow | null>(null)
  const query = useDeviceConnections(useRange(range))
  const policy = useActivityPolicy()
  const update = useUpdateActivityPolicy()
  const rows = useMemo(() => query.data ?? [], [query.data])
  const departments = useMemo(() => [...new Set(rows.map((r) => r.department || 'No department'))].sort(), [rows])
  const shown = useMemo(() => {
    const needle = search.trim().toLowerCase()
    const list = rows.filter(
      (r) =>
        (kind === ALL || r.kind === kind) &&
        (department === ALL || (r.department || 'No department') === department) &&
        (!needle || [r.employee, r.title, r.laptop, r.team].some((v) => v.toLowerCase().includes(needle))),
    )
    return [...list].sort((a, b) => {
      const x = sort.key === 'connected_at' ? a.connected_at.localeCompare(b.connected_at) : (a[sort.key] || '￿').localeCompare(b[sort.key] || '￿')
      return sort.desc ? -x : x
    })
  }, [rows, kind, department, search, sort])
  const sortBy = (key: SortKey) => setSort((s) => ({ key, desc: s.key === key ? !s.desc : key === 'connected_at' }))
  const tracking = policy.data?.track_devices

  const allow = (row: DeviceConnectionRow) => {
    if (!policy.data) return
    const allowed = [...policy.data.allowed_devices, { key: row.device_key, name: row.name, kind: row.kind }]
    update.mutate(
      { allowed_devices: allowed },
      {
        onSuccess: () => {
          toast.success('Marked as allowed', { description: `${row.name} is still logged, but no longer raises an alert.` })
          void query.refetch()
        },
        onError: (error) => toast.error(errorMessage(error)),
      },
    )
  }

  const usbCount = rows.filter((r) => r.kind === 'storage').length
  const filesTo = rows.reduce((n, r) => n + (r.file_counts.added ?? 0) + (r.file_counts.changed ?? 0) + (r.file_counts.copied_to_phone ?? 0), 0)
  const filesFrom = rows.reduce((n, r) => n + (r.file_counts.copied_to_computer ?? 0) + (r.file_counts.copied_from_phone ?? 0), 0)

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
        <Select value={kind} onValueChange={setKind}>
          <SelectTrigger size="sm" className="w-40" aria-label="Device type">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>All devices</SelectItem>
            {(Object.keys(KINDS) as DeviceKind[]).map((k) => (
              <SelectItem key={k} value={k}>
                {KINDS[k].plural}
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
        <div className="relative ml-auto w-full sm:w-56">
          <Search className="pointer-events-none absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2 text-muted-foreground" aria-hidden />
          <Input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search employee, device…" className="h-8 pl-8 text-[13px]" aria-label="Search" />
        </div>
      </div>
      {query.data && rows.length > 0 && (
        <div className="flex flex-wrap gap-x-6 gap-y-1 border-b bg-subtle px-4 py-2 text-[12.5px] text-muted-foreground">
          <span>
            <b className="text-foreground tabular">{rows.length}</b> devices plugged in
          </span>
          <span>
            <b className="text-foreground tabular">{usbCount}</b> USB drives
          </span>
          <span>
            <b className="text-foreground tabular">{filesTo}</b> files copied to USB or phone
          </span>
          <span>
            <b className="text-foreground tabular">{filesFrom}</b> copied from USB or phone
          </span>
        </div>
      )}
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
          icon={Usb}
          title={rows.length ? 'Nothing matches these filters' : 'No devices plugged in'}
          description={
            tracking === false
              ? 'Device tracking is off. An administrator can switch it on in Settings → Workspace → Devices & automated input (needs WorkPulse 1.0.2 on the computers).'
              : 'USB drives, phones, mice and other devices plugged into employees’ computers appear here.'
          }
          size="sm"
        />
      ) : (
        <div className="max-h-[70vh] overflow-auto">
          <table className="w-full text-[13px]">
            <thead className="sticky top-0 z-10 bg-subtle text-left text-[11.5px] text-muted-foreground uppercase">
              <tr>
                {COLUMNS.map((c) => (
                  <th key={c.key} className="px-3 py-2 font-medium">
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
                <th className="px-3 py-2 font-medium">Connected for</th>
                <th className="px-3 py-2 font-medium">Files</th>
                {admin && <th className="px-3 py-2"><span className="sr-only">Actions</span></th>}
              </tr>
            </thead>
            <tbody className="divide-y">
              {shown.map((r) => {
                const info = KINDS[r.kind]
                const KindIcon = info.icon
                const minutes = connectedMinutes(r)
                const fileTotal = Object.values(r.file_counts).reduce((a, b) => a + b, 0)
                return (
                  <tr key={r.id} className="align-top">
                    <td className="px-3 py-2.5 whitespace-nowrap">
                      <p className="tabular">{formatDateTime(r.connected_at)}</p>
                      <p className="text-[11.5px] text-muted-foreground">
                        {r.disconnected_at ? `removed ${formatTime(r.disconnected_at)}` : 'still connected'}
                      </p>
                    </td>
                    <td className="px-3 py-2.5">
                      <p className="font-medium">{r.employee}</p>
                      <p className="text-[11.5px] text-muted-foreground">{[r.department, r.team].filter(Boolean).join(' · ') || '—'}</p>
                    </td>
                    <td className="px-3 py-2.5 whitespace-nowrap text-muted-foreground">{r.laptop}</td>
                    <td className="px-3 py-2.5">
                      <p className="flex items-start gap-2">
                        <KindIcon className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden />
                        <span>
                          <span className="font-medium">{r.title}</span>
                          <span className="mt-0.5 flex flex-wrap gap-1">
                            <Badge variant="outline">{info.label}</Badge>
                            {r.at_start && <Badge variant="warning">Found at start-up</Badge>}
                            {r.allowed && (
                              <Badge variant="success">
                                <ShieldCheck /> Allowed
                              </Badge>
                            )}
                          </span>
                        </span>
                      </p>
                    </td>
                    <td className="px-3 py-2.5 whitespace-nowrap tabular">{minutes == null ? '—' : minutesText(minutes)}</td>
                    <td className="px-3 py-2.5 whitespace-nowrap">
                      {r.kind !== 'storage' && r.kind !== 'phone' ? (
                        <span className="text-muted-foreground">—</span>
                      ) : fileTotal ? (
                        <Button variant="outline" size="sm" onClick={() => setOpen(r)}>
                          <FileStack /> {fileTotal} file{fileTotal === 1 ? '' : 's'}
                          {r.bytes_to_usb > 0 && <span className="text-muted-foreground">· {bytes(r.bytes_to_usb)}</span>}
                        </Button>
                      ) : (
                        <span className="text-muted-foreground">None</span>
                      )}
                    </td>
                    {admin && (
                      <td className="px-3 py-2.5 text-right">
                        {!r.allowed && (
                          <Button variant="ghost" size="sm" onClick={() => allow(r)} disabled={update.isPending} title="Keep logging it, but no alert">
                            Allow
                          </Button>
                        )}
                      </td>
                    )}
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
      <FilesDialog row={open} onClose={() => setOpen(null)} />
    </Card>
  )
}
