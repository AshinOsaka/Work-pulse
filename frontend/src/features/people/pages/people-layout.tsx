import { Building2, LayoutGrid, Users, UsersRound } from 'lucide-react'
import { Outlet } from 'react-router'

import { LinkTabs } from '@/components/common/link-tabs'
import { PageHeader } from '@/components/common/page-header'
import { RequirePermission } from '@/features/auth/guards'

const TABS = [
  { to: '/people', label: 'Overview', icon: LayoutGrid, end: true },
  { to: '/people/employees', label: 'Employees', icon: Users },
  { to: '/people/departments', label: 'Departments', icon: Building2 },
  { to: '/people/teams', label: 'Teams', icon: UsersRound },
]

export default function PeopleLayout() {
  return (
    <RequirePermission permission="EMPLOYEE_VIEW">
      <div className="space-y-6">
        <PageHeader
          title="People"
          description="Your organisation's employees, departments and teams."
          icon={Users}
        />
        <LinkTabs tabs={TABS} />
        <Outlet />
      </div>
    </RequirePermission>
  )
}
