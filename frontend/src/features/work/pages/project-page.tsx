import { useMemo, useState } from 'react'
import { ArrowLeft, CalendarRange, Columns3, Flag, List, Pencil, Search, Users } from 'lucide-react'
import { Link, useParams, useSearchParams } from 'react-router'

import { EmptyState } from '@/components/common/empty-state'
import { FilterSelect } from '@/components/common/filter-select'
import { AvatarGroup } from '@/components/common/person'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Progress, Skeleton } from '@/components/ui/misc'
import { SegmentedControl } from '@/components/ui/segmented-control'
import { formatSeconds } from '@/features/activity/format'
import { WidgetError } from '@/features/dashboard/components/widget'
import { useLabels, useMilestones, useProject, useTasks } from '@/features/work/api'
import { TaskBoard } from '@/features/work/components/board'
import { MilestoneBoard } from '@/features/work/components/milestone-board'
import { ProjectDialog } from '@/features/work/components/project-dialog'
import { TaskDrawer } from '@/features/work/components/task-drawer'
import { TaskList } from '@/features/work/components/task-list'
import { Timeline } from '@/features/work/components/timeline'
import { formatDue, PRIORITIES, PRIORITY, PROJECT_COLOR, STATUS, STATUSES } from '@/features/work/meta'
import { useDocumentTitle } from '@/hooks/use-document-title'
import { ApiError } from '@/lib/api-client'
import { cn } from '@/lib/utils'
import type { TaskPriority } from '@/types/api'

const ANY = '__any__'
type View = 'board' | 'list' | 'timeline' | 'milestones'
const VIEWS: View[] = ['board', 'list', 'timeline', 'milestones']

/** Open task in a side panel, kept in the URL (`?task=`) so it can be linked and survives reloads. */
export function useTaskParam(): [string | null, (id: string | null) => void] {
  const [params, setParams] = useSearchParams()
  const set = (id: string | null) =>
    setParams(
      (current) => {
        const next = new URLSearchParams(current)
        if (id) next.set('task', id)
        else next.delete('task')
        return next
      },
      { replace: false },
    )
  return [params.get('task'), set]
}

export default function ProjectPage() {
  const { projectId = '' } = useParams()
  const project = useProject(projectId)
  const tasks = useTasks({ project_id: projectId })
  const milestones = useMilestones(projectId)
  const labels = useLabels(projectId)
  const [openTask, setOpenTask] = useTaskParam()
  const [view, setView] = useState<View>(() => {
    try {
      const saved = localStorage.getItem('wp.taskView') as View | null
      return saved && VIEWS.includes(saved) ? saved : 'board'
    } catch {
      return 'board'
    }
  })
  const [label, setLabel] = useState(ANY)
  const [milestone, setMilestone] = useState(ANY)
  const [search, setSearch] = useState('')
  const [assignee, setAssignee] = useState(ANY)
  const [priority, setPriority] = useState(ANY)
  const [editing, setEditing] = useState(false)
  useDocumentTitle(project.data?.name ?? 'Project')

  const visible = useMemo(() => {
    const term = search.trim().toLowerCase()
    return (tasks.data ?? []).filter(
      (t) =>
        (!term || t.title.toLowerCase().includes(term) || t.reference.toLowerCase().includes(term)) &&
        (assignee === ANY || (assignee === 'none' ? t.assignees.length === 0 : t.assignees.some((a) => a.id === assignee))) &&
        (priority === ANY || t.priority === priority) &&
        (label === ANY || t.labels.includes(label)) &&
        (milestone === ANY || (milestone === 'none' ? !t.milestone_id : t.milestone_id === milestone)),
    )
  }, [tasks.data, search, assignee, priority, label, milestone])

  const changeView = (v: View) => {
    setView(v)
    try {
      localStorage.setItem('wp.taskView', v)
    } catch {
      /* storage unavailable: the choice just isn't remembered */
    }
  }

  if (project.isError && !(project.error instanceof ApiError && project.error.status === 404)) {
    return (
      <Card>
        <WidgetError error={project.error} onRetry={() => void project.refetch()} />
      </Card>
    )
  }
  if (project.isError) {
    return (
      <Card>
        <EmptyState icon={Columns3} title="Project not found" description="It doesn't exist or you're not a member." action={<Button asChild size="sm" variant="outline"><Link to="/projects">All projects</Link></Button>} />
      </Card>
    )
  }
  const p = project.data
  return (
    <div className="space-y-5">
      <Link to="/projects" className="inline-flex items-center gap-1.5 text-[13px] text-muted-foreground hover:text-foreground">
        <ArrowLeft className="size-3.5" /> All projects
      </Link>
      {!p ? (
        <Skeleton className="h-24" />
      ) : (
        <Card className="relative overflow-hidden p-5">
          <span className={cn('absolute inset-y-0 left-0 w-1', PROJECT_COLOR[p.color])} aria-hidden />
          <div className="flex flex-wrap items-start gap-4">
            <div className="min-w-0 flex-1">
              <p className="text-[11px] font-semibold tracking-wider text-muted-foreground">{p.key}</p>
              <h2 className="text-xl font-semibold tracking-tight">{p.name}</h2>
              {p.description && <p className="mt-1 max-w-2xl text-[13px] text-muted-foreground">{p.description}</p>}
            </div>
            {p.can_manage && (
              <Button size="sm" variant="outline" onClick={() => setEditing(true)}>
                <Pencil /> Edit
              </Button>
            )}
          </div>
          <div className="mt-4 grid grid-cols-2 gap-4 sm:grid-cols-[minmax(0,2fr)_repeat(3,minmax(0,1fr))]">
            <div className="col-span-2 space-y-1.5 sm:col-span-1">
              <div className="flex justify-between text-[12px]">
                <span className="text-muted-foreground">Progress · {p.stats.completed} of {p.stats.total} tasks</span>
                <span className="font-medium tabular">{p.stats.progress}%</span>
              </div>
              <Progress value={p.stats.progress} aria-label={`${p.stats.progress}% of tasks completed`} />
              <p className="flex flex-wrap gap-x-3 text-[11px] text-muted-foreground">
                {STATUSES.map((s) => (
                  <span key={s} className="inline-flex items-center gap-1">
                    <span className={cn('size-1.5 rounded-full', STATUS[s].dot)} aria-hidden />
                    {STATUS[s].label} {p.stats.by_status[s]}
                  </span>
                ))}
              </p>
            </div>
            <div>
              <p className="text-[12px] text-muted-foreground">Overdue</p>
              <p className={cn('text-lg font-semibold tabular', p.stats.overdue > 0 && 'text-destructive')}>{p.stats.overdue}</p>
            </div>
            <div>
              <p className="text-[12px] text-muted-foreground">Time logged</p>
              <p className="text-lg font-semibold tabular">{formatSeconds(p.stats.time_spent_seconds)}</p>
            </div>
            <div className="col-span-2 sm:col-span-1">
              <p className="flex items-center gap-1 text-[12px] text-muted-foreground">
                <Users className="size-3.5" aria-hidden /> {p.members.length} members{p.due_date && ` · due ${formatDue(p.due_date)}`}
              </p>
              <AvatarGroup people={p.members} max={7} size="md" className="mt-1" />
            </div>
          </div>
        </Card>
      )}

      <div className="flex flex-wrap items-center gap-3">
        <SegmentedControl<View>
          label="View"
          value={view}
          onChange={changeView}
          options={[
            { value: 'board', label: 'Board', icon: Columns3 },
            { value: 'list', label: 'List', icon: List },
            { value: 'timeline', label: 'Timeline', icon: CalendarRange },
            { value: 'milestones', label: 'Milestones', icon: Flag },
          ]}
        />
        <div className="relative w-full sm:w-56">
          <Search className="pointer-events-none absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2 text-muted-foreground" aria-hidden />
          <Input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Filter tasks" aria-label="Filter tasks" className="h-8 pl-8 text-[13px]" />
        </div>
        <FilterSelect
          label="Assignee"
          value={assignee === ANY ? null : assignee}
          onChange={(v) => setAssignee(v ?? ANY)}
          options={[{ value: 'none', label: 'Unassigned' }, ...(p?.members ?? []).map((m) => ({ value: m.id, label: m.full_name }))]}
          allLabel="Anyone"
        />
        <FilterSelect
          label="Priority"
          value={priority === ANY ? null : priority}
          onChange={(v) => setPriority(v ?? ANY)}
          options={PRIORITIES.map((pr) => ({ value: pr, label: PRIORITY[pr as TaskPriority].label }))}
          allLabel="Any priority"
        />
        {(labels.data?.length ?? 0) > 0 && (
          <FilterSelect
            label="Label"
            value={label === ANY ? null : label}
            onChange={(v) => setLabel(v ?? ANY)}
            options={(labels.data ?? []).map((l) => ({ value: l.name, label: `${l.name} (${l.count})` }))}
            allLabel="Any label"
          />
        )}
        {view !== 'milestones' && (milestones.data?.length ?? 0) > 0 && (
          <FilterSelect
            label="Milestone"
            value={milestone === ANY ? null : milestone}
            onChange={(v) => setMilestone(v ?? ANY)}
            options={[{ value: 'none', label: 'No milestone' }, ...(milestones.data ?? []).map((m) => ({ value: m.id, label: m.name }))]}
            allLabel="Any milestone"
          />
        )}
      </div>

      {tasks.isError ? (
        <Card>
          <WidgetError error={tasks.error} onRetry={() => void tasks.refetch()} />
        </Card>
      ) : !tasks.data ? (
        <div className="grid grid-cols-5 gap-3">
          {STATUSES.map((s) => (
            <Skeleton key={s} className="h-64" />
          ))}
        </div>
      ) : view === 'board' ? (
        <TaskBoard tasks={visible} projectId={p?.status === 'active' ? projectId : undefined} onOpen={setOpenTask} />
      ) : view === 'timeline' ? (
        <Card className="overflow-hidden py-0">
          <Timeline tasks={visible} milestones={milestones.data ?? []} onOpen={setOpenTask} />
        </Card>
      ) : view === 'milestones' ? (
        <MilestoneBoard
          tasks={visible}
          milestones={milestones.data ?? []}
          projectId={projectId}
          canManage={Boolean(p?.can_manage_tasks) && p?.status === 'active'}
          onOpen={setOpenTask}
        />
      ) : (
        <Card className="overflow-hidden py-0">
          <TaskList tasks={visible} onOpen={setOpenTask} />
        </Card>
      )}

      <TaskDrawer taskId={openTask} onClose={() => setOpenTask(null)} />
      {editing && p && <ProjectDialog open onOpenChange={setEditing} project={p} />}
    </div>
  )
}
