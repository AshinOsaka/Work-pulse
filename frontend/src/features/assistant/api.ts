import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api, apiStream } from '@/lib/api-client'

export interface AssistantStatus {
  configured: boolean
  model: string | null
  suggestions: string[]
}

export interface ConversationSummary {
  id: string
  title: string
  updated_at: string
  questions: number
}

export interface CardLink {
  label: string
  href: string
}

interface CardBase {
  title: string
  period: string
  source: string
  link?: CardLink | null
  note?: string | null
}

export type CardCell = string | number | boolean | null

export interface MetricsCard extends CardBase {
  kind: 'metrics'
  metrics: { label: string; value: string; hint?: string | null }[]
  columns?: { key: string; label: string }[]
  rows?: (Record<string, CardCell> & { href?: string | null })[]
}

export interface TableCard extends CardBase {
  kind: 'table'
  columns: { key: string; label: string }[]
  rows: (Record<string, CardCell> & { href?: string | null })[]
}

export interface ChartCard extends CardBase {
  kind: 'chart'
  unit: string
  series: { label: string; value: number }[]
}

export interface ListCard extends CardBase {
  kind: 'list'
  items: { title: string; meta?: string | null; href?: string | null }[]
}

export type DataCard = MetricsCard | TableCard | ChartCard | ListCard

export type ToolStatus = 'running' | 'done' | 'error'

export interface ToolUse {
  id?: string
  name: string
  label: string
  status: ToolStatus
  message?: string | null
}

export interface UserTurn {
  id: string
  role: 'user'
  text: string
  created_at: string
}

export interface AssistantTurn {
  id: string
  role: 'assistant'
  text: string
  cards: DataCard[]
  tools: ToolUse[]
  error: string | null
  created_at: string
}

export type Turn = UserTurn | AssistantTurn

export interface Conversation {
  id: string
  title: string
  created_at: string
  updated_at: string
  turns: Turn[]
}

export type AskEvent =
  | { type: 'start'; conversation_id: string; turn_id: string; title: string }
  | { type: 'text'; delta: string }
  | ({ type: 'tool' } & ToolUse)
  | { type: 'card'; card: DataCard }
  | { type: 'error'; message: string }
  | { type: 'done'; turn: AssistantTurn }

export const assistantKeys = {
  status: ['assistant', 'status'] as const,
  conversations: ['assistant', 'conversations'] as const,
  conversation: (id: string) => ['assistant', 'conversations', id] as const,
}

export const useAssistantStatus = () => useQuery({ queryKey: assistantKeys.status, queryFn: () => api.get<AssistantStatus>('/assistant/status'), staleTime: 60_000 })

export const useConversations = () => useQuery({ queryKey: assistantKeys.conversations, queryFn: () => api.get<ConversationSummary[]>('/assistant/conversations') })

export const fetchConversation = (id: string) => api.get<Conversation>(`/assistant/conversations/${id}`)

export function useDeleteConversation() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => api.delete<void>(`/assistant/conversations/${id}`),
    onSuccess: (_, id) => client.setQueryData<ConversationSummary[]>(assistantKeys.conversations, (list) => list?.filter((c) => c.id !== id)),
    onSettled: () => void client.invalidateQueries({ queryKey: assistantKeys.conversations }),
  })
}

export function useClearConversations() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: () => api.delete<void>('/assistant/conversations'),
    onSuccess: () => client.setQueryData<ConversationSummary[]>(assistantKeys.conversations, []),
    onSettled: () => void client.invalidateQueries({ queryKey: assistantKeys.conversations }),
  })
}

/** Ask a question; `onEvent` receives each server-sent event as it arrives. Resolves when the stream ends. */
export async function ask(body: { message: string; conversation_id?: string }, onEvent: (event: AskEvent) => void, signal?: AbortSignal): Promise<void> {
  const response = await apiStream('/assistant/ask', body, signal)
  const reader = response.body?.getReader()
  if (!reader) throw new Error('The answer could not be read.')
  const decoder = new TextDecoder()
  let buffer = ''
  for (;;) {
    const { value, done } = await reader.read()
    buffer += decoder.decode(value, { stream: !done })
    let boundary = buffer.indexOf('\n\n')
    while (boundary !== -1) {
      const chunk = buffer.slice(0, boundary)
      buffer = buffer.slice(boundary + 2)
      for (const line of chunk.split('\n')) {
        if (line.startsWith('data: ')) onEvent(JSON.parse(line.slice(6)) as AskEvent)
      }
      boundary = buffer.indexOf('\n\n')
    }
    if (done) return
  }
}
