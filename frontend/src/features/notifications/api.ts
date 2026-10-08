import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api, toQuery } from '@/lib/api-client'
import type { NotificationChannels, NotificationPage, NotificationPreferences, NotificationSeverity, NotificationType } from '@/types/api'

export interface NotificationQuery {
  read?: boolean
  type?: NotificationType
  severity?: NotificationSeverity
  employee_id?: string
  since?: string
  page?: number
  page_size?: number
}

export const notificationKeys = {
  all: ['notifications'] as const,
  list: (q: NotificationQuery) => ['notifications', 'list', q] as const,
  unread: () => ['notifications', 'unread'] as const,
  prefs: () => ['notifications', 'prefs'] as const,
}

/** New notifications arrive over the WebSocket; polling is only a slow safety net. */
export const useNotifications = (q: NotificationQuery, enabled = true) =>
  useQuery({
    queryKey: notificationKeys.list(q),
    queryFn: () => api.get<NotificationPage>(`/notifications${toQuery({ ...q })}`),
    placeholderData: keepPreviousData,
    refetchInterval: 120_000,
    enabled,
  })

export const useUnreadCount = () =>
  useQuery({
    queryKey: notificationKeys.unread(),
    queryFn: () => api.get<{ unread: number }>('/notifications/unread-count'),
    refetchInterval: 120_000,
  })

export function useMarkNotifications() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (input: { ids?: string[]; all?: boolean; type?: NotificationType; read: boolean }) =>
      api.post<{ updated: number; unread: number }>('/notifications/mark', input),
    onSuccess: (result) => client.setQueryData(notificationKeys.unread(), { unread: result.unread }),
    onSettled: () => void client.invalidateQueries({ queryKey: notificationKeys.all }),
  })
}

export const usePreferences = () =>
  useQuery({ queryKey: notificationKeys.prefs(), queryFn: () => api.get<NotificationPreferences>('/notifications/preferences') })

type PreferencesInput = { throttle_minutes?: number; types?: Partial<Record<NotificationType, NotificationChannels>> }

/** Optimistic: switches flip at once and roll back if the server refuses. */
export function useUpdatePreferences() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (input: PreferencesInput) => api.put<NotificationPreferences>('/notifications/preferences', { types: {}, ...input }),
    onMutate: async (input) => {
      await client.cancelQueries({ queryKey: notificationKeys.prefs() })
      const previous = client.getQueryData<NotificationPreferences>(notificationKeys.prefs())
      if (previous) {
        client.setQueryData<NotificationPreferences>(notificationKeys.prefs(), {
          ...previous,
          throttle_minutes: input.throttle_minutes ?? previous.throttle_minutes,
          types: previous.types.map((t) => (input.types?.[t.type] ? { ...t, channels: input.types[t.type] as NotificationChannels } : t)),
        })
      }
      return { previous }
    },
    onError: (_error, _input, context) => {
      if (context?.previous) client.setQueryData(notificationKeys.prefs(), context.previous)
    },
    onSuccess: (prefs) => client.setQueryData(notificationKeys.prefs(), prefs),
  })
}
