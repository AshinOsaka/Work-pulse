import { formatSeconds } from '@/features/activity/format'
import { CATEGORY, CATEGORY_ORDER, share } from '@/features/productivity/meta'
import { cn } from '@/lib/utils'
import type { ProductivityMetrics } from '@/types/api'

/** One stacked bar of tracked time by category, with a labelled legend (identity never relies on colour alone). */
export function CategoryBar({
  metrics,
  legend = true,
  className,
}: {
  metrics: ProductivityMetrics
  legend?: boolean
  className?: string
}) {
  const total = metrics.tracked_seconds
  const parts = CATEGORY_ORDER.map((key) => ({ key, ...CATEGORY[key], seconds: metrics[CATEGORY[key].metric] as number })).filter(
    (p) => p.seconds > 0,
  )
  const summary = parts.map((p) => `${p.label} ${formatSeconds(p.seconds)} (${share(p.seconds, total)}%)`).join(', ')

  return (
    <div className={cn('space-y-2', className)}>
      <span className="sr-only">{total ? summary : 'No tracked time'}</span>
      <div className="flex h-3 w-full gap-[2px] overflow-hidden rounded-full bg-muted" aria-hidden>
        {parts.map((p) => (
          <span
            key={p.key}
            className={cn('h-full first:rounded-l-full last:rounded-r-full', p.swatch)}
            style={{ width: `${(100 * p.seconds) / total}%`, minWidth: 3 }}
            title={`${p.label}: ${formatSeconds(p.seconds)} (${share(p.seconds, total)}%)`}
          />
        ))}
      </div>
      {legend && (
        <ul className="flex flex-wrap gap-x-4 gap-y-1 text-[12px]">
          {CATEGORY_ORDER.map((key) => {
            const c = CATEGORY[key]
            const seconds = metrics[c.metric] as number
            return (
              <li key={key} className="inline-flex items-center gap-1.5 text-muted-foreground">
                <span className={cn('size-2.5 rounded-sm', c.swatch)} aria-hidden />
                {c.label}
                <span className="font-medium text-foreground tabular">{formatSeconds(seconds)}</span>
                {total > 0 && <span className="tabular">({share(seconds, total)}%)</span>}
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}
