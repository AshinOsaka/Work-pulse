import { useState } from 'react'
import { Bell, BellOff, CheckCheck } from 'lucide-react'
import { Link } from 'react-router'

import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/misc'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { useMarkNotifications, useNotifications, useUnreadCount } from '@/features/notifications/api'
import { NotificationItem } from '@/features/notifications/notification-item'

/** Top-bar bell: live unread count, the latest items, mark all read. */
export function NotificationBell() {
  const [open, setOpen] = useState(false)
  const unread = useUnreadCount().data?.unread ?? 0
  const latest = useNotifications({ page_size: 8 }, open)
  const mark = useMarkNotifications()
  const label = unread ? `Notifications, ${unread} unread` : 'Notifications'
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button variant="ghost" size="icon-sm" aria-label={label} className="relative">
          <Bell />
          {unread > 0 && (
            <span className="absolute -top-0.5 -right-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-destructive px-1 text-[10px] leading-none font-semibold text-white tabular" aria-hidden>
              {unread > 99 ? '99+' : unread}
            </span>
          )}
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-[22rem] p-0">
        <div className="flex items-center justify-between border-b px-4 py-2.5">
          <p className="text-[13px] font-semibold">
            Notifications {unread > 0 && <span className="font-normal text-muted-foreground">· {unread} unread</span>}
          </p>
          <Button size="sm" variant="ghost" disabled={!unread} loading={mark.isPending} onClick={() => mark.mutate({ all: true, read: true })}>
            <CheckCheck /> Mark all read
          </Button>
        </div>
        {!latest.data ? (
          <div className="space-y-2 p-4">
            <Skeleton className="h-12" />
            <Skeleton className="h-12" />
          </div>
        ) : latest.data.items.length === 0 ? (
          <div className="flex flex-col items-center gap-2 px-6 py-10 text-center">
            <BellOff className="size-6 text-muted-foreground" aria-hidden />
            <p className="text-[13px] font-medium">You&apos;re all caught up</p>
            <p className="text-[12px] text-muted-foreground">Alerts you subscribe to appear here as they happen.</p>
          </div>
        ) : (
          <ul className="max-h-[420px] divide-y overflow-y-auto">
            {latest.data.items.map((n) => (
              <NotificationItem key={n.id} n={n} compact onRead={(read) => mark.mutate({ ids: [n.id], read })} onNavigate={() => setOpen(false)} />
            ))}
          </ul>
        )}
        <div className="flex items-center justify-between border-t px-4 py-2 text-[12px]">
          <Link to="/alerts" onClick={() => setOpen(false)} className="font-medium text-primary hover:underline">
            Open notification center
          </Link>
          <Link to="/alerts?tab=preferences" onClick={() => setOpen(false)} className="text-muted-foreground hover:text-foreground">
            Preferences
          </Link>
        </div>
      </PopoverContent>
    </Popover>
  )
}
