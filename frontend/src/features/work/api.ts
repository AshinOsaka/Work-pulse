import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api, toQuery } from '@/lib/api-client'
import type { LabelCount, Milestone, MyWork, Project, Task, TaskAttachment, TaskComment, TaskDetail, TaskPriority, TaskStatus, TimeEntry, TimerState, WorkSummary } from '@/types/api'

export const workKeys = {
  all: ['work'] as const,
  projects: (archived: boolean) => ['work', 'projects', archived] as const,
  project: (id: string) => ['work', 'project', id] as const,
  tasks: (params: TaskQuery) => ['work', 'tasks', params] as const,
  task: (id: string) => ['work', 'task', id] as const,
  timer: () => ['work', 'timer'] as const,
  myWork: () => ['work', 'my'] as const,
  summary: (params: Record<string, string | undefined>) => ['work', 'summary', params] as const,
  milestones: (projectId: string) => ['work', 'milestones', projectId] as const,
  labels: (projectId: string) => ['work', 'labels', projectId] as const,
}

export interface TaskQuery {
  project_id?: string
  assignee?: string
  team_id?: string
  priority?: TaskPriority
  search?: string
  due?: 'overdue' | 'today' | 'week'
  label?: string
  milestone_id?: string
}

/** Any task change can move counts, boards, timers and dashboards: refresh the whole module. */
function useWorkMutation<TVars, TResult>(fn: (vars: TVars) => Promise<TResult>) {
  const client = useQueryClient()
  return useMutation({ mutationFn: fn, onSettled: () => void client.invalidateQueries({ queryKey: workKeys.all }) })
}

export const useProjects = (archived = false) =>
  useQuery({ queryKey: workKeys.projects(archived), queryFn: () => api.get<Project[]>(`/projects${toQuery({ include_archived: archived || undefined })}`) })

export const useProject = (id: string) => useQuery({ queryKey: workKeys.project(id), queryFn: () => api.get<Project>(`/projects/${id}`) })

export const useTasks = (params: TaskQuery, enabled = true) =>
  useQuery({
    queryKey: workKeys.tasks(params),
    queryFn: () => api.get<Task[]>(`/tasks${toQuery({ ...params })}`),
    placeholderData: keepPreviousData,
    enabled,
  })

export const useTask = (id: string | null) =>
  useQuery({ queryKey: workKeys.task(id ?? ''), queryFn: () => api.get<TaskDetail>(`/tasks/${id}`), enabled: Boolean(id) })

export const useTimer = (enabled = true) =>
  useQuery({ queryKey: workKeys.timer(), queryFn: () => api.get<TimerState>('/me/timer'), refetchInterval: 30_000, enabled })

export const useMyWork = () => useQuery({ queryKey: workKeys.myWork(), queryFn: () => api.get<MyWork>('/me/work'), refetchInterval: 60_000 })

export const useWorkSummary = (params: { start: string; end: string; team_id?: string; project_id?: string }) =>
  useQuery({
    queryKey: workKeys.summary(params),
    queryFn: () => api.get<WorkSummary>(`/work/summary${toQuery({ ...params })}`),
    placeholderData: keepPreviousData,
  })

export const useMilestones = (projectId: string | undefined) =>
  useQuery({
    queryKey: workKeys.milestones(projectId ?? ''),
    queryFn: () => api.get<Milestone[]>(`/projects/${projectId}/milestones`),
    enabled: Boolean(projectId),
  })

export const useLabels = (projectId: string | undefined) =>
  useQuery({
    queryKey: workKeys.labels(projectId ?? ''),
    queryFn: () => api.get<LabelCount[]>(`/projects/${projectId}/labels`),
    enabled: Boolean(projectId),
  })

export interface MilestoneInput {
  name: string
  description?: string | null
  due_date?: string | null
}

export const useCreateMilestone = () =>
  useWorkMutation(({ projectId, ...input }: MilestoneInput & { projectId: string }) => api.post<Milestone>(`/projects/${projectId}/milestones`, input))
export const useUpdateMilestone = () =>
  useWorkMutation(({ id, ...input }: Partial<MilestoneInput> & { id: string; closed?: boolean }) => api.patch<Milestone>(`/milestones/${id}`, input))
export const useDeleteMilestone = () => useWorkMutation((id: string) => api.delete<void>(`/milestones/${id}`))

export interface ProjectInput {
  name: string
  key?: string
  description?: string | null
  color?: string
  member_ids?: string[]
  due_date?: string | null
}

export const useCreateProject = () => useWorkMutation((input: ProjectInput) => api.post<Project>('/projects', input))
export const useUpdateProject = () =>
  useWorkMutation(({ id, ...input }: Partial<ProjectInput> & { id: string; status?: 'active' | 'archived' }) => api.patch<Project>(`/projects/${id}`, input))
export const useSetMembers = () =>
  useWorkMutation(({ id, member_ids }: { id: string; member_ids: string[] }) => api.put<Project>(`/projects/${id}/members`, { member_ids }))

export interface TaskInput {
  project_id: string
  title: string
  description?: string | null
  status?: TaskStatus
  priority?: TaskPriority
  assignee_ids?: string[]
  parent_id?: string | null
  due_date?: string | null
  /** For updates, null clears these; leaving them out keeps the current value. */
  start_date?: string | null
  labels?: string[] | null
  milestone_id?: string | null
}

export const useCreateTask = () => useWorkMutation((input: TaskInput) => api.post<Task>('/tasks', input))
export const useUpdateTask = () =>
  useWorkMutation(({ id, ...input }: { id: string } & Partial<Omit<TaskInput, 'project_id' | 'parent_id'>> & { clear_due_date?: boolean }) =>
    api.patch<Task>(`/tasks/${id}`, input),
  )
export const useMoveTask = () =>
  useWorkMutation(({ id, status, index }: { id: string; status: TaskStatus; index: number }) => api.post<Task>(`/tasks/${id}/move`, { status, index }))
export const useDeleteTask = () => useWorkMutation((id: string) => api.delete<void>(`/tasks/${id}`))

export const useAddComment = () =>
  useWorkMutation(({ taskId, body }: { taskId: string; body: string }) => api.post<TaskComment>(`/tasks/${taskId}/comments`, { body }))
export const useEditComment = () =>
  useWorkMutation(({ taskId, id, body }: { taskId: string; id: string; body: string }) => api.patch<TaskComment>(`/tasks/${taskId}/comments/${id}`, { body }))
export const useDeleteComment = () =>
  useWorkMutation(({ taskId, id }: { taskId: string; id: string }) => api.delete<void>(`/tasks/${taskId}/comments/${id}`))

export const useUploadAttachment = () =>
  useWorkMutation(({ taskId, file }: { taskId: string; file: File }) =>
    api.post<TaskAttachment>(`/tasks/${taskId}/attachments${toQuery({ filename: file.name })}`, file, {
      headers: { 'Content-Type': file.type || 'application/octet-stream' },
    }),
  )
export const useDeleteAttachment = () =>
  useWorkMutation(({ taskId, id }: { taskId: string; id: string }) => api.delete<void>(`/tasks/${taskId}/attachments/${id}`))

export const useStartTimer = () => useWorkMutation((taskId: string) => api.post<TimerState>(`/tasks/${taskId}/timer/start`))
export const useStopTimer = () => useWorkMutation(() => api.post<TimerState>('/me/timer/stop'))
export const useLogTime = () =>
  useWorkMutation(({ taskId, minutes, day, note }: { taskId: string; minutes: number; day: string; note?: string }) =>
    api.post<TimeEntry>(`/tasks/${taskId}/time`, { minutes, day, note }),
  )
