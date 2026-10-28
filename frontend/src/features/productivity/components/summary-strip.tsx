import { Sparkles } from 'lucide-react'

import { Card } from '@/components/ui/card'
import type { SummaryLine } from '@/types/api'

/**
 * The headline measurements, side by side ("Active work 6h 42m · Task completion 87% · …").
 */
export function SummaryStrip({ lines, title = 'Productivity insight' }: { lines: SummaryLine[]; title?: string }) {
  return (
    <Card className="p-5">
      <p className="flex items-center gap-2 text-[13px] font-semibold">
        <Sparkles className="size-4 text-muted-foreground" aria-hidden /> {title}
      </p>
      <dl className="mt-3 grid grid-cols-2 gap-x-6 gap-y-3 sm:grid-cols-3 xl:grid-cols-6">
        {lines.map((line) => (
          <div key={line.key} className="min-w-0">
            <dt className="truncate text-[12px] text-muted-foreground">{line.label}</dt>
            <dd className="text-lg font-semibold tracking-tight tabular">{line.value}</dd>
          </div>
        ))}
      </dl>
    </Card>
  )
}
