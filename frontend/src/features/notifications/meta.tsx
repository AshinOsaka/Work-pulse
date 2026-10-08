import { useEffect } from 'react'
import {
  CalendarClock,
  CircleAlert,
  Clock,
  Info,
  LogIn,
  LogOut,
  Monitor,
  MonitorOff,
  MonitorPlay,
  Camera,
  Moon,
  TriangleAlert,
  WifiOff,
  type LucideIcon,
} from 'lucide-react'
import { useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router'
import { toast } from 'sonner'

import { notificationKeys } from '@/features/notifications/api'
import { subscribe } from '@/lib/realtime'
import type { AppNotification, NotificationSeverity, NotificationType } from '@/types/api'

export const TYPE: Record<NotificationType, { label: string; icon: LucideIcon }> = {
  employee_offline: { label: 'Employee offline', icon: WifiOff },
  device_offline: { label: 'Device offline', icon: MonitorOff },
  extended_idle: { label: 'Extended idle', icon: Moon },
  shift_started: { label: 'Shift started', icon: LogIn },
  shift_ended: { label: 'Shift ended', icon: LogOut },
  task_overdue: { label: 'Task overdue', icon: Clock },
  project_deadline: { label: 'Project deadline', icon: CalendarClock },
  live_session_started: { label: 'Live session started', icon: MonitorPlay },
  live_session_ended: { label: 'Live session ended', icon: Monitor },
  screenshot_policy: { label: 'Screenshot policy', icon: Camera },
}

/** Severity is always shown with its label and icon, never colour alone. */
export const SEVERITY: Record<NotificationSeverity, { label: string; icon: LucideIcon; dot: string; text: string; soft: string }> = {
  info: { label: 'Info', icon: Info, dot: 'bg-info', text: 'text-info', soft: 'bg-info-soft' },
  warning: { label: 'Warning', icon: TriangleAlert, dot: 'bg-warning', text: 'text-warning', soft: 'bg-warning-soft' },
  critical: { label: 'Critical', icon: CircleAlert, dot: 'bg-destructive', text: 'text-destructive', soft: 'bg-destructive-soft' },
}

export const TYPES = Object.keys(TYPE) as NotificationType[]

/**
 * Listens for notifications pushed over the realtime gateway: updates the unread badge and lists instantly.
 * Only warnings and critical items pop a toast (info just counts), and repeats that were folded into an
 * existing notification never toast again — so nothing nags.
 */
export function useNotificationStream() {
  const client = useQueryClient()
  const navigate = useNavigate()
  useEffect(
    () =>
      subscribe((event) => {
        if (event.type !== 'notification.created' && event.type !== 'notification.updated') return
        const payload = event.payload as { notification?: AppNotification; unread_count?: number }
        if (typeof payload.unread_count === 'number') client.setQueryData(notificationKeys.unread(), { unread: payload.unread_count })
        void client.invalidateQueries({ queryKey: ['notifications', 'list'] })
        const n = payload.notification
        if (event.type === 'notification.created' && n && n.severity !== 'info') {
          toast(n.title, {
            description: n.body,
            icon: n.severity === 'critical' ? <CircleAlert className="size-4 text-destructive" /> : <TriangleAlert className="size-4 text-warning" />,
            action: n.link ? { label: 'Open', onClick: () => navigate(n.link as string) } : undefined,
          })
        }
      }),
    [client, navigate],
  )
}
