import { useMemo, useState } from 'react'
import { BarChart3, Camera, ChevronLeft, Download, Images, Plus, Settings2, ShieldCheck } from 'lucide-react'
import { Link } from 'react-router'

import { EmptyState } from '@/components/common/empty-state'
import { FilterSelect, toOptions } from '@/components/common/filter-select'
import { PageHeader } from '@/components/common/page-header'
import { PersonAvatar } from '@/components/common/person'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { RequirePermission } from '@/features/auth/guards'
import { todayIn } from '@/features/activity/format'
import { useTeams } from '@/features/people/api'
import { EmployeeProductivityView } from '@/features/productivity/components/employee-view'
import { useScreenshotMembers, useScreenshotPolicy, useScreenshotRequests } from '@/features/screenshots/api'
import { DownloadRequestsDialog } from '@/features/screenshots/components/download-requests-dialog'
import { RaiseRequestDialog } from '@/features/screenshots/components/raise-request-dialog'
import { ScreenshotMemberGrid } from '@/features/screenshots/components/screenshot-members'
import { ScreenshotViewerDialog } from '@/features/screenshots/components/screenshot-viewer-dialog'
import { scheduleSummary } from '@/features/screenshots/format'
import { useDocumentTitle } from '@/hooks/use-document-title'
import { cn } from '@/lib/utils'
import { useAuthStore, usePermissions } from '@/stores/auth-store'

type Tab = 'gallery' | 'productivity'

function PolicyLine() {
  const policy = useScreenshotPolicy().data
  const { can } = usePermissions()
  if (!policy) return null
  return (
    <div className="flex flex-wrap items-center gap-2 text-[12px] text-muted-foreground">
      <Badge variant={policy.enabled ? 'destructive' : 'secondary'}>{scheduleSummary(policy)}</Badge>
      <span className="inline-flex items-center gap-1">
        <ShieldCheck className="size-3.5 text-success" aria-hidden /> Private, encrypted, audited · kept {policy.retention_days} days
      </span>
      {can('POLICY_MANAGE') && (
        <Button asChild variant="link" size="sm" className="h-auto px-1 text-[12px]">
          <Link to="/settings/workspace">
            <Settings2 /> Policy
          </Link>
        </Button>
      )}
    </div>
  )
}

function Workspace() {
  const timeZone = useAuthStore((s) => s.company?.timezone ?? 'UTC')
  const today = todayIn(timeZone)
  const teams = useTeams()

  const [tab, setTab] = useState<Tab>('gallery')
  const [teamId, setTeamId] = useState<string | null>(null)
  const [search, setSearch] = useState('')
  const [day, setDay] = useState(today)
  const [selected, setSelected] = useState<string | null>(null) // productivity tab: inline view
  const [viewer, setViewer] = useState<{ id: string; name: string } | null>(null) // gallery tab: modal
  const [raising, setRaising] = useState(false)
  const [showRequests, setShowRequests] = useState(false)

  const members = useScreenshotMembers(teamId ?? undefined)
  const requests = useScreenshotRequests()
  const activeRequests = (requests.data ?? []).filter((r) =>
    ['queued', 'preparing', 'packaging'].includes(r.status),
  ).length

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase()
    const list = members.data ?? []
    if (!q) return list
    return list.filter(
      (m) => m.employee.full_name.toLowerCase().includes(q) || m.employee.email.toLowerCase().includes(q),
    )
  }, [members.data, search])

  const selectedMember = (members.data ?? []).find((m) => m.employee.id === selected) ?? null
  const onSelectMember = (id: string) => {
    const m = (members.data ?? []).find((x) => x.employee.id === id)
    if (!m) return
    if (tab === 'gallery') setViewer({ id, name: m.employee.full_name })
    else setSelected(id)
  }

  return (
    <div className="space-y-5">
      {/* Tabs + Download Requests */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="inline-flex rounded-lg border bg-subtle p-1">
          {(
            [
              { key: 'gallery', label: 'Gallery', icon: Images },
              { key: 'productivity', label: 'Productivity', icon: BarChart3 },
            ] as const
          ).map(({ key, label, icon: Icon }) => (
            <button
              key={key}
              type="button"
              aria-pressed={tab === key}
              onClick={() => setTab(key)}
              className={cn(
                'inline-flex items-center gap-2 rounded-md px-4 py-1.5 text-[13px] font-medium transition',
                tab === key ? 'bg-card text-foreground shadow-xs' : 'text-muted-foreground hover:text-foreground',
              )}
            >
              <Icon className="size-4" aria-hidden /> {label}
            </button>
          ))}
        </div>
        <Button variant="outline" onClick={() => setShowRequests(true)}>
          <Download /> Download Requests
          {activeRequests > 0 && <Badge variant="secondary">{activeRequests}</Badge>}
        </Button>
      </div>

      {/* Filter row */}
      <div className="flex flex-wrap items-center gap-3 rounded-xl border bg-card p-3 shadow-xs">
        <FilterSelect
          label="Members"
          value={teamId}
          onChange={setTeamId}
          options={toOptions(teams.data)}
          allLabel="All Members"
        />
        <div className="min-w-48 flex-1">
          <Input
            type="search"
            placeholder="Search by name or email…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        <Input
          type="date"
          value={day}
          max={today}
          onChange={(e) => e.target.value && setDay(e.target.value)}
          className="w-44"
          aria-label="Date"
        />
        <Button onClick={() => setRaising(true)}>
          <Plus /> Raise Request
        </Button>
      </div>

      {/* Member grid */}
      <ScreenshotMemberGrid
        members={filtered}
        loading={!members.data}
        selectedId={tab === 'gallery' ? (viewer?.id ?? null) : selected}
        onSelect={onSelectMember}
      />

      {/* Gallery tab clicks open the hour-by-hour viewer modal; Productivity shows an inline report. */}
      {tab === 'productivity' && selectedMember ? (
        <div className="space-y-4 border-t pt-5">
          <div className="flex flex-wrap items-center gap-3">
            <Button variant="ghost" size="sm" onClick={() => setSelected(null)}>
              <ChevronLeft /> Back
            </Button>
            <PersonAvatar name={selectedMember.employee.full_name} aria-hidden />
            <div className="min-w-0">
              <p className="text-[14px] font-semibold">{selectedMember.employee.full_name}</p>
              <p className="text-[12px] text-muted-foreground">{selectedMember.employee.email}</p>
            </div>
            <div className="ml-auto">
              <PolicyLine />
            </div>
          </div>
          <EmployeeProductivityView key={selectedMember.employee.id} employeeId={selectedMember.employee.id} />
        </div>
      ) : (
        <EmptyState
          size="sm"
          icon={tab === 'gallery' ? Camera : BarChart3}
          title={
            tab === 'gallery'
              ? 'Click a person to view their screenshots'
              : 'Select a person to see their productivity'
          }
          description="Choose a member above, or use Raise Request to download a day's screenshots as a ZIP."
        />
      )}

      {viewer && (
        <ScreenshotViewerDialog
          open={Boolean(viewer)}
          onOpenChange={(o) => !o && setViewer(null)}
          employeeId={viewer.id}
          employeeName={viewer.name}
          day={day}
          timeZone={timeZone}
        />
      )}
      <RaiseRequestDialog
        open={raising}
        onOpenChange={setRaising}
        defaultEmployeeId={viewer?.id ?? selected}
        defaultDay={day}
        today={today}
      />
      <DownloadRequestsDialog open={showRequests} onOpenChange={setShowRequests} />
    </div>
  )
}

export default function ScreenshotsPage() {
  useDocumentTitle('Screenshots')
  return (
    <div className="space-y-6">
      <PageHeader
        title="Screenshots"
        description="View screenshots by date, and download a day's captures."
        icon={Camera}
      />
      <RequirePermission permission="SCREENSHOT_VIEW">
        <Workspace />
      </RequirePermission>
    </div>
  )
}
