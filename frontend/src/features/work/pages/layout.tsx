import { FolderKanban, LayoutGrid, ListTodo, UsersRound } from 'lucide-react'
import { Outlet } from 'react-router'

import { LinkTabs } from '@/components/common/link-tabs'
import { PageHeader } from '@/components/common/page-header'
import { useAuthStore, usePermissions } from '@/stores/auth-store'

export default function WorkLayout() {
  const { can } = usePermissions()
  const hasEmployee = useAuthStore((s) => Boolean(s.user?.employee_id))
  const tabs = [
    ...(hasEmployee ? [{ to: '/projects/my-work', label: 'My work', icon: ListTodo }] : []),
    { to: '/projects', label: 'Projects', icon: LayoutGrid, end: true },
    ...(can('TASK_MANAGE') || can('PROJECT_MANAGE') ? [{ to: '/projects/team', label: 'Team', icon: UsersRound }] : []),
  ]
  return (
    <div className="space-y-6">
      <PageHeader title="Projects & Tasks" description="Plan the work, track it on boards, and see where the time goes." icon={FolderKanban} />
      <LinkTabs tabs={tabs} />
      <Outlet />
    </div>
  )
}
