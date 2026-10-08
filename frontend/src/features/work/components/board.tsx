import { useMemo, useState, type FormEvent } from 'react'
import {
  closestCorners,
  DndContext,
  DragOverlay,
  KeyboardSensor,
  PointerSensor,
  useDroppable,
  useSensor,
  useSensors,
  type DragEndEvent,
  type DragOverEvent,
  type CollisionDetection,
  type DragStartEvent,
} from '@dnd-kit/core'
import { SortableContext, sortableKeyboardCoordinates, useSortable, verticalListSortingStrategy } from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import { Plus } from 'lucide-react'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { useCreateTask, useMoveTask } from '@/features/work/api'
import { TaskCard } from '@/features/work/components/task-card'
import { STATUS, STATUSES } from '@/features/work/meta'
import { errorMessage } from '@/lib/api-client'
import { cn } from '@/lib/utils'
import type { Task, TaskStatus } from '@/types/api'

type Columns = Record<TaskStatus, Task[]>

// The dragged card's own droppable stays put under the overlay; ignoring it keeps the first keyboard step from resolving to its origin.
const collisions: CollisionDetection = (args) => closestCorners({ ...args, droppableContainers: args.droppableContainers.filter((c) => c.id !== args.active.id) })

function group(tasks: Task[]): Columns {
  const columns = Object.fromEntries(STATUSES.map((s) => [s, [] as Task[]])) as Columns
  for (const t of [...tasks].sort((a, b) => a.rank - b.rank)) columns[t.status].push(t)
  return columns
}

function SortableCard({ task, onOpen, showProject }: { task: Task; onOpen: (id: string) => void; showProject?: boolean }) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id: task.id,
    data: { status: task.status },
    disabled: !task.can_edit,
  })
  return (
    <div ref={setNodeRef} style={{ transform: CSS.Translate.toString(transform), transition }} className={cn(isDragging && 'opacity-30')}>
      <button
        type="button"
        {...attributes}
        {...listeners}
        aria-roledescription={task.can_edit ? 'Draggable task' : 'Task'}
        // No aria-label: the card's own text is the name, so it matches what sighted users see.
        onClick={() => onOpen(task.id)}
        // Enter opens via the native click; Space is reserved for pick up / drop, so it must not click.
        onKeyDown={(e) => {
          if (e.key !== 'Enter') listeners?.onKeyDown?.(e)
        }}
        onKeyUp={(e) => {
          if (e.key === ' ') e.preventDefault()
        }}
        className={cn(
          'block w-full rounded-lg text-left outline-none focus-visible:ring-[3px] focus-visible:ring-ring/40',
          task.can_edit ? 'cursor-grab active:cursor-grabbing' : 'cursor-pointer',
        )}
      >
        <TaskCard task={task} showProject={showProject} />
        <span className="sr-only">
          , {STATUS[task.status].label}. Press Enter to open{task.can_edit ? ', space to pick up and move' : ''}.
        </span>
      </button>
    </div>
  )
}

function QuickAdd({ projectId, status }: { projectId: string; status: TaskStatus }) {
  const create = useCreateTask()
  const [open, setOpen] = useState(false)
  const [title, setTitle] = useState('')
  const submit = (event: FormEvent) => {
    event.preventDefault()
    if (!title.trim()) return
    create.mutate(
      { project_id: projectId, title: title.trim(), status },
      { onSuccess: () => setTitle(''), onError: (error) => toast.error(errorMessage(error)) },
    )
  }
  if (!open)
    return (
      <Button variant="ghost" size="sm" className="w-full justify-start text-muted-foreground" onClick={() => setOpen(true)}>
        <Plus /> Add task
      </Button>
    )
  return (
    <form onSubmit={submit} className="space-y-1.5">
      <Input
        ref={(el) => el?.focus()}
        value={title}
        onChange={(e) => setTitle(e.target.value)}
        onKeyDown={(e) => e.key === 'Escape' && setOpen(false)}
        onBlur={() => !title && setOpen(false)}
        placeholder="Task title, then Enter"
        aria-label={`New task in ${STATUS[status].label}`}
        className="h-8 text-[13px]"
        disabled={create.isPending}
      />
    </form>
  )
}

function Column({
  status,
  tasks,
  projectId,
  onOpen,
  showProject,
}: {
  status: TaskStatus
  tasks: Task[]
  projectId?: string
  onOpen: (id: string) => void
  showProject?: boolean
}) {
  const { setNodeRef, isOver } = useDroppable({ id: `column:${status}`, data: { status } })
  return (
    <section className="flex w-72 shrink-0 flex-col rounded-xl bg-muted/50 lg:w-auto lg:min-w-0 lg:flex-1" aria-label={`${STATUS[status].label}, ${tasks.length} tasks`}>
      <header className="flex items-center gap-2 px-3 pt-3 pb-2">
        <span className={cn('size-2 rounded-full', STATUS[status].dot)} aria-hidden />
        <h3 className="text-[13px] font-semibold">{STATUS[status].label}</h3>
        <span className="rounded-full bg-background px-1.5 text-[11px] text-muted-foreground tabular">{tasks.length}</span>
      </header>
      <div ref={setNodeRef} className={cn('flex min-h-24 flex-1 flex-col gap-2 rounded-lg px-2 pb-2 transition-colors', isOver && 'bg-primary-soft/40')}>
        <SortableContext items={tasks.map((t) => t.id)} strategy={verticalListSortingStrategy}>
          {tasks.map((task) => (
            <SortableCard key={task.id} task={task} onOpen={onOpen} showProject={showProject} />
          ))}
        </SortableContext>
        {projectId && <QuickAdd projectId={projectId} status={status} />}
      </div>
    </section>
  )
}

/**
 * Kanban board. Drag with the mouse, touch, or the keyboard (focus a card, Space to lift, arrows to move,
 * Space to drop). Moves are applied optimistically and rolled back if the server refuses them.
 */
export function TaskBoard({
  tasks,
  projectId,
  onOpen,
  showProject,
}: {
  tasks: Task[]
  projectId?: string
  onOpen: (id: string) => void
  showProject?: boolean
}) {
  const move = useMoveTask()
  const base = useMemo(() => group(tasks), [tasks])
  // Local column order while dragging and until fresh data arrives (tied to the list it was derived from).
  const [local, setLocal] = useState<{ from: Task[]; columns: Columns } | null>(null)
  const columns = local && local.from === tasks ? local.columns : base
  const setColumns = (update: (current: Columns) => Columns) => setLocal({ from: tasks, columns: update(columns) })
  const reset = () => setLocal(null)
  const [activeId, setActiveId] = useState<string | null>(null)
  const active = useMemo(() => tasks.find((t) => t.id === activeId) ?? null, [tasks, activeId])
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  )

  const columnOf = (id: string): TaskStatus | null => {
    if (id.startsWith('column:')) return id.slice(7) as TaskStatus
    return STATUSES.find((s) => columns[s].some((t) => t.id === id)) ?? null
  }

  const onDragStart = (event: DragStartEvent) => setActiveId(String(event.active.id))

  const onDragOver = ({ active: a, over }: DragOverEvent) => {
    if (!over) return
    const from = columnOf(String(a.id))
    const to = columnOf(String(over.id))
    if (!from || !to || from === to) return
    setColumns((current) => {
      const moving = current[from].find((t) => t.id === a.id)
      if (!moving) return current
      const target = [...current[to]]
      const overIndex = target.findIndex((t) => t.id === over.id)
      target.splice(overIndex >= 0 ? overIndex : target.length, 0, { ...moving, status: to })
      return { ...current, [from]: current[from].filter((t) => t.id !== a.id), [to]: target }
    })
  }

  const onDragEnd = ({ active: a, over }: DragEndEvent) => {
    setActiveId(null)
    const to = over ? columnOf(String(over.id)) : null
    if (!over || !to) return reset()
    const list = [...columns[to]]
    const from = list.findIndex((t) => t.id === a.id)
    const overIndex = list.findIndex((t) => t.id === over.id)
    if (from >= 0 && overIndex >= 0 && from !== overIndex) {
      const [item] = list.splice(from, 1)
      list.splice(overIndex, 0, item)
    }
    const index = list.findIndex((t) => t.id === a.id)
    setColumns((c) => ({ ...c, [to]: list }))
    const original = tasks.find((t) => t.id === a.id)
    const originalIndex = original ? base[original.status].findIndex((t) => t.id === a.id) : -1
    if (original && index >= 0 && (original.status !== to || originalIndex !== index)) {
      move.mutate(
        { id: String(a.id), status: to, index },
        {
          onError: (error) => {
            toast.error(errorMessage(error))
            reset()
          },
        },
      )
    }
  }

  return (
    <DndContext
      sensors={sensors}
      collisionDetection={collisions}
      onDragStart={onDragStart}
      onDragOver={onDragOver}
      onDragEnd={onDragEnd}
      onDragCancel={() => {
        setActiveId(null)
        reset()
      }}
      accessibility={{
        announcements: {
          onDragStart: ({ active: a }) => `Picked up ${tasks.find((t) => t.id === a.id)?.reference ?? 'task'}.`,
          onDragOver: ({ over }) => (over ? `Over ${STATUS[columnOf(String(over.id)) ?? 'TODO'].label}.` : 'Not over a column.'),
          onDragEnd: ({ over }) => (over ? `Dropped in ${STATUS[columnOf(String(over.id)) ?? 'TODO'].label}.` : 'Dropped.'),
          onDragCancel: () => 'Move cancelled.',
        },
      }}
    >
      <div className="relative -mx-4 flex gap-3 overflow-x-auto px-4 pb-2 sm:-mx-6 sm:px-6 lg:mx-0 lg:px-0">
        {STATUSES.map((status) => (
          <Column key={status} status={status} tasks={columns[status]} projectId={projectId} onOpen={onOpen} showProject={showProject} />
        ))}
      </div>
      <DragOverlay>{active ? <TaskCard task={active} dragging showProject={showProject} /> : null}</DragOverlay>
    </DndContext>
  )
}
