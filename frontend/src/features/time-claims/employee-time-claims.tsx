import { useState } from 'react'
import { Handshake, Plus } from 'lucide-react'

import { EmptyState } from '@/components/common/empty-state'
import { Button } from '@/components/ui/button'
import { Card, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/misc'
import { useTimeClaims } from '@/features/time-claims/api'
import { LogTimeDialog } from '@/features/time-claims/log-time-dialog'
import { ClaimRow } from '@/features/time-claims/time-claims-page'
import { usePermissions, useAuthStore } from '@/stores/auth-store'

/** One person's time claims on their profile; their managers can add meeting time for them here. */
export function EmployeeTimeClaims({ employeeId, name }: { employeeId: string; name: string }) {
  const { can } = usePermissions()
  const timeZone = useAuthStore((s) => s.company?.timezone ?? 'UTC')
  const list = useTimeClaims({ employee_id: employeeId, page_size: 50 })
  const [adding, setAdding] = useState(false)
  const items = list.data?.items ?? []
  return (
    <Card className="overflow-hidden">
      <CardHeader className="flex flex-row items-start justify-between gap-4 pb-4">
        <div className="space-y-1.5">
          <CardTitle>Time claims</CardTitle>
          <CardDescription>Meetings, visits and calls away from the computer, counted in attendance.</CardDescription>
        </div>
        {can('TIME_CLAIM_MANAGE') && (
          <Button size="sm" onClick={() => setAdding(true)}>
            <Plus /> Add for {name.split(' ')[0]}
          </Button>
        )}
      </CardHeader>
      {list.isPending ? (
        <div className="space-y-2 p-4">
          {[0, 1].map((i) => (
            <Skeleton key={i} className="h-14" />
          ))}
        </div>
      ) : items.length === 0 ? (
        <EmptyState size="sm" icon={Handshake} title="No time claims" description="Nothing logged away from the computer yet." />
      ) : (
        <ul className="divide-y border-t">
          {items.map((c) => (
            <ClaimRow key={c.id} claim={c} showPerson={false} timeZone={timeZone} />
          ))}
        </ul>
      )}
      {adding && <LogTimeDialog mode={{ kind: 'team', preselected: [employeeId] }} onOpenChange={setAdding} />}
    </Card>
  )
}
