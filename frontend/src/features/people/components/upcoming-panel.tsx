import type { LucideIcon } from 'lucide-react'

import { ComingSoonBadge } from '@/components/common/status'
import { Card } from '@/components/ui/card'

interface UpcomingPanelProps {
  icon: LucideIcon
  title: string
  description: string
  bullets?: string[]
}

/** Honest placeholder for profile sections whose data source ships in a later release. */
export function UpcomingPanel({ icon: Icon, title, description, bullets }: UpcomingPanelProps) {
  return (
    <Card className="overflow-hidden">
      <div className="grid md:grid-cols-[minmax(0,1fr)_280px]">
        <div className="p-6 sm:p-8">
          <div className="flex items-center gap-3">
            <div className="flex size-10 items-center justify-center rounded-lg border bg-subtle text-muted-foreground">
              <Icon className="size-5" />
            </div>
            <div>
              <p className="font-semibold">{title}</p>
              <p className="text-[12px] text-muted-foreground">Coming in a future release</p>
            </div>
            <ComingSoonBadge long className="ml-auto" />
          </div>
          <p className="mt-4 max-w-xl text-[13px] text-muted-foreground">{description}</p>
          {bullets && (
            <ul className="mt-4 space-y-2 text-[13px]">
              {bullets.map((b) => (
                <li key={b} className="flex items-center gap-2">
                  <span className="size-1.5 rounded-full bg-primary/50" /> {b}
                </li>
              ))}
            </ul>
          )}
        </div>
        <div className="hidden border-l bg-subtle/60 p-6 md:block" aria-hidden>
          <div className="space-y-3 opacity-70">
            {[0, 1, 2, 3].map((i) => (
              <div key={i} className="flex items-center gap-3">
                <div className="h-2 rounded bg-muted" style={{ width: `${30 + i * 10}%` }} />
                <div className="h-2 flex-1 rounded bg-muted/70" />
              </div>
            ))}
          </div>
          <p className="mt-5 text-center text-[11px] text-muted-foreground">No data yet</p>
        </div>
      </div>
    </Card>
  )
}
