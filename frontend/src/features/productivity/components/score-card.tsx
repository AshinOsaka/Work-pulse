import { Info } from 'lucide-react'

import { Card } from '@/components/ui/card'
import { formatSeconds } from '@/features/activity/format'
import { cn } from '@/lib/utils'
import type { ProductivityScore } from '@/types/api'

/**
 * A calculated figure, always shown with what it is made of: the formula, every input, and what it
 * does and does not mean. A score is never shown on its own.
 */
export function ScoreCard({ score, className }: { score: ProductivityScore; className?: string }) {
  const ok = score.value !== null
  return (
    <Card className={cn('flex flex-col gap-4 p-5', className)}>
      <div>
        <p className="text-[13px] font-medium text-muted-foreground">{score.label}</p>
        <p className="mt-1 text-3xl font-semibold tracking-tight tabular">
          {ok ? `${score.value}%` : <span className="text-xl text-muted-foreground">Not enough data</span>}
        </p>
        {!ok && score.reason && <p className="mt-1 text-[12px] text-muted-foreground">{score.reason}</p>}
      </div>

      <div className="rounded-lg border bg-subtle px-3 py-2.5">
        <p className="text-[11px] font-medium tracking-wide text-muted-foreground uppercase">How it is calculated</p>
        <p className="mt-0.5 font-mono text-[12px]">{score.formula}</p>
        <dl className="mt-2 space-y-1 text-[12px]">
          {score.components.map((c) => (
            <div key={c.key} className="flex justify-between gap-3">
              <dt className="text-muted-foreground">{c.label}</dt>
              <dd className="font-medium tabular">{formatSeconds(c.seconds)}</dd>
            </div>
          ))}
          {score.coverage !== undefined && score.coverage !== null && (
            <div className="flex justify-between gap-3 border-t pt-1">
              <dt className="text-muted-foreground">Activity covered by rules</dt>
              <dd className="font-medium tabular">{score.coverage}%</dd>
            </div>
          )}
        </dl>
      </div>

      <p className="flex gap-2 text-[12px] text-muted-foreground">
        <Info className="mt-0.5 size-3.5 shrink-0" aria-hidden />
        {score.interpretation}
      </p>
    </Card>
  )
}
