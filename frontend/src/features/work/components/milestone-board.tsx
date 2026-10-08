import { useMemo, useState } from 'react'
import {
  DndContext,
  DragOverlay,
  KeyboardCode,
  KeyboardSensor,
  pointerWithin,
  PointerSensor,
  rectIntersection,
  useDraggable,
  useDroppable,
  useSensor,
  useSensors,
  type CollisionDetection,
  type DragEndEvent,
  type KeyboardCoordinateGetter,
} from '@dnd-kit/core'
import { CheckCircle2, Flag, MoreHorizontal, Pencil, Plus, RotateCcw, Trash2 } from 'lucide-react'
import { toast } from 'sonner'

import { ConfirmDialog } from '@/components/common/confirm-dialog'
import { Button } from '@/components/ui/button'
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from '@/components/ui/dropdown-menu'
import { Progress } from '@/components/ui/misc'
import { useDeleteMilestone, useUpdateMilestone, useUpdateTask } from '@/features/work/api'
import { MilestoneDialog } from '@/features/work/components/milestone-dialog'
import { TaskCard } from '@/features/work/components/task-card'
import { formatDue, STATUSES } from '@/features/work/meta'
import { errorMessage } from '@/lib/api-client'
import { cn } from '@/lib/utils'
import type { Milestone, Task } from '@/types/api'

const NONE = 'none'
const columnId = (milestoneId: string | null) => `ms:${milestoneId ?? NONE}`
const milestoneOf = (droppableId: string) => (droppableId === columnId(null) ? null : droppableId.slice(3))

// Pointer drops land on the column under the pointer; keyboard drops use the overlap with the dragged card.
const collisions: CollisionDetection = (args) => {
  const hits = pointerWithin(args)
  return hits.length ? hits : rectIntersection(args)
}

/** Arrow keys jump a lifted card a whole column left or right (there's no ordering inside a column). */
const columnCoordinates: KeyboardCoordinateGetter = (event, { context }) => {
  if (event.code !== KeyboardCode.Right && event.code !== KeyboardCode.Left) return undefined
  event.preventDefault()
  const rect = context.collisionRect
  if (!rect) return undefined
  const columns = [...context.droppableRects.entries()]
    .filter(([id]) => String(id).startsWith('ms:'))
    .map(([, r]) => r)
    .sort((a, b) => a.left - b.left)
  const centre = rect.left + rect.width / 2
  const current = columns.findIndex((c) => centre >= c.left && centre <= c.left + c.width)
  const target = columns[current + (event.code === KeyboardCode.Right ? 1 : -1)]
  return target ? { x: target.left + 8, y: target.top + 56 } : undefined
}

const statusOrder = (t: Task) => STATUSES.indexOf(t.status) * 1e9 + t.rank

function DraggableCard({ task, onOpen }: { task: Task; onOpen: (id: string) => void }) {
  const { attributes, listeners, setNodeRef, isDragging } = useDraggable({ id: task.id, disabled: !task.can_edit })
  return (
    <button
      ref={setNodeRef}
      type="button"
      {...attributes}
      {...listeners}
      aria-roledescription={task.can_edit ? 'Draggable task' : 'Task'}
      onClick={() => onOpen(task.id)}
      onKeyDown={(e) => {
        if (e.key !== 'Enter') listeners?.onKeyDown?.(e)
      }}
      onKeyUp={(e) => {
        if (e.key === ' ') e.preventDefault()
      }}
      className={cn(
        'block w-full rounded-lg text-left outline-none focus-visible:ring-[3px] focus-visible:ring-ring/40',
        task.can_edit ? 'cursor-grab active:cursor-grabbing' : 'cursor-pointer',
        isDragging && 'opacity-30',
      )}
    >
      <TaskCard task={task} />
      <span className="sr-only">. Press Enter to open{task.can_edit ? ', space to pick up and move to another milestone' : ''}.</span>
    </button>
  )
}

function MilestoneMenu({ milestone, onEdit }: { milestone: Milestone; onEdit: () => void }) {
  const update = useUpdateMilestone()
  const remove = useDeleteMilestone()
  const [confirm, setConfirm] = useState(false)
  const fail = { onError: (e: unknown) => toast.error(errorMessage(e)) }
  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="ghost" size="icon-sm" aria-label={`Actions for ${milestone.name}`} className="-mr-1 size-7">
            <MoreHorizontal />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          <DropdownMenuItem onSelect={onEdit}>
            <Pencil /> Edit
          </DropdownMenuItem>
          <DropdownMenuItem onSelect={() => update.mutate({ id: milestone.id, closed: !milestone.closed }, fail)}>
            {milestone.closed ? <RotateCcw /> : <CheckCircle2 />} {milestone.closed ? 'Reopen' : 'Mark as reached'}
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuItem variant="destructive" onSelect={() => setConfirm(true)}>
            <Trash2 /> Delete
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
      <ConfirmDialog
        open={confirm}
        onOpenChange={setConfirm}
        title={`Delete “${milestone.name}”?`}
        description="Its tasks stay in the project, without a milestone."
        confirmLabel="Delete milestone"
        destructive
        loading={remove.isPending}
        onConfirm={() => remove.mutate(milestone.id, { ...fail, onSuccess: () => setConfirm(false) })}
      />
    </>
  )
}

function MilestoneColumn({
  milestone,
  tasks,
  onOpen,
  onEdit,
}: {
  milestone: Milestone | null
  tasks: Task[]
  onOpen: (id: string) => void
  onEdit: (m: Milestone) => void
}) {
  const { setNodeRef, isOver } = useDroppable({ id: columnId(milestone?.id ?? null) })
  const label = milestone?.name ?? 'No milestone'
  return (
    <section
      className={cn('flex w-72 shrink-0 flex-col rounded-xl bg-muted/50', milestone?.closed && 'opacity-70')}
      aria-label={`${label}, ${tasks.length} tasks`}
    >
      <header className="space-y-2 px-3 pt-3 pb-2">
        <div className="flex items-center gap-2">
          {milestone ? (
            <Flag className={cn('size-3.5 shrink-0', milestone.closed ? 'text-success' : milestone.overdue ? 'text-destructive' : 'text-primary')} aria-hidden />
          ) : (
            <span className="size-3.5 shrink-0 rounded-full border border-dashed border-muted-foreground/50" aria-hidden />
          )}
          <h3 className="min-w-0 flex-1 truncate text-[13px] font-semibold" title={milestone?.description ?? undefined}>
            {label}
          </h3>
          <span className="rounded-full bg-background px-1.5 text-[11px] text-muted-foreground tabular">{tasks.length}</span>
          {milestone?.can_manage && <MilestoneMenu milestone={milestone} onEdit={() => onEdit(milestone)} />}
        </div>
        {milestone && (
          <div className="space-y-1">
            <div className="flex items-center justify-between text-[11px] text-muted-foreground">
              <span className={cn('tabular', milestone.overdue && 'font-medium text-destructive')}>
                {milestone.closed ? 'Reached' : milestone.due_date ? `Due ${formatDue(milestone.due_date)}${milestone.overdue ? ' · overdue' : ''}` : 'No date'}
              </span>
              <span className="tabular">
                {milestone.completed}/{milestone.total} · {milestone.progress}%
              </span>
            </div>
            <Progress value={milestone.progress} className="h-1" indicatorClassName={milestone.closed ? 'bg-success' : undefined} aria-label={`${milestone.name}: ${milestone.progress}% complete`} />
          </div>
        )}
      </header>
      <div ref={setNodeRef} className={cn('flex min-h-24 flex-1 flex-col gap-2 rounded-lg px-2 pb-2 transition-colors', isOver && 'bg-primary-soft/40')}>
        {tasks.map((t) => (
          <DraggableCard key={t.id} task={t} onOpen={onOpen} />
        ))}
        {tasks.length === 0 && <p className="px-2 py-6 text-center text-[12px] text-muted-foreground">Drop tasks here</p>}
      </div>
    </section>
  )
}

/**
 * Tasks grouped by milestone. Dragging a card only changes its milestone (status and order are the Kanban's
 * job), so a drop can never reshuffle anything else. Moves are optimistic and roll back on error.
 */
export function MilestoneBoard({
  tasks,
  milestones,
  projectId,
  canManage,
  onOpen,
}: {
  tasks: Task[]
  milestones: Milestone[]
  projectId: string
  canManage: boolean
  onOpen: (id: string) => void
}) {
  const update = useUpdateTask()
  const [pending, setPending] = useState<{ from: Task[]; moves: Record<string, string | null> } | null>(null)
  const moves = useMemo(() => (pending && pending.from === tasks ? pending.moves : {}), [pending, tasks])
  const [activeId, setActiveId] = useState<string | null>(null)
  const [editing, setEditing] = useState<Milestone | 'new' | null>(null)
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
    useSensor(KeyboardSensor, { coordinateGetter: columnCoordinates }),
  )

  const ordered = useMemo(
    () => [...milestones].sort((a, b) => Number(a.closed) - Number(b.closed) || (a.due_date ?? '9999').localeCompare(b.due_date ?? '9999')),
    [milestones],
  )
  const byColumn = useMemo(() => {
    const map = new Map<string | null, Task[]>([[null, []], ...ordered.map((m) => [m.id, []] as [string, Task[]])])
    for (const t of [...tasks].sort((a, b) => statusOrder(a) - statusOrder(b))) {
      const target = t.id in moves ? moves[t.id] : t.milestone_id
      ;(map.get(target) ?? map.get(null))!.push(t)
    }
    return map
  }, [tasks, ordered, moves])
  const active = tasks.find((t) => t.id === activeId) ?? null
  const name = (id: string | null) => (id ? (milestones.find((m) => m.id === id)?.name ?? 'milestone') : 'No milestone')

  const onDragEnd = ({ active: a, over }: DragEndEvent) => {
    setActiveId(null)
    if (!over) return
    const task = tasks.find((t) => t.id === a.id)
    const target = milestoneOf(String(over.id))
    const current = task ? (task.id in moves ? moves[task.id] : task.milestone_id) : undefined
    if (!task || target === current) return
    setPending({ from: tasks, moves: { ...moves, [task.id]: target } })
    update.mutate(
      { id: task.id, milestone_id: target },
      {
        onError: (error) => {
          toast.error(errorMessage(error))
          setPending(null)
        },
      },
    )
  }

  return (
    <>
      <DndContext
        sensors={sensors}
        collisionDetection={collisions}
        onDragStart={(e) => setActiveId(String(e.active.id))}
        onDragCancel={() => setActiveId(null)}
        onDragEnd={onDragEnd}
        accessibility={{
          announcements: {
            onDragStart: ({ active: a }) => `Picked up ${tasks.find((t) => t.id === a.id)?.reference ?? 'task'}. Use left and right arrows to choose a milestone.`,
            onDragOver: ({ over }) => (over ? `Over ${name(milestoneOf(String(over.id)))}.` : 'Not over a milestone.'),
            onDragEnd: ({ over }) => (over ? `Moved to ${name(milestoneOf(String(over.id)))}.` : 'Dropped; nothing changed.'),
            onDragCancel: () => 'Move cancelled.',
          },
        }}
      >
        <div className="relative -mx-4 flex gap-3 overflow-x-auto px-4 pb-2 sm:-mx-6 sm:px-6 lg:mx-0 lg:px-0">
          {[null, ...ordered].map((m) => (
            <MilestoneColumn key={m?.id ?? NONE} milestone={m} tasks={byColumn.get(m?.id ?? null) ?? []} onOpen={onOpen} onEdit={setEditing} />
          ))}
          {canManage && (
            <button
              type="button"
              onClick={() => setEditing('new')}
              className="flex w-56 shrink-0 flex-col items-center justify-center gap-2 rounded-xl border border-dashed text-[13px] text-muted-foreground transition hover:border-primary/50 hover:text-foreground"
            >
              <Plus className="size-4" aria-hidden /> Add milestone
            </button>
          )}
        </div>
        <DragOverlay>{active ? <TaskCard task={active} dragging /> : null}</DragOverlay>
      </DndContext>
      {!milestones.length && (
        <p className="text-[12px] text-muted-foreground">
          No milestones yet.{canManage ? ' Add one to group tasks towards a dated goal, then drag tasks into it.' : ' A project manager can add them.'}
        </p>
      )}
      {editing && (
        <MilestoneDialog projectId={projectId} milestone={editing === 'new' ? undefined : editing} onOpenChange={(open) => !open && setEditing(null)} />
      )}
    </>
  )
}
