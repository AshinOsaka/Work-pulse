import { StatusDot } from '@/components/common/status'
import { Badge } from '@/components/ui/badge'
import { ACCESS_STATE, EMPLOYEE_STATUS } from '@/features/people/meta'
import type { AccessState, EmployeeStatus } from '@/types/api'

export function EmployeeStatusBadge({ status }: { status: EmployeeStatus }) {
  const meta = EMPLOYEE_STATUS[status]
  return (
    <span className="inline-flex items-center gap-1.5 text-[13px] whitespace-nowrap">
      <StatusDot tone={meta.tone} />
      {meta.label}
    </span>
  )
}

const ACCESS_VARIANT: Record<AccessState, 'outline' | 'soft' | 'success' | 'warning' | 'secondary'> = {
  none: 'outline',
  invited: 'warning',
  active: 'success',
  suspended: 'warning',
  deactivated: 'secondary',
}

export function AccessBadge({ access }: { access: AccessState }) {
  return (
    <Badge variant={ACCESS_VARIANT[access]} title={ACCESS_STATE[access].description}>
      {ACCESS_STATE[access].label}
    </Badge>
  )
}
