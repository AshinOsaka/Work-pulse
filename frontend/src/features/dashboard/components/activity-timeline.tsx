import {
  AppWindow,
  BellRing,
  CircleCheck,
  History,
  Laptop,
  LogIn,
  Moon,
  UserCog,
  Users,
  type LucideIcon,
} from 'lucide-react'
import { Link } from 'react-router'

import { EmptyState } from '@/components/common/empty-state'
import { Skeleton } from '@/components/ui/misc'
import { WidgetCard, WidgetError } from '@/features/dashboard/components/widget'
import type { ActivityEvent, ActivityKind } from '@/features/dashboard/data/types'
import { useNow } from '@/hooks/use-now'
import { formatDateTime, formatRelative } from '@/lib/format'
import { cn } from '@/lib/utils'

const KIND: Record<ActivityKind, { icon: LucideIcon; className: string }> = {
  session: { icon: LogIn, className: 'bg-primary-soft text-primary-soft-foreground' },
  application: { icon: AppWindow, className: 'bg-muted text-muted-foreground' },
  idle: { icon: Moon, className: 'bg-warning-soft text-warning' },
  task: { icon: CircleCheck, className: 'bg-success-soft text-success' },
  alert: { icon: BellRing, className: 'bg-destructive-soft text-destructive' },
  people: { icon: Users, className: 'bg-primary-soft text-primary-soft-foreground' },
  device: { icon: Laptop, className: 'bg-info-soft text-info' },
  account: { icon: UserCog, className: 'bg-muted text-muted-foreground' },
}

function TimelineItem({ event, now, last }: { event: ActivityEvent; now: number; last: boolean }) {
  const kind = KIND[event.kind]
  const Icon = kind.icon
  const actorName = event.actor?.name ?? 'Someone'
  return (
    <li className="relative flex gap-3 pb-5 animate-in duration-500 fade-in-0 slide-in-from-top-1 last:pb-0">
      {!last && <span className="absolute top-8 bottom-0 left-[15px] w-px bg-border" aria-hidden />}
      <span className={cn('relative flex size-8 shrink-0 items-center justify-center rounded-full ring-4 ring-card', kind.className)}>
        <Icon className="size-3.5" aria-hidden />
      </span>
      <div className="min-w-0 flex-1 pt-1">
        <p className="text-[13px] leading-snug">
          {event.actor?.employeeId ? (
            <Link to={`/people/employees/${event.actor.employeeId}`} className="font-medium hover:text-primary">
              {actorName}
            </Link>
          ) : (
            <span className="font-medium">{actorName}</span>
          )}{' '}
          <span className="text-muted-foreground">{event.summary}</span>
        </p>
        {event.detail && <p className="mt-0.5 truncate text-[12px] text-muted-foreground">{event.detail}</p>}
        <time dateTime={event.timestamp} title={formatDateTime(event.timestamp)} className="mt-0.5 block text-[11px] text-muted-foreground">
          {formatRelative(event.timestamp, now)}
        </time>
      </div>
    </li>
  )
}

interface ActivityTimelineCardProps {
  data: ActivityEvent[] | undefined
  isPending: boolean
  isError: boolean
  error: unknown
  isRefreshing: boolean
  onRetry: () => void
  sample: boolean
}

export function ActivityTimelineCard({ data, isPending, isError, error, isRefreshing, onRetry, sample }: ActivityTimelineCardProps) {
  const now = useNow(30_000)
  const events = (data ?? []).slice(0, 25)
  return (
    <WidgetCard
      title="Recent activity"
      description={sample ? 'Live stream of workforce events' : 'Organisation changes in your scope'}
      sample={sample}
      refreshing={isRefreshing}
      className="xl:row-span-2"
    >
      {isError ? (
        <WidgetError error={error} onRetry={onRetry} />
      ) : isPending ? (
        <div className="space-y-4 p-5">
          {Array.from({ length: 7 }, (_, i) => (
            <div key={i} className="flex gap-3">
              <Skeleton className="size-8 rounded-full" />
              <div className="flex-1 space-y-1.5">
                <Skeleton className="h-3 w-4/5" />
                <Skeleton className="h-2.5 w-1/3" />
              </div>
            </div>
          ))}
        </div>
      ) : events.length === 0 ? (
        <EmptyState
          size="sm"
          icon={History}
          title="No activity yet"
          description="Changes to people, invitations, roles and devices will appear here as they happen."
        />
      ) : (
        <ol
          className="max-h-[42rem] flex-1 overflow-y-auto rounded-b-xl px-5 pt-3 pb-5 outline-none focus-visible:ring-[3px] focus-visible:ring-ring/40 focus-visible:ring-inset"
          aria-label="Recent activity"
          aria-live="off"
          // A scrollable region must be keyboard-focusable so it can be scrolled without a mouse (WCAG 2.1.1).
          // oxlint-disable-next-line jsx-a11y/no-noninteractive-tabindex
          tabIndex={0}
        >
          {events.map((event, index) => (
            <TimelineItem key={event.id} event={event} now={now} last={index === events.length - 1} />
          ))}
        </ol>
      )}
    </WidgetCard>
  )
}
