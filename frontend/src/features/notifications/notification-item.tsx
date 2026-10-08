import { Check, Dot } from 'lucide-react'
import { Link } from 'react-router'

import { Button } from '@/components/ui/button'
import { SEVERITY, TYPE } from '@/features/notifications/meta'
import { formatDateTime, formatRelative } from '@/lib/format'
import { cn } from '@/lib/utils'
import type { AppNotification } from '@/types/api'

/** One notification. Opening its link marks it read; the toggle flips read/unread. */
export function NotificationItem({
  n,
  onRead,
  compact,
  onNavigate,
}: {
  n: AppNotification
  onRead: (read: boolean) => void
  compact?: boolean
  onNavigate?: () => void
}) {
  const severity = SEVERITY[n.severity]
  const kind = TYPE[n.type]
  const Body = (
    <span className="min-w-0 flex-1">
      <span className={cn('block text-[13px]', n.read ? 'text-muted-foreground' : 'font-semibold')}>
        {n.title}
        {n.count > 1 && (
          <span className="ml-1.5 rounded bg-muted px-1 text-[10px] font-medium text-muted-foreground tabular" title={`Happened ${n.count} times; repeats are combined`}>
            ×{n.count}
          </span>
        )}
      </span>
      {!compact && <span className="mt-0.5 block text-[12px] text-muted-foreground">{n.body}</span>}
      <span className="mt-1 flex flex-wrap items-center gap-x-2 text-[11px] text-muted-foreground">
        <span className={cn('inline-flex items-center gap-1 font-medium', severity.text)}>
          <severity.icon className="size-3" aria-hidden /> {severity.label}
        </span>
        <span>· {kind.label}</span>
        {!compact && n.employee && <span>· {n.employee.name}</span>}
        <span title={formatDateTime(n.last_occurred_at)}>· {formatRelative(n.last_occurred_at)}</span>
      </span>
    </span>
  )
  return (
    <li className={cn('group flex items-start gap-3 px-4 py-3', !n.read && 'bg-primary-soft/25')}>
      <span className={cn('mt-0.5 flex size-7 shrink-0 items-center justify-center rounded-full', severity.soft)} aria-hidden>
        <kind.icon className={cn('size-3.5', severity.text)} />
      </span>
      {n.link ? (
        <Link
          to={n.link}
          className="min-w-0 flex-1 rounded-sm outline-none focus-visible:ring-[3px] focus-visible:ring-ring/40"
          onClick={() => {
            if (!n.read) onRead(true)
            onNavigate?.()
          }}
        >
          {Body}
        </Link>
      ) : (
        Body
      )}
      <Button
        size="icon-sm"
        variant="ghost"
        className="shrink-0 text-muted-foreground"
        aria-label={n.read ? `Mark “${n.title}” as unread` : `Mark “${n.title}” as read`}
        title={n.read ? 'Mark as unread' : 'Mark as read'}
        onClick={() => onRead(!n.read)}
      >
        {n.read ? <Dot className="size-5" /> : <Check />}
      </Button>
    </li>
  )
}
