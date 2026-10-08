import { useState } from 'react'
import { AlertTriangle, CalendarClock, FolderKanban, Plus } from 'lucide-react'
import { Link, useNavigate } from 'react-router'

import { EmptyState } from '@/components/common/empty-state'
import { AvatarGroup } from '@/components/common/person'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/misc'
import { Progress } from '@/components/ui/misc'
import { SegmentedControl } from '@/components/ui/segmented-control'
import { formatSeconds } from '@/features/activity/format'
import { WidgetError } from '@/features/dashboard/components/widget'
import { useProjects } from '@/features/work/api'
import { ProjectDialog } from '@/features/work/components/project-dialog'
import { formatDue, PROJECT_COLOR } from '@/features/work/meta'
import { useDocumentTitle } from '@/hooks/use-document-title'
import { cn } from '@/lib/utils'
import { usePermissions } from '@/stores/auth-store'
import type { Project } from '@/types/api'

function ProjectCard({ project }: { project: Project }) {
  const s = project.stats
  return (
    <Link to={`/projects/${project.id}`} className="group block focus-visible:outline-none">
      <Card className="relative h-full overflow-hidden p-5 transition group-hover:border-primary/40 group-hover:shadow-card group-focus-visible:ring-[3px] group-focus-visible:ring-ring/40">
        <span className={cn('absolute inset-y-0 left-0 w-1', PROJECT_COLOR[project.color])} aria-hidden />
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <p className="text-[11px] font-semibold tracking-wider text-muted-foreground">{project.key}</p>
            <h3 className="truncate text-[15px] font-semibold">{project.name}</h3>
          </div>
          {project.status === 'archived' && <span className="rounded bg-muted px-1.5 py-0.5 text-[11px] text-muted-foreground">Archived</span>}
        </div>
        {project.description && <p className="mt-1 line-clamp-2 text-[12px] text-muted-foreground">{project.description}</p>}
        <div className="mt-4 space-y-1.5">
          <div className="flex justify-between text-[12px]">
            <span className="text-muted-foreground">
              {s.completed} of {s.total} tasks done
            </span>
            <span className="font-medium tabular">{s.progress}%</span>
          </div>
          <Progress value={s.progress} aria-label={`${project.name}: ${s.progress}% of tasks completed`} />
        </div>
        <div className="mt-4 flex flex-wrap items-center gap-x-3 gap-y-1.5 text-[12px] text-muted-foreground">
          {s.overdue > 0 && (
            <span className="inline-flex items-center gap-1 font-medium text-destructive">
              <AlertTriangle className="size-3.5" aria-hidden /> {s.overdue} overdue
            </span>
          )}
          {project.due_date && (
            <span className="inline-flex items-center gap-1">
              <CalendarClock className="size-3.5" aria-hidden /> Due {formatDue(project.due_date)}
            </span>
          )}
          {s.time_spent_seconds > 0 && <span className="tabular">{formatSeconds(s.time_spent_seconds)} logged</span>}
          <AvatarGroup people={project.members} className="ml-auto" />
        </div>
      </Card>
    </Link>
  )
}

export default function ProjectsPage() {
  useDocumentTitle('Projects')
  const { can } = usePermissions()
  const navigate = useNavigate()
  const [show, setShow] = useState<'active' | 'all'>('active')
  const [creating, setCreating] = useState(false)
  const query = useProjects(show === 'all')
  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center gap-3">
        <SegmentedControl
          label="Show"
          value={show}
          onChange={setShow}
          options={[
            { value: 'active', label: 'Active' },
            { value: 'all', label: 'Including archived' },
          ]}
        />
        {can('PROJECT_MANAGE') && (
          <Button size="sm" className="ml-auto" onClick={() => setCreating(true)}>
            <Plus /> New project
          </Button>
        )}
      </div>
      {query.isError ? (
        <Card>
          <WidgetError error={query.error} onRetry={() => void query.refetch()} />
        </Card>
      ) : !query.data ? (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {Array.from({ length: 3 }, (_, i) => (
            <Skeleton key={i} className="h-48" />
          ))}
        </div>
      ) : query.data.length === 0 ? (
        <Card>
          <EmptyState
            icon={FolderKanban}
            title="No projects yet"
            description={can('PROJECT_MANAGE') ? 'Create a project, add members, and start planning tasks.' : "You're not a member of any project yet."}
            action={
              can('PROJECT_MANAGE') ? (
                <Button size="sm" onClick={() => setCreating(true)}>
                  <Plus /> New project
                </Button>
              ) : undefined
            }
          />
        </Card>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {query.data.map((p) => (
            <ProjectCard key={p.id} project={p} />
          ))}
        </div>
      )}
      {creating && <ProjectDialog open onOpenChange={setCreating} onCreated={(p) => navigate(`/projects/${p.id}`)} />}
    </div>
  )
}
