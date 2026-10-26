import { useMemo, useState } from 'react'
import { Link } from 'react-router'
import { Search } from 'lucide-react'

import { PersonAvatar } from '@/components/common/person'
import { StatusDot } from '@/components/common/status'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/misc'
import { SegmentedControl } from '@/components/ui/segmented-control'
import { formatClock, formatShort } from '@/features/dashboard/components/org/shared'
import { todayIn } from '@/features/activity/format'
import { api, toQuery } from '@/lib/api-client'
import { formatTime } from '@/lib/format'
import { useAuthStore } from '@/stores/auth-store'
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import type { PresenceOverview, RowUsage, TeamProductivity } from '@/types/api'

export type MembersFilter = 'all' | 'online' | 'offline'

interface Member {
  id: string
  name: string
  email: string
  online: boolean
  /** Online since (connected) or last active (offline). */
  marker: string | null
  productiveSeconds: number
  activeSeconds: number
  topUsage: RowUsage[]
}

const TITLE: Record<MembersFilter, string> = { all: 'All Members', online: 'Online Members', offline: 'Offline Members' }

export function MembersDialog({
  open,
  onOpenChange,
  initialFilter,
  teamId,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  initialFilter: MembersFilter
  teamId: string | null
}) {
  const [filter, setFilter] = useState<MembersFilter>(initialFilter)
  const [search, setSearch] = useState('')
  const company = useAuthStore((s) => s.company)
  const today = todayIn(company?.timezone ?? 'UTC')
  const scope = { team_id: teamId ?? undefined }

  const presence = useQuery({
    queryKey: ['members-dialog', 'presence', teamId],
    queryFn: () => api.get<PresenceOverview>(`/presence${toQuery(scope)}`),
    enabled: open,
    placeholderData: keepPreviousData,
    refetchInterval: open ? 30_000 : false,
  })
  const productivity = useQuery({
    queryKey: ['members-dialog', 'team', today, teamId],
    queryFn: () => api.get<TeamProductivity>(`/productivity/team${toQuery({ start: today, end: today, ...scope })}`),
    enabled: open,
    placeholderData: keepPreviousData,
  })

  const members: Member[] = useMemo(() => {
    const rows = productivity.data?.rows ?? []
    const byId = new Map(rows.map((r) => [r.employee.id, r]))
    return (presence.data?.employees ?? [])
      .filter((e) => e.device !== null) // only enrolled members have a device/signal
      .map((e) => {
        const row = byId.get(e.employee.id)
        return {
          id: e.employee.id,
          name: e.employee.full_name,
          email: e.employee.email,
          online: e.connected,
          marker: e.connected ? e.session_started_at ?? e.since : e.since,
          productiveSeconds: row?.metrics.productive_seconds ?? 0,
          activeSeconds: row?.metrics.active_seconds ?? 0,
          topUsage: row?.top_usage ?? [],
        }
      })
  }, [presence.data, productivity.data])

  const online = members.filter((m) => m.online).length
  const offline = members.length - online
  const scoped = filter === 'online' ? members.filter((m) => m.online) : filter === 'offline' ? members.filter((m) => !m.online) : members
  const q = search.trim().toLowerCase()
  const visible = q ? scoped.filter((m) => m.name.toLowerCase().includes(q) || m.email.toLowerCase().includes(q)) : scoped
  const loading = presence.isPending || productivity.isPending

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[85vh] gap-0 overflow-hidden p-0 sm:max-w-5xl">
        <DialogHeader className="space-y-1 px-6 pt-6">
          <DialogTitle>{TITLE[filter]}</DialogTitle>
          <DialogDescription>
            {visible.length} member{visible.length === 1 ? '' : 's'} · today's activity and productivity
          </DialogDescription>
        </DialogHeader>

        <div className="flex flex-col gap-3 px-6 py-4 sm:flex-row sm:items-center">
          <div className="relative flex-1">
            <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
            <Input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search by member name or email..."
              className="pl-9"
            />
          </div>
          <SegmentedControl<MembersFilter>
            label="Filter members"
            value={filter}
            onChange={setFilter}
            options={[
              { value: 'all', label: `All ${members.length}` },
              { value: 'online', label: `Online ${online}` },
              { value: 'offline', label: `Offline ${offline}` },
            ]}
          />
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto border-t">
          {loading ? (
            <div className="space-y-2 p-6">
              {[0, 1, 2, 3].map((i) => (
                <Skeleton key={i} className="h-16" />
              ))}
            </div>
          ) : !visible.length ? (
            <p className="p-10 text-center text-[13px] text-muted-foreground">No members match.</p>
          ) : (
            <table className="w-full border-collapse text-[13px]">
              <thead className="sticky top-0 bg-popover">
                <tr className="border-b text-left text-[11px] font-medium tracking-wide text-muted-foreground uppercase">
                  <th className="px-6 py-2.5 font-medium">Member</th>
                  <th className="px-3 py-2.5 font-medium">{filter === 'offline' ? 'Last active' : 'Online since / last active'}</th>
                  <th className="px-3 py-2.5 font-medium">Productive time</th>
                  <th className="px-3 py-2.5 font-medium">Top apps today</th>
                  <th className="px-6 py-2.5 font-medium">Active time today</th>
                </tr>
              </thead>
              <tbody>
                {visible.map((m) => (
                  <tr key={m.id} className="border-b align-top last:border-0 hover:bg-muted/40">
                    <td className="px-6 py-4">
                      <Link to={`/people/employees/${m.id}`} className="flex items-center gap-3" onClick={() => onOpenChange(false)}>
                        <PersonAvatar name={m.name} seed={m.id} className="size-9" aria-hidden />
                        <span className="min-w-0">
                          <span className="flex items-center gap-1.5 font-medium">
                            <StatusDot tone={m.online ? 'success' : 'neutral'} />
                            <span className="truncate">{m.name}</span>
                          </span>
                          <span className="block truncate text-[12px] text-muted-foreground">{m.email}</span>
                        </span>
                      </Link>
                    </td>
                    <td className="px-3 py-4">
                      <p className="font-semibold tabular">{m.marker ? formatTime(m.marker) : '—'}</p>
                      <p className="text-[11px] text-muted-foreground">{m.online ? 'Online since' : 'Last active'}</p>
                    </td>
                    <td className="px-3 py-4">
                      <p className="font-semibold tabular">{formatClock(m.productiveSeconds)}</p>
                      <p className="text-[11px] text-muted-foreground">Productive time today</p>
                    </td>
                    <td className="px-3 py-4">
                      {m.topUsage.length ? (
                        <div className="space-y-1">
                          {m.topUsage.map((u) => (
                            <div key={`${u.kind}:${u.name}`} className="flex items-center justify-between gap-4">
                              <span className="truncate text-[12px]">{u.name}</span>
                              <span className="shrink-0 text-[12px] font-medium tabular text-primary">{formatShort(u.seconds)}</span>
                            </div>
                          ))}
                        </div>
                      ) : (
                        <span className="text-[12px] text-muted-foreground">—</span>
                      )}
                    </td>
                    <td className="px-6 py-4">
                      <p className="font-semibold tabular">{formatClock(m.activeSeconds)}</p>
                      <p className="text-[11px] text-muted-foreground">Active time today</p>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
        <p className="border-t px-6 py-2.5 text-[11px] text-muted-foreground">
          Times shown are for today and update with the member's monitoring and productivity activity.
        </p>
      </DialogContent>
    </Dialog>
  )
}
