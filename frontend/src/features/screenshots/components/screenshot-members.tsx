import { PersonAvatar } from '@/components/common/person'
import { Skeleton } from '@/components/ui/misc'
import { cn } from '@/lib/utils'
import type { ScreenshotMember } from '@/types/api'

const DOT: Record<ScreenshotMember['status'], string> = {
  active: 'bg-success',
  idle: 'bg-warning',
  offline: 'bg-muted-foreground/40',
}
const DOT_LABEL: Record<ScreenshotMember['status'], string> = {
  active: 'Active now',
  idle: 'Idle',
  offline: 'Offline',
}

/** The member picker: one card per person, their avatar, name, email and live status. */
export function ScreenshotMemberGrid({
  members,
  loading,
  selectedId,
  onSelect,
}: {
  members: ScreenshotMember[] | undefined
  loading: boolean
  selectedId: string | null
  onSelect: (id: string) => void
}) {
  if (loading) {
    return (
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5">
        {Array.from({ length: 5 }, (_, i) => (
          <Skeleton key={i} className="h-[72px]" />
        ))}
      </div>
    )
  }
  if (!members || members.length === 0) {
    return (
      <p className="py-10 text-center text-[13px] text-muted-foreground">
        No people match. Everyone you manage with the desktop agent appears here.
      </p>
    )
  }
  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5">
      {members.map((m) => {
        const selected = m.employee.id === selectedId
        return (
          <button
            key={m.employee.id}
            type="button"
            onClick={() => onSelect(m.employee.id)}
            aria-pressed={selected}
            className={cn(
              'flex items-center gap-3 rounded-xl border bg-card p-3 text-left shadow-xs transition hover:border-primary/50 hover:shadow-sm',
              selected && 'border-primary bg-primary-soft/30 ring-1 ring-primary',
            )}
          >
            <PersonAvatar name={m.employee.full_name} className="size-10 shrink-0" aria-hidden />
            <span className="min-w-0 flex-1">
              <span className="flex items-center gap-1.5">
                <span className="truncate text-[13px] font-semibold">{m.employee.full_name}</span>
                <span
                  className={cn('size-2 shrink-0 rounded-full', DOT[m.status])}
                  title={DOT_LABEL[m.status]}
                  aria-label={DOT_LABEL[m.status]}
                />
              </span>
              <span className="block truncate text-[12px] text-muted-foreground">{m.employee.email}</span>
            </span>
          </button>
        )
      })}
    </div>
  )
}
