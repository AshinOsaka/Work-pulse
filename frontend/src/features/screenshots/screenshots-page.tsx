import { useState } from 'react'
import { Camera, Settings2, ShieldCheck } from 'lucide-react'
import { Link } from 'react-router'

import { FilterSelect, toOptions } from '@/components/common/filter-select'
import { PageHeader } from '@/components/common/page-header'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { RequirePermission } from '@/features/auth/guards'
import { useTeams } from '@/features/people/api'
import { EmployeePicker } from '@/features/people/components/employee-picker'
import { useScreenshotPolicy } from '@/features/screenshots/api'
import { ScreenshotGallery } from '@/features/screenshots/components/screenshot-gallery'
import { scheduleSummary } from '@/features/screenshots/format'
import { useDocumentTitle } from '@/hooks/use-document-title'
import { usePermissions } from '@/stores/auth-store'

function PolicyLine() {
  const policy = useScreenshotPolicy().data
  const { can } = usePermissions()
  if (!policy) return null
  return (
    <div className="flex flex-wrap items-center gap-2 text-[12px] text-muted-foreground">
      <Badge variant={policy.enabled ? 'destructive' : 'secondary'}>{scheduleSummary(policy)}</Badge>
      <span className="inline-flex items-center gap-1">
        <ShieldCheck className="size-3.5 text-success" aria-hidden /> Private, encrypted, audited · kept{' '}
        {policy.retention_days} days
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

function Gallery() {
  const [teamId, setTeamId] = useState<string | null>(null)
  const [employeeId, setEmployeeId] = useState<string | null>(null)
  const teams = useTeams()
  const policy = useScreenshotPolicy().data
  return (
    <ScreenshotGallery
      employeeId={employeeId ?? undefined}
      teamId={teamId ?? undefined}
      emptyDescription={
        policy && !policy.enabled
          ? 'Screenshot capture is turned off for this workspace. Administrators can enable it in Settings → Workspace.'
          : 'Nothing was captured for the selected people on this day. Screenshots are taken only during active work sessions.'
      }
      filters={
        <>
          <FilterSelect label="Team" value={teamId} onChange={setTeamId} options={toOptions(teams.data)} allLabel="All teams" />
          <div className="w-56">
            <EmployeePicker value={employeeId} onChange={setEmployeeId} placeholder="All people" />
          </div>
          <div className="ml-auto">
            <PolicyLine />
          </div>
        </>
      }
    />
  )
}

export default function ScreenshotsPage() {
  useDocumentTitle('Screenshots')
  return (
    <div className="space-y-6">
      <PageHeader
        title="Screenshots"
        description="Screenshots captured by the desktop agent during work sessions, for the people you manage."
        icon={Camera}
      />
      <RequirePermission permission="SCREENSHOT_VIEW">
        <Gallery />
      </RequirePermission>
    </div>
  )
}
