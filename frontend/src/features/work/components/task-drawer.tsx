import { useRef, useState, type FormEvent, type ReactNode } from 'react'
import { Dialog as SheetPrimitive } from 'radix-ui'
import { CheckSquare, Clock, Download, FileText, Paperclip, Plus, Send, Trash2, X } from 'lucide-react'
import { toast } from 'sonner'

import { ConfirmDialog } from '@/components/common/confirm-dialog'
import { PersonAvatar } from '@/components/common/person'
import { Button } from '@/components/ui/button'
import { Checkbox, Textarea } from '@/components/ui/form-controls'
import { Input } from '@/components/ui/input'
import { Skeleton, Spinner } from '@/components/ui/misc'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { formatSeconds, todayIn } from '@/features/activity/format'
import { formatBytes } from '@/features/screenshots/format'
import {
  useAddComment,
  useCreateTask,
  useDeleteAttachment,
  useDeleteComment,
  useDeleteTask,
  useLabels,
  useLogTime,
  useMilestones,
  useProject,
  useTask,
  useUpdateTask,
  useUploadAttachment,
} from '@/features/work/api'
import { AssigneePicker } from '@/features/work/components/assignee-picker'
import { LabelEditor } from '@/features/work/components/labels'
import { StatusSelect } from '@/features/work/components/task-list'
import { TimerButton, useElapsed } from '@/features/work/components/timer'
import { PRIORITIES, PRIORITY } from '@/features/work/meta'
import { errorMessage } from '@/lib/api-client'
import { formatDateTime, formatRelative } from '@/lib/format'
import { cn } from '@/lib/utils'
import { useAuthStore } from '@/stores/auth-store'
import type { TaskActivityItem, TaskDetail, TaskPriority } from '@/types/api'

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="grid grid-cols-[96px_minmax(0,1fr)] items-center gap-3 text-[13px]">
      <span className="text-muted-foreground">{label}</span>
      <div className="min-w-0">{children}</div>
    </div>
  )
}

const ACTIVITY_TEXT: Record<string, (d: Record<string, unknown>) => string> = {
  created: () => 'created the task',
  status_changed: (d) => `moved it from ${String(d.from).replace('_', ' ').toLowerCase()} to ${String(d.to).replace('_', ' ').toLowerCase()}`,
  renamed: (d) => `renamed it to “${String(d.to)}”`,
  description_changed: () => 'updated the description',
  priority_changed: (d) => `changed priority to ${String(d.to)}`,
  due_changed: (d) => (d.to ? `set the due date to ${String(d.to)}` : 'removed the due date'),
  assignees_changed: (d) =>
    [
      (d.added as string[])?.length ? `assigned ${(d.added as string[]).join(', ')}` : '',
      (d.removed as string[])?.length ? `unassigned ${(d.removed as string[]).join(', ')}` : '',
    ]
      .filter(Boolean)
      .join(' and '),
  commented: () => 'commented',
  attachment_added: (d) => `attached ${String(d.filename)}`,
  attachment_removed: (d) => `removed ${String(d.filename)}`,
  timer_started: () => 'started a timer',
  timer_stopped: () => 'stopped the timer',
  time_logged: (d) => `logged ${String(d.minutes)} min for ${String(d.day)}`,
  subtask_added: (d) => `added subtask ${String(d.subtask)}`,
  subtask_removed: (d) => `removed subtask “${String(d.title)}”`,
  start_changed: (d) => (d.to ? `set the start date to ${String(d.to)}` : 'removed the start date'),
  labels_changed: (d) =>
    [
      (d.added as string[])?.length ? `added label${(d.added as string[]).length > 1 ? 's' : ''} ${(d.added as string[]).join(', ')}` : '',
      (d.removed as string[])?.length ? `removed ${(d.removed as string[]).join(', ')}` : '',
    ]
      .filter(Boolean)
      .join(' and '),
  milestone_changed: (d) => (d.to ? `moved it to milestone “${String(d.to)}”` : `removed it from milestone “${String(d.from)}”`),
}

const NO_MILESTONE = '__none__'

function ActivityLine({ item }: { item: TaskActivityItem }) {
  const text = ACTIVITY_TEXT[item.kind]?.(item.data) ?? item.kind
  return (
    <li className="flex gap-2.5 text-[12px]">
      <PersonAvatar name={item.actor?.full_name ?? 'System'} seed={item.actor?.id} className="mt-0.5 size-5 text-[8px]" />
      <p className="min-w-0 text-muted-foreground">
        <span className="font-medium text-foreground">{item.actor?.full_name ?? 'Someone'}</span> {text}
        <span className="ml-1.5 whitespace-nowrap" title={formatDateTime(item.created_at)}>
          · {formatRelative(item.created_at)}
        </span>
      </p>
    </li>
  )
}

function Subtasks({ task }: { task: TaskDetail }) {
  const create = useCreateTask()
  const update = useUpdateTask()
  const [title, setTitle] = useState('')
  const add = (event: FormEvent) => {
    event.preventDefault()
    if (!title.trim()) return
    create.mutate({ project_id: task.project_id, title: title.trim(), parent_id: task.id }, { onSuccess: () => setTitle(''), onError: (e) => toast.error(errorMessage(e)) })
  }
  return (
    <section className="space-y-2">
      <h3 className="flex items-center gap-2 text-[13px] font-semibold">
        <CheckSquare className="size-4 text-muted-foreground" aria-hidden /> Subtasks
        {task.subtasks.length > 0 && (
          <span className="text-[12px] font-normal text-muted-foreground tabular">
            {task.subtasks.filter((s) => s.status === 'COMPLETED').length}/{task.subtasks.length}
          </span>
        )}
      </h3>
      <ul className="space-y-1">
        {task.subtasks.map((sub) => {
          const done = sub.status === 'COMPLETED'
          return (
            <li key={sub.id} className="flex items-center gap-2 rounded-md px-1 py-1 hover:bg-muted/60">
              <Checkbox
                checked={done}
                aria-label={`Mark ${sub.title} ${done ? 'not completed' : 'completed'}`}
                disabled={!sub.can_edit}
                onCheckedChange={() => update.mutate({ id: sub.id, status: done ? 'TODO' : 'COMPLETED' })}
              />
              <span className={cn('flex-1 truncate text-[13px]', done && 'text-muted-foreground line-through')}>{sub.title}</span>
              <span className="text-[11px] text-muted-foreground tabular">{sub.reference}</span>
            </li>
          )
        })}
      </ul>
      {task.can_edit && (
        <form onSubmit={add} className="flex gap-2">
          <Input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Add a subtask" aria-label="New subtask" className="h-8 text-[13px]" />
          <Button type="submit" size="sm" variant="outline" disabled={!title.trim()} loading={create.isPending}>
            <Plus /> Add
          </Button>
        </form>
      )}
    </section>
  )
}

function Attachments({ task }: { task: TaskDetail }) {
  const upload = useUploadAttachment()
  const remove = useDeleteAttachment()
  const input = useRef<HTMLInputElement>(null)
  return (
    <section className="space-y-2">
      <div className="flex items-center justify-between">
        <h3 className="flex items-center gap-2 text-[13px] font-semibold">
          <Paperclip className="size-4 text-muted-foreground" aria-hidden /> Files
        </h3>
        <input
          ref={input}
          type="file"
          className="sr-only"
          aria-label="Attach a file"
          onChange={(e) => {
            const file = e.target.files?.[0]
            e.target.value = ''
            if (!file) return
            if (file.size > 9 * 1024 * 1024) return toast.error('Files must be at most 9 MB.')
            upload.mutate({ taskId: task.id, file }, { onSuccess: () => toast.success(`${file.name} attached`), onError: (err) => toast.error(errorMessage(err)) })
          }}
        />
        <Button size="sm" variant="ghost" onClick={() => input.current?.click()} loading={upload.isPending}>
          <Plus /> Attach
        </Button>
      </div>
      {task.attachments.length === 0 ? (
        <p className="text-[12px] text-muted-foreground">No files. Up to 9 MB each, stored encrypted.</p>
      ) : (
        <ul className="divide-y rounded-lg border">
          {task.attachments.map((a) => (
            <li key={a.id} className="flex items-center gap-3 px-3 py-2">
              <FileText className="size-4 shrink-0 text-muted-foreground" aria-hidden />
              <div className="min-w-0 flex-1">
                <p className="truncate text-[13px] font-medium">{a.filename}</p>
                <p className="text-[11px] text-muted-foreground">
                  {formatBytes(a.size_bytes)} · {a.uploaded_by?.full_name ?? 'Someone'} · {formatRelative(a.created_at)}
                </p>
              </div>
              <Button asChild size="icon-sm" variant="ghost">
                <a href={a.download_url} target="_blank" rel="noreferrer noopener" aria-label={`Download ${a.filename}`}>
                  <Download />
                </a>
              </Button>
              {a.can_delete && (
                <Button size="icon-sm" variant="ghost" aria-label={`Remove ${a.filename}`} onClick={() => remove.mutate({ taskId: task.id, id: a.id })}>
                  <Trash2 />
                </Button>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}

function Comments({ task }: { task: TaskDetail }) {
  const add = useAddComment()
  const remove = useDeleteComment()
  const [body, setBody] = useState('')
  const submit = (event: FormEvent) => {
    event.preventDefault()
    if (!body.trim()) return
    add.mutate({ taskId: task.id, body: body.trim() }, { onSuccess: () => setBody(''), onError: (e) => toast.error(errorMessage(e)) })
  }
  return (
    <div className="space-y-4">
      {task.comments.length === 0 && <p className="text-[12px] text-muted-foreground">No comments yet.</p>}
      <ul className="space-y-3">
        {task.comments.map((c) => (
          <li key={c.id} className="flex gap-2.5">
            <PersonAvatar name={c.author?.full_name ?? '?'} seed={c.author?.id} className="size-7 text-[10px]" />
            <div className="min-w-0 flex-1 rounded-lg bg-muted/60 px-3 py-2">
              <p className="flex items-center gap-2 text-[12px]">
                <span className="font-medium">{c.author?.full_name ?? 'Someone'}</span>
                <span className="text-muted-foreground" title={formatDateTime(c.created_at)}>
                  {formatRelative(c.created_at)}
                  {c.edited_at && ' · edited'}
                </span>
                {c.can_edit && (
                  <button type="button" className="ml-auto text-muted-foreground hover:text-destructive" aria-label="Delete comment" onClick={() => remove.mutate({ taskId: task.id, id: c.id })}>
                    <X className="size-3.5" />
                  </button>
                )}
              </p>
              <p className="mt-0.5 text-[13px] break-words whitespace-pre-wrap">{c.body}</p>
            </div>
          </li>
        ))}
      </ul>
      <form onSubmit={submit} className="flex gap-2">
        <Textarea
          value={body}
          onChange={(e) => setBody(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) submit(e)
          }}
          placeholder="Write a comment… (Ctrl+Enter to send)"
          aria-label="New comment"
          className="min-h-16 text-[13px]"
          maxLength={5000}
        />
        <Button type="submit" size="icon" className="self-end" aria-label="Send comment" disabled={!body.trim()} loading={add.isPending}>
          <Send />
        </Button>
      </form>
    </div>
  )
}

function TimePanel({ task }: { task: TaskDetail }) {
  const timeZone = useAuthStore((s) => s.company?.timezone ?? 'UTC')
  const log = useLogTime()
  const [minutes, setMinutes] = useState('')
  const [day, setDay] = useState(() => todayIn(timeZone))
  const submit = (event: FormEvent) => {
    event.preventDefault()
    const value = Number(minutes)
    if (!value) return
    log.mutate({ taskId: task.id, minutes: value, day }, { onSuccess: () => setMinutes(''), onError: (e) => toast.error(errorMessage(e)) })
  }
  return (
    <div className="space-y-4">
      <form onSubmit={submit} className="flex flex-wrap items-end gap-2">
        <div className="space-y-1 text-[12px]">
          <label htmlFor="log-minutes" className="text-muted-foreground">
            Minutes
          </label>
          <Input id="log-minutes" type="number" min={1} max={1440} value={minutes} onChange={(e) => setMinutes(e.target.value)} className="h-8 w-24" />
        </div>
        <div className="space-y-1 text-[12px]">
          <label htmlFor="log-day" className="text-muted-foreground">
            Day
          </label>
          <Input id="log-day" type="date" value={day} max={todayIn(timeZone)} onChange={(e) => setDay(e.target.value)} className="h-8 w-40" />
        </div>
        <Button type="submit" size="sm" variant="outline" disabled={!Number(minutes)} loading={log.isPending}>
          Log time
        </Button>
      </form>
      {task.time_entries.length === 0 ? (
        <p className="text-[12px] text-muted-foreground">No time logged yet.</p>
      ) : (
        <ul className="divide-y rounded-lg border text-[12px]">
          {task.time_entries.map((e) => (
            <li key={e.id} className="flex items-center gap-2.5 px-3 py-2">
              <PersonAvatar name={e.employee?.full_name ?? '?'} seed={e.employee?.id} className="size-5 text-[8px]" />
              <span className="min-w-0 flex-1 truncate">
                {e.employee?.full_name} · {formatDateTime(e.started_at)}
                {e.source === 'manual' && <span className="text-muted-foreground"> · manual{e.note ? `: ${e.note}` : ''}</span>}
              </span>
              <span className={cn('font-medium tabular', !e.ended_at && 'text-primary')}>{e.ended_at ? formatSeconds(e.seconds) : 'running'}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

function DrawerBody({ task, onClose }: { task: TaskDetail; onClose: () => void }) {
  const update = useUpdateTask()
  const remove = useDeleteTask()
  const project = useProject(task.project_id)
  const milestones = useMilestones(task.parent_id ? undefined : task.project_id)
  const labels = useLabels(task.project_id)
  const [title, setTitle] = useState(task.title)
  const [description, setDescription] = useState(task.description ?? '')
  const [confirmDelete, setConfirmDelete] = useState(false)
  const save = (changes: Parameters<typeof update.mutate>[0]) => update.mutate(changes, { onError: (e) => toast.error(errorMessage(e)) })
  // My running entry (if any) ticks locally; the server total already includes its seconds at fetch time.
  const runningEntry = task.timer_running ? task.time_entries.find((e) => !e.ended_at) : undefined
  const elapsed = useElapsed(runningEntry?.started_at)
  const total = task.time_spent_seconds - (runningEntry?.seconds ?? 0) + (runningEntry ? elapsed : 0)

  return (
    <>
      <div className="flex items-center gap-2 border-b px-5 py-3 pr-12 text-[12px] text-muted-foreground">
        <span className="font-medium tabular">{task.reference}</span>
        <span>·</span>
        <span className="truncate">{task.project_name}</span>
        {task.parent_id && <span className="rounded bg-muted px-1.5">Subtask</span>}
      </div>
      <div className="flex-1 space-y-6 overflow-y-auto px-5 py-5">
        <div className="space-y-2">
          <SheetPrimitive.Title asChild>
            <textarea
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              onBlur={() => title.trim() && title.trim() !== task.title && save({ id: task.id, title: title.trim() })}
              readOnly={!task.can_edit}
              rows={1}
              aria-label="Task title"
              className="w-full resize-none rounded-md border border-transparent bg-transparent px-1 py-0.5 text-lg font-semibold outline-none [field-sizing:content] hover:border-input focus:border-ring"
            />
          </SheetPrimitive.Title>
          <SheetPrimitive.Description className="sr-only">Task details, subtasks, files, comments and time</SheetPrimitive.Description>
        </div>

        <div className="space-y-2.5">
          <Field label="Status">
            <StatusSelect task={task} />
          </Field>
          <Field label="Priority">
            <Select value={task.priority} disabled={!task.can_edit} onValueChange={(v) => save({ id: task.id, priority: v as TaskPriority })}>
              <SelectTrigger size="sm" className="w-40" aria-label="Priority">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {PRIORITIES.map((p) => {
                  const meta = PRIORITY[p]
                  return (
                    <SelectItem key={p} value={p}>
                      <span className="inline-flex items-center gap-1.5">
                        <meta.icon className={cn('size-3.5', meta.className)} aria-hidden />
                        {meta.label}
                      </span>
                    </SelectItem>
                  )
                })}
              </SelectContent>
            </Select>
          </Field>
          <Field label="Assignees">
            <AssigneePicker
              members={project.data?.members ?? task.assignees}
              value={task.assignees.map((a) => a.id)}
              onChange={(ids) => save({ id: task.id, assignee_ids: ids })}
              disabled={!task.can_edit}
            />
          </Field>
          <Field label="Due date">
            <div className="flex items-center gap-2">
              <Input
                type="date"
                value={task.due_date ?? ''}
                disabled={!task.can_edit}
                onChange={(e) => (e.target.value ? save({ id: task.id, due_date: e.target.value }) : save({ id: task.id, clear_due_date: true }))}
                className={cn('h-8 w-40', task.overdue && 'border-destructive text-destructive')}
                aria-label="Due date"
              />
              {task.overdue && <span className="text-[12px] font-medium text-destructive">Overdue</span>}
            </div>
          </Field>
          <Field label="Start date">
            <Input
              type="date"
              value={task.start_date ?? ''}
              max={task.due_date ?? undefined}
              disabled={!task.can_edit}
              onChange={(e) => save({ id: task.id, start_date: e.target.value || null })}
              className="h-8 w-40"
              aria-label="Start date"
            />
          </Field>
          {!task.parent_id && (
            <Field label="Milestone">
              <Select
                value={task.milestone_id ?? NO_MILESTONE}
                disabled={!task.can_edit}
                onValueChange={(v) => save({ id: task.id, milestone_id: v === NO_MILESTONE ? null : v })}
              >
                <SelectTrigger size="sm" className="w-56" aria-label="Milestone">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={NO_MILESTONE}>No milestone</SelectItem>
                  {(milestones.data ?? [])
                    .filter((m) => !m.closed || m.id === task.milestone_id)
                    .map((m) => (
                      <SelectItem key={m.id} value={m.id}>
                        {m.name}
                        {m.closed && ' (closed)'}
                      </SelectItem>
                    ))}
                </SelectContent>
              </Select>
            </Field>
          )}
          <Field label="Labels">
            <LabelEditor
              value={task.labels}
              onChange={(next) => save({ id: task.id, labels: next })}
              suggestions={(labels.data ?? []).map((l) => l.name)}
              disabled={!task.can_edit}
            />
          </Field>
          <Field label="Time">
            <div className="flex flex-wrap items-center gap-3">
              <span className="inline-flex items-center gap-1.5 font-medium tabular">
                <Clock className="size-3.5 text-muted-foreground" aria-hidden />
                {formatSeconds(total)}
                {task.estimate_minutes && <span className="font-normal text-muted-foreground">of {formatSeconds(task.estimate_minutes * 60)}</span>}
              </span>
              <TimerButton task={task} />
            </div>
          </Field>
        </div>

        <section className="space-y-1.5">
          <h3 className="text-[13px] font-semibold">Description</h3>
          <Textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            onBlur={() => description !== (task.description ?? '') && save({ id: task.id, description: description || null })}
            readOnly={!task.can_edit}
            placeholder={task.can_edit ? 'Add details, acceptance criteria, links…' : 'No description.'}
            className="min-h-24 text-[13px]"
            maxLength={10_000}
          />
        </section>

        {!task.parent_id && <Subtasks task={task} />}
        <Attachments task={task} />

        <Tabs defaultValue="comments">
          <TabsList>
            <TabsTrigger value="comments">Comments {task.comments.length > 0 && `· ${task.comments.length}`}</TabsTrigger>
            <TabsTrigger value="activity">Activity</TabsTrigger>
            <TabsTrigger value="time">Time</TabsTrigger>
          </TabsList>
          <TabsContent value="comments" className="pt-3">
            <Comments task={task} />
          </TabsContent>
          <TabsContent value="activity" className="pt-3">
            <ul className="space-y-2.5">
              {task.activity.map((a) => (
                <ActivityLine key={a.id} item={a} />
              ))}
            </ul>
          </TabsContent>
          <TabsContent value="time" className="pt-3">
            <TimePanel task={task} />
          </TabsContent>
        </Tabs>
      </div>
      <div className="flex items-center justify-between border-t px-5 py-3 text-[11px] text-muted-foreground">
        <span>Created {formatDateTime(task.created_at)}</span>
        {task.can_edit && (
          <Button size="sm" variant="ghost" className="text-destructive hover:bg-destructive-soft hover:text-destructive" onClick={() => setConfirmDelete(true)}>
            <Trash2 /> Delete
          </Button>
        )}
      </div>
      <ConfirmDialog
        open={confirmDelete}
        onOpenChange={setConfirmDelete}
        title={`Delete ${task.reference}?`}
        description="The task, its subtasks, comments and files are removed. Logged time stays in reports."
        confirmLabel="Delete task"
        destructive
        loading={remove.isPending}
        onConfirm={() =>
          remove.mutate(task.id, {
            onSuccess: () => {
              setConfirmDelete(false)
              onClose()
              toast.success(`${task.reference} deleted`)
            },
            onError: (e) => toast.error(errorMessage(e)),
          })
        }
      />
    </>
  )
}

/** Task details in a side panel. Controlled by the caller (usually the `?task=` search parameter). */
export function TaskDrawer({ taskId, onClose }: { taskId: string | null; onClose: () => void }) {
  const query = useTask(taskId)
  return (
    <SheetPrimitive.Root open={taskId !== null} onOpenChange={(open) => !open && onClose()}>
      <SheetPrimitive.Portal>
        <SheetPrimitive.Overlay className="fixed inset-0 z-50 bg-[oklch(0.15_0.02_285/0.35)] data-[state=open]:animate-in data-[state=open]:fade-in-0" />
        <SheetPrimitive.Content
          className="fixed inset-y-0 right-0 z-50 flex w-full flex-col border-l bg-background shadow-elevated outline-none data-[state=open]:animate-in data-[state=open]:slide-in-from-right sm:max-w-xl"
          aria-describedby={undefined}
        >
          {query.isError ? (
            <div className="p-6 text-[13px]">
              <SheetPrimitive.Title className="font-semibold">Task unavailable</SheetPrimitive.Title>
              <p className="mt-1 text-muted-foreground">{errorMessage(query.error)}</p>
            </div>
          ) : !query.data ? (
            <div className="space-y-4 p-6">
              <SheetPrimitive.Title className="sr-only">Loading task</SheetPrimitive.Title>
              <Spinner className="size-5" />
              <Skeleton className="h-8" />
              <Skeleton className="h-40" />
            </div>
          ) : (
            <DrawerBody key={`${query.data.id}:${query.data.updated_at}`} task={query.data} onClose={onClose} />
          )}
          <SheetPrimitive.Close className="absolute top-2.5 right-3 rounded-md p-1.5 text-muted-foreground transition hover:bg-accent hover:text-foreground" aria-label="Close task">
            <X className="size-4" />
          </SheetPrimitive.Close>
        </SheetPrimitive.Content>
      </SheetPrimitive.Portal>
    </SheetPrimitive.Root>
  )
}
