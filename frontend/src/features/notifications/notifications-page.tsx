import { useState } from 'react'
import { Bell, BellOff, CheckCheck, Mail, MonitorSmartphone, Settings2 } from 'lucide-react'
import { useSearchParams } from 'react-router'
import { toast } from 'sonner'

import { EmptyState } from '@/components/common/empty-state'
import { FilterSelect } from '@/components/common/filter-select'
import { PageHeader } from '@/components/common/page-header'
import { Button } from '@/components/ui/button'
import { Card, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Switch } from '@/components/ui/form-controls'
import { Skeleton } from '@/components/ui/misc'
import { SegmentedControl } from '@/components/ui/segmented-control'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { WidgetError } from '@/features/dashboard/components/widget'
import { useMarkNotifications, useNotifications, usePreferences, useUpdatePreferences, type NotificationQuery } from '@/features/notifications/api'
import { SEVERITY, TYPE, TYPES } from '@/features/notifications/meta'
import { NotificationItem } from '@/features/notifications/notification-item'
import { useEmployeeOptions } from '@/features/people/api'
import { useDocumentTitle } from '@/hooks/use-document-title'
import { errorMessage } from '@/lib/api-client'
import { cn } from '@/lib/utils'
import { usePermissions } from '@/stores/auth-store'
import type { NotificationChannels, NotificationSeverity, NotificationType } from '@/types/api'

const PAGE_SIZE = 25
type ReadFilter = 'all' | 'unread' | 'read'
type Since = 'any' | '24h' | '7d' | '30d'
const SINCE_MS: Record<Since, number | null> = { any: null, '24h': 86_400_000, '7d': 7 * 86_400_000, '30d': 30 * 86_400_000 }

function Inbox() {
  const { can } = usePermissions()
  const people = useEmployeeOptions(can('ACTIVITY_VIEW'))
  const [read, setRead] = useState<ReadFilter>('all')
  const [type, setType] = useState<NotificationType | null>(null)
  const [severity, setSeverity] = useState<NotificationSeverity | null>(null)
  const [employee, setEmployee] = useState<string | null>(null)
  // The cut-off is fixed when chosen (in the handler), so the query key stays stable while the page is open.
  const [since, setSince] = useState<{ key: Since; iso?: string }>({ key: 'any' })
  const [page, setPage] = useState(1)
  const query: NotificationQuery = {
    read: read === 'all' ? undefined : read === 'read',
    type: type ?? undefined,
    severity: severity ?? undefined,
    employee_id: employee ?? undefined,
    since: since.iso,
    page,
    page_size: PAGE_SIZE,
  }
  const list = useNotifications(query)
  const mark = useMarkNotifications()
  const data = list.data
  const pages = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1
  const filtered = read !== 'all' || type || severity || employee || since.key !== 'any'
  const reset = (fn: () => void) => {
    fn()
    setPage(1)
  }

  return (
    <Card className="overflow-hidden">
      <div className="flex flex-wrap items-center gap-3 border-b px-4 py-3">
        <SegmentedControl<ReadFilter>
          label="Show"
          size="sm"
          value={read}
          onChange={(v) => reset(() => setRead(v))}
          options={[
            { value: 'all', label: 'All' },
            { value: 'unread', label: `Unread${data ? ` ${data.unread}` : ''}` },
            { value: 'read', label: 'Read' },
          ]}
        />
        <FilterSelect
          label="Type"
          value={type}
          onChange={(v) => reset(() => setType(v as NotificationType | null))}
          options={TYPES.map((t) => ({ value: t, label: TYPE[t].label }))}
          allLabel="All types"
        />
        <FilterSelect
          label="Severity"
          value={severity}
          onChange={(v) => reset(() => setSeverity(v as NotificationSeverity | null))}
          options={(Object.keys(SEVERITY) as NotificationSeverity[]).map((s) => ({ value: s, label: SEVERITY[s].label }))}
          allLabel="Any severity"
        />
        {(people.data?.length ?? 0) > 0 && (
          <FilterSelect
            label="Employee"
            value={employee}
            onChange={(v) => reset(() => setEmployee(v))}
            options={(people.data ?? []).map((p) => ({ value: p.id, label: p.full_name }))}
            allLabel="Anyone"
          />
        )}
        <Select
          value={since.key}
          onValueChange={(v) =>
            reset(() => {
              const ms = SINCE_MS[v as Since]
              setSince({ key: v as Since, iso: ms ? new Date(Date.now() - ms).toISOString() : undefined })
            })
          }
        >
          <SelectTrigger size="sm" className="w-full sm:w-44" aria-label="Time">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="any">Any time</SelectItem>
            <SelectItem value="24h">Last 24 hours</SelectItem>
            <SelectItem value="7d">Last 7 days</SelectItem>
            <SelectItem value="30d">Last 30 days</SelectItem>
          </SelectContent>
        </Select>
        <Button
          size="sm"
          variant="outline"
          className="ml-auto"
          disabled={!data?.unread}
          loading={mark.isPending}
          onClick={() => mark.mutate({ all: true, type: type ?? undefined, read: true }, { onError: (e) => toast.error(errorMessage(e)) })}
        >
          <CheckCheck /> Mark {type ? `${TYPE[type].label.toLowerCase()}` : 'all'} read
        </Button>
      </div>
      {list.isError ? (
        <WidgetError error={list.error} onRetry={() => void list.refetch()} />
      ) : !data ? (
        <div className="space-y-2 p-4">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-16" />
          ))}
        </div>
      ) : data.items.length === 0 ? (
        <EmptyState
          icon={filtered ? Bell : BellOff}
          title={filtered ? 'Nothing matches these filters' : "You're all caught up"}
          description={filtered ? 'Try another type, severity, person or time range.' : 'Alerts you receive appear here as they happen. Choose which in Preferences.'}
        />
      ) : (
        <>
          <ul className={cn('divide-y', list.isFetching && 'opacity-80')}>
            {data.items.map((n) => (
              <NotificationItem key={n.id} n={n} onRead={(r) => mark.mutate({ ids: [n.id], read: r })} />
            ))}
          </ul>
          <div className="flex items-center justify-between border-t px-4 py-2.5 text-[12px] text-muted-foreground">
            <span>
              {data.total.toLocaleString()} notification{data.total === 1 ? '' : 's'} · kept for 90 days
            </span>
            <span className="flex items-center gap-2">
              <Button size="sm" variant="ghost" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
                Previous
              </Button>
              <span className="tabular">
                {page} / {pages}
              </span>
              <Button size="sm" variant="ghost" disabled={page >= pages} onClick={() => setPage((p) => p + 1)}>
                Next
              </Button>
            </span>
          </div>
        </>
      )}
    </Card>
  )
}

const THROTTLE = [5, 15, 30, 60, 120, 240, 720, 1440]
const minutes = (m: number) => (m < 60 ? `${m} minutes` : m === 60 ? '1 hour' : m < 1440 ? `${m / 60} hours` : '1 day')


function Preferences() {
  const prefs = usePreferences()
  const update = useUpdatePreferences()
  const save = (input: Parameters<typeof update.mutate>[0]) =>
    update.mutate(input, { onError: (e) => toast.error(`Not saved: ${errorMessage(e)}`) })
  if (prefs.isError) return <WidgetError error={prefs.error} onRetry={() => void prefs.refetch()} />
  const data = prefs.data
  if (!data) return <Skeleton className="h-96" />
  const set = (type: NotificationType, channels: NotificationChannels) => save({ types: { [type]: channels } })

  return (
    <div className="space-y-5">
      <Card>
        <CardHeader>
          <CardTitle>Not too much, not too often</CardTitle>
          <CardDescription>
            Repeats about the same person or item within your throttle window are combined into one notification (shown as ×2, ×3…) and never e-mailed
            twice. If many alerts arrive at once, they are still listed here but stop popping up and e-mailing.
          </CardDescription>
        </CardHeader>
        <div className="flex flex-wrap items-center gap-3 px-5 pt-3 pb-5">
          <label htmlFor="throttle" className="text-[13px] font-medium">
            Throttle window
          </label>
          <Select value={String(data.throttle_minutes)} onValueChange={(v) => save({ throttle_minutes: Number(v) })}>
            <SelectTrigger id="throttle" size="sm" className="w-40">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {THROTTLE.map((m) => (
                <SelectItem key={m} value={String(m)}>
                  {minutes(m)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <span className="text-[12px] text-muted-foreground">E-mails go to {data.email_address}.</span>
        </div>
      </Card>

      <Card className="overflow-hidden">
        <CardHeader>
          <CardTitle>Alerts</CardTitle>
          <CardDescription>Choose how you hear about each kind of alert. E-mail is off until you turn it on.</CardDescription>
        </CardHeader>
        <div className="relative mt-3 overflow-x-auto border-t">
          <Table>
            <caption className="sr-only">Notification preferences per alert type</caption>
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                <TableHead scope="col" className="px-5">
                  Alert
                </TableHead>
                <TableHead scope="col" className="w-24 text-center">
                  <span className="inline-flex items-center gap-1">
                    <MonitorSmartphone className="size-3.5" aria-hidden /> In-app
                  </span>
                </TableHead>
                <TableHead scope="col" className="w-24 pr-5 text-center">
                  <span className="inline-flex items-center gap-1">
                    <Mail className="size-3.5" aria-hidden /> E-mail
                  </span>
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.types.map((t) => {
                const kind = TYPE[t.type]
                const severity = SEVERITY[t.severity]
                return (
                  <TableRow key={t.type} className={cn(!t.applies && 'text-muted-foreground')}>
                    <TableCell className="px-5 py-3">
                      <p className="flex items-center gap-2 font-medium">
                        <kind.icon className="size-4 text-muted-foreground" aria-hidden /> {t.label}
                        <span className={cn('inline-flex items-center gap-1 text-[11px] font-normal', severity.text)}>
                          <severity.icon className="size-3" aria-hidden /> {severity.label}
                        </span>
                      </p>
                      <p className="mt-0.5 text-[12px] text-muted-foreground">{t.description}</p>
                      <p className="text-[11px] text-muted-foreground">{t.applies ? `Sent to: ${t.audience}` : 'Not available for your role'}</p>
                    </TableCell>
                    <TableCell className="py-3 text-center">
                      <Switch checked={t.applies && t.channels.in_app} disabled={!t.applies} onCheckedChange={(v) => set(t.type, { ...t.channels, in_app: v })} aria-label={`${t.label}: in-app`} />
                    </TableCell>
                    <TableCell className="py-3 pr-5 text-center">
                      <Switch checked={t.applies && t.channels.email} disabled={!t.applies} onCheckedChange={(v) => set(t.type, { ...t.channels, email: v })} aria-label={`${t.label}: e-mail`} />
                    </TableCell>
                  </TableRow>
                )
              })}
            </TableBody>
          </Table>
        </div>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Channels</CardTitle>
          <CardDescription>More delivery channels can be added later without changing your alert choices.</CardDescription>
        </CardHeader>
        <ul className="flex flex-wrap gap-2 px-5 pt-3 pb-5">
          {data.channels.map((c) => (
            <li key={c.key} className={cn('rounded-full border px-3 py-1 text-[12px]', c.available ? 'border-primary/40 text-foreground' : 'text-muted-foreground')}>
              {c.label} {c.available ? '· available' : '· coming later'}
            </li>
          ))}
        </ul>
      </Card>
    </div>
  )
}

export default function NotificationsPage() {
  useDocumentTitle('Alerts')
  const [params, setParams] = useSearchParams()
  const tab = params.get('tab') === 'preferences' ? 'preferences' : 'inbox'
  return (
    <div className="space-y-6">
      <PageHeader title="Alerts" description="Offline devices, long idle, overdue work, deadlines, live views and policy changes — as they happen." icon={Bell} />
      <Tabs value={tab} onValueChange={(v) => setParams(v === 'preferences' ? { tab: 'preferences' } : {}, { replace: true })}>
        <TabsList>
          <TabsTrigger value="inbox">
            <Bell /> Notifications
          </TabsTrigger>
          <TabsTrigger value="preferences">
            <Settings2 /> Preferences
          </TabsTrigger>
        </TabsList>
        <TabsContent value="inbox">
          <Inbox />
        </TabsContent>
        <TabsContent value="preferences">
          <Preferences />
        </TabsContent>
      </Tabs>
    </div>
  )
}
