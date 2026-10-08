import { ListChecks } from 'lucide-react'

import { EmptyState } from '@/components/common/empty-state'
import { Card } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/misc'
import { useTasks } from '@/features/work/api'
import { TaskDrawer } from '@/features/work/components/task-drawer'
import { TaskList } from '@/features/work/components/task-list'
import { useTaskParam } from '@/features/work/pages/project-page'

/** Profile tab: tasks assigned to this person, in projects the viewer can see. */
export function EmployeeTasksPanel({ employeeId, firstName }: { employeeId: string; firstName: string }) {
  const tasks = useTasks({ assignee: employeeId })
  const [openTask, setOpenTask] = useTaskParam()
  return (
    <>
      {!tasks.data ? (
        <Skeleton className="h-48" />
      ) : tasks.data.length === 0 ? (
        <Card>
          <EmptyState icon={ListChecks} title="No tasks" description={`${firstName} has no tasks in projects you can see.`} />
        </Card>
      ) : (
        <Card className="overflow-hidden py-0">
          <TaskList tasks={tasks.data} onOpen={setOpenTask} showProject />
        </Card>
      )}
      <TaskDrawer taskId={openTask} onClose={() => setOpenTask(null)} />
    </>
  )
}
